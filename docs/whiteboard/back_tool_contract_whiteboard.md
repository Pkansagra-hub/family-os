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

0R. Current Reality Grounding Pass - 2026-05-30
  Source-backed overlay from Front, Back, Planner, Orchestrator, and Fabric code.
  This pass separates what is live today from the target contracts below.

0D. Four-Plane Development Roadmap - 2026-06-02
  Bottom-up build order across the four planes. Phase 1: Fabric + Bridge gateway.
  Phase 2: Back + E2E Tier 2 spine. Phase 3: Context Plane prompt enrichment.
  Phase 4: IFL connector/tool design formalization. Each phase has a hard gate.

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
If a section says Front should pre-classify domains, guess operations, or resolve resources, it is stale.
    Front's role: pass raw user utterance + full context. Back's role: ALL intent reasoning.
    Front must not pre-classify domain="calendar" or operation="create" — Back derives these from the
    raw query + context (self model, household roster, available services, grounding, beliefs,
    task state, chat history).
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
1. Front captures raw user utterance; packages query + full context (self model, household roster,
   available services, grounding, beliefs, task state, chat history) into BackTaskEnvelope.
   Front does NOT pre-classify intents or domains.
2. FSM canonicalizes task and state correlation, routes to Back.
3. Back receives BackTaskEnvelope containing raw query + full rich context.
4. Back performs ALL intent reasoning: builds RequestFrame (extracts user_goal, actor_ref,
   operation_hints[], resource_references[], people_references[], time_references[],
   location_references[], missing_fields[]) from raw utterance + context.
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

## Current Reality Grounding Pass - 2026-05-30

**Section mode:** current proof overlay for the target design.

This pass does not introduce a new architecture. It grounds the existing design in the code paths that are live today, so future edits can enhance the current system instead of designing from an unimplemented ideal.

### Live Runtime Spine

```text
Front today:
  front_handler builds a mode-specific prompt and tool list.
  The Front LLM can call dispatch_task with user-world intents, params,
  domain hints, reference_context, depends_on, urgency, and plan=true.
  execute_dispatch_task returns ToolResult.data._dispatch; it does not
  emit bus events itself.
  react_loop collects dispatched_tasks.
  front_handler publishes task.dispatch events before any final response.

Back today:
  route_back_envelope calls back_handler.
  back_handler reads SessionState once at task start, then builds the
  Back prompt and runs the shared react_loop.
  Back receives tier-filtered meta-tools, not app tools directly.
  submit_result terminates the loop; _emit_back_result publishes
  task.complete, task.suspended, or task.failed after the loop returns.

Fabric/native tools today:
  discover_capabilities returns scored CapabilityContract records.
  invoke_capability uses the Back binding helper, validates required
  inputs, builds CapabilityRequest, and calls IDispatchPort.dispatch_direct.
  FabricDispatchAdapter forwards LOW/direct capability requests to Fabric.
  Native family tools register CapabilityContract records with
  provider_type=LOCAL and provider_id=k1_native_tools, then execute through
  NativeToolProvider -> BaseToolService.dispatch.

Planner/Orchestrator today:
  MEDIUM Orchestrator tasks execute one or two capabilities directly via Fabric.
  HIGH Orchestrator tasks build a PlanRequest and send it to Planner.
  PipelineController runs SKETCH -> EXPAND -> VALIDATE -> COMMIT.
  CommitService emits k1.planner.plan.ready.v1 with CommittedPlan.to_dict().
  Orchestrator deserializes with CommittedPlan.from_dict(), correlates the
  request_id, validates, acquires the concurrency guard, and executes the DAG.
  DAGExecutor builds Kahn waves, resolves $step result references, dispatches
  StepRunner calls to Fabric, runs guards, aggregates, and compensates when
  side-effect metadata supports it.
```

Primary current-code anchors:

- Front prompt/dispatch: [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1145), [k1/concierge/tools/schemas_front.py](../../k1/concierge/tools/schemas_front.py#L460), [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L1225)
- Shared ReAct loop: [k1/concierge/react/loop.py](../../k1/concierge/react/loop.py#L1048)
- Back prompt/execution: [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L940), [k1/concierge/tools/schemas_back.py](../../k1/concierge/tools/schemas_back.py#L286)
- Back binding/invocation: [k1/concierge/react/capability_routing.py](../../k1/concierge/react/capability_routing.py#L34), [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L328), [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L1487)
- Orchestrator routing/DAG: [k1/orchestrator/orchestration/orchestrator_service.py](../../k1/orchestrator/orchestration/orchestrator_service.py#L1518), [k1/orchestrator/orchestration/orchestrator_service.py](../../k1/orchestrator/orchestration/orchestrator_service.py#L1688), [k1/orchestrator/orchestration/dag_executor.py](../../k1/orchestrator/orchestration/dag_executor.py#L125)
- Planner pipeline/delivery: [k1/planner/pipeline_controller.py](../../k1/planner/pipeline_controller.py#L430), [k1/planner/stages/expand_service.py](../../k1/planner/stages/expand_service.py#L1110), [k1/planner/stages/commit_service.py](../../k1/planner/stages/commit_service.py#L429)
- Fabric contracts/native provider: [k1/fabric/types.py](../../k1/fabric/types.py#L718), [k1/fabric/manifest_translator.py](../../k1/fabric/manifest_translator.py#L167), [k1/tools/family/bootstrap.py](../../k1/tools/family/bootstrap.py#L115), [k1/fabric/providers/native_tool_provider.py](../../k1/fabric/providers/native_tool_provider.py#L192)

### Target-Only As Of This Pass

The following names are design contracts in this whiteboard, not first-class runtime primitives in the current K1 code path:

```text
resolve_situation
RequestFrame as the mandatory Back input object
ResolutionEnvelope as the resolver return object
CandidateUniverse as the canonical local-world projection object
PromptPack as the model context contract
BindingBundle / binding_id as the normal execution authority
connector/capability constitution artifacts with companion_resource roles
cross-resource (person, time-window) availability projection
```

There is a current binding helper, but it is not the same thing as the target binding authority. Today `bind_capability(...)` validates or repairs the exact `capability_name` path for Back; the target `BindingBundle` would bind actor, resource, capability, policy, schema, freshness, and allowed actions.

### Design Implication

The current code already has the right major bones: Front dispatch, Back meta-tools, Fabric CapabilityContract registry, native provider execution, Planner pipeline, Orchestrator DAG waves, parameter resolution, guards, and compensation hooks. The next design work should therefore be additive and contract-binding:

```text
do not replace Front/Back/Planner/Orchestrator/Fabric;
make the existing handoff objects carry typed authority evidence;
make current discovery/invocation a compatibility spine;
promote staged resolver, PromptPack, CandidateUniverse, and binding ids
only where the live path can prove them.
```

---

## Four-Plane Development Roadmap

**Section mode:** development plan — build order, gates, and dependencies.
**Date:** 2026-06-02
**Status:** active. This section defines HOW development proceeds across the four planes.

The four-plane decomposition (IFL, Fabric, Back, Context Plane) defines the component architecture. This section defines the build order. The two are complementary:

```text
4-plane decomposition  →  WHAT each plane owns (static architecture)
4-plane development roadmap  →  HOW we build and prove each plane (dynamic order)
```

The build order is bottom-up by dependency. A plane cannot be proven until the planes it depends on are proven.

### Dependency Chain

```text
Fabric (Phase 1)
  ↑ depends on: ModelHub, Bridge connector gateway, FamilyToolsBundle
  ↑ provides: capability registry, resolver, policy enforcement, invocation dispatch

Back (Phase 2)
  ↑ depends on: Fabric (Phase 1 proven)
  ↑ provides: LLM ReAct loop, RequestFrame, tier classification, prompt assembly

Context Plane (Phase 3)
  ↑ depends on: Back + Fabric (Phase 2 proven)
  ↑ provides: rich temporal/spatial/grounding signals to Back's prompt

IFL (Phase 4)
  ↑ depends on: Fabric + Back + Context Plane (Phase 3 proven)
  ↑ provides: formal connector/tool design contract, manifest standard, adapter protocol
```

Each phase has an integration gate. A phase is not "done" until its gate passes.

---

### Phase 1 — Fabric: Tool Search, Invocation, Meta-Tools, Task Resolver

**Goal:** Prove the Fabric execution spine works standalone — all adapters, ports, meta-tools, and the Bridge connector gateway.

**What this phase owns:**

```text
CapabilityFabric (9-step _execute_impl)
  → resolve provider → build context → circuit-break → validate output

CapabilityRegistry
  → all 41+ family-tool capability contracts registered
  → FTS5-indexed for indexed lookup

ProviderFactory
  → MCP, WASM, BRIDGE, AGENT, WORKFLOW, CONCIERGE, LOCAL_STUB, NATIVE
  → NativeToolProvider wired for calendar/tasks/reminders/chores/shopping

Meta-tool surface
  → resolve_situation (target authority path)
  → invoke_capability (bound invocation)
  → batch_invoke_capabilities (independent parallel)
  → discover_capabilities (legacy catalog — marked for deprecation, C-014)
  → submit_result (terminal)
  → recall_memory (paired contract via Bridge)

Policy selector and enforcer
  → PolicyBundle with gates[], hil_triggers[], verifier_requirements[]
  → policy_cards[] for Back's prompt
  → guide_selection_rules[]

Bridge connector gateway (security boundary)
  → ConnectorGateway (3-stage pipeline: token verify → adapter verify → route)
  → CredentialVault (AES256-GCM, secrets never leave Bridge)
  → MCP process manager (per-adapter child process supervision)
  → Envelope signing (Ed25519), band enforcement, rate limiting, circuit breaking

IdempotencyStore
  → in_flight → succeeded/failed state machine
  → immutable-succeeded invariant

VerificationPlanRunner
  → build_plan → run → gate
  → read_after_write (proven), output_schema (proven)

HIL service (shared)
  → HumanInTheLoopService (S2.5)
  → per-session HIL on session_bus (P1.5)

Adapters:
  → EventPortProdAdapter, DeltaBusProdAdapter, BridgeConnectionAdapter
  → ModelGatewayBridgeAdapter, PromptSystemProdAdapter
  → SessionStateReaderAdapter, SessionRoutingStateReader
```

**What this phase does NOT own:**

```text
- Back's ReAct loop or prompt (Phase 2)
- Back's RequestFrame builder (Phase 2)
- Rich prompt grounding signals (Phase 3)
- IFL manifest standard or per-adapter MCP server design (Phase 4)
- IFL-tier protocol engine, adapter registry (Phase 4)
- Connector/tool authoring documentation (Phase 4)
```

**What's already wired (from service.py):**

```text
S1:  Bus + Router + AsyncBusBridge
S2:  ModelHub (provider registry, LLM gateway)
S3:  Shared Fabric (CapabilityFabric, 9-step pipeline)
S4:  Bridge (Live/Sink/Offline adapter); runs BEFORE S3
S8:  FamilyToolsBundle (NativeToolProvider, ToolRegistry, K1FamilyStore)

P3:  Per-session Fabric reuses shared CapabilityRegistry
P3.1: NativeToolProvider re-registered on per-session fabric
P1.5: Per-session HIL service bound to session_bus
```

**Phase 1 integration gate:**

```text
GATE-P1: Fabric standalone proven.

Required:
  ✓ All 41+ family-tool capability contracts registered and discoverable
  ✓ resolve_situation returns ResolutionEnvelope with valid CandidateUniverse
  ✓ invoke_capability executes calendar.create_event with schema-valid params → ok
  ✓ NativeToolProvider dispatches to correct adapter service
  ✓ Bridge ConnectorGateway validates tokens and routes to adapter
  ✓ IdempotencyStore prevents duplicate execution
  ✓ VerificationPlanRunner.read_after_write confirms event exists after create
  ✓ PolicySelector returns PolicyBundle with gates for calendar write
  ✓ HIL service fires hil.request on missing_required_params
  ✓ discover_capabilities returns catalog results (legacy path, catalog-only marker)
  ✓ All adapter ports satisfy their protocol types (isinstance checks)
  ✓ Negative proof: invalid params → capability_params_incomplete
  ✓ Negative proof: AMBER band → band_denied
  ✓ Negative proof: missing connector → missing_capability

Tests to run:
  pytest tests/k1/fabric/ -v
  pytest tests/k1/tools/family/ -v
  pytest tests/bridge/connector/ -v
  pytest tests/k1/hil/ -v
  pytest poc/back_tool_contract_v2/test_resolve_situation.py -v
  pytest poc/back_tool_contract_v2/test_idempotency_store.py -v
  pytest poc/back_tool_contract_v2/test_verification_runner.py -v
```

**Key design note — connector redesign:** Family tools (calendar/tasks/reminders/chores/shopping) are already wired at S8. But their schemas follow the legacy `ActionSpec` model. During Phase 1, these connectors should be redesigned to carry:

```text
- Full input/output JSON schemas (not only required_inputs/optional_inputs hints)
- Connector constitution (preconditions, companion resources, conflict checks, HIL gates)
- Verifier affordances (read_after_write, state_compare, etc.)
- Side-effect declarations
- Freshness guarantees
- Capability naming: tool.{read|execute}.{connector_id}.{action} (already followed)
```

This redesign is Phase 1 work because Fabric needs real schemas to test the resolver, policy selector, and verifier. The formal IFL standard (Phase 4) will document this design pattern, but the actual schema work happens here.

---

### Phase 2 — Back: Prompt, ReAct Loop, Context, Tool Invocation Paradigm

**Goal:** Prove the full Tier 2 spine end-to-end: `Back → resolve_situation → Fabric → Bridge → NativeToolProvider → calendar.create_event`.

**What this phase owns:**

```text
Back Context Model — Back receives raw query + FULL rich context
  Back is the SOLE intelligence/execution layer. Front passes raw user utterance
  plus full context. Back does ALL intent reasoning — extracts frame, classifies
  operations, resolves people/resources, detects missing fields.

  Back's prompt is assembled from these context blocks at loop_start:

  (A) Self Model — actor identity, household role, autonomy level, situation frame
      S(actor) ∩ F ∩ C — who am I, what can I do, what constraints apply.
      Source: SelfModelHandle (P3.5), SituationFrame.

  (B) Household Roster — space members with display_name, role, age_band,
      linked_resource_ids (who has which calendar/tasks/chores connected).
      Source: LocalProjectionStore.household_members, SpaceGraphService.

  (C) Available Services — connector catalog (names + descriptions, NO schemas yet):
      what connectors are admitted and connected for this household.
      Source: GlobalProjectionStore.connectors + LocalProjectionStore.connected_resources.

  (D) Grounding Block — resolved temporal context ("now" in household timezone,
      "next Monday" → ISO 8601), resolved spatial context (device location, geofence
      hints), freshness state, staleness warnings.
      Source: TemporalHandle (P3.6), SpatialHandle (P3.7), GroundingHandle (P3.8).

  (E) Beliefs / Memory — relevant memory items, prior task outcomes, learned patterns.
      Source: recall_memory meta-tool via Bridge, MemoryWriter.

  (F) Active Task State — task kind, safety band, budget (max_iterations,
      max_fabric_calls, prompt_tokens), session_id, prior HIL responses.
      Source: FSM, SessionState, BackTaskEnvelope.

  (G) Chat History — recent conversation turns for grounding and continuity.
      Source: SessionState narrative thread.

  Back uses ALL of this context to build the RequestFrame and call resolve_situation.
  Front's only job: capture the user's words and hand them to Back with the raw
  context blocks attached. Front MUST NOT pre-classify domains, guess operations,
  or resolve resources. All of that is Back's responsibility.

Back system prompt
  → stable executor role
  → meta-tool declarations (resolve_situation, invoke_capability, batch_invoke_capabilities,
    submit_result, recall_memory)
  → GLOBAL constitution rules (build RequestFrame first, never invent tools, act only
    through allowed_next_actions, submit_result with evidence)
  → discover_capabilities demoted to catalog-only (discovery_mode flag, C-014)

Back ReAct loop
  → orient → resolve → decide → bind → read/check/ask/write → finish
  → bounded by allowed_next_actions[] from ResolutionEnvelope
  → tier classification (Tier 2 vs. promote-to-Tier 3)
  → submit_result as terminal meta-tool

RequestFrame builder
  → extracts user_goal, actor_ref, operation_hints[], resource_references[],
    people_references[], time_references[], location_references[], missing_fields[]
  → calls resolve_situation for execution tasks (NOT discover_capabilities)

BackTaskEnvelope (CC-0)
  → task_id, actor_ref, raw_user_utterance, task_kind, safety_context
  → self_model_ref (SituationFrame: who am I, role, constraints)
  → household_roster_ref (space members with display_name, role, age_band, linked_resources)
  → available_services_ref (admitted + connected connectors for this household)
  → grounding_snapshot_ref (resolved temporal, spatial, participant context)
  → beliefs_memory_ref (relevant memory items, prior outcomes, learned patterns)
  → active_task_state_ref (budget, prior HIL responses, narrative thread)
  → chat_history_ref (recent conversation turns)
  → Front MUST NOT pre-classify domain, operation, or resource — Back does ALL intent reasoning
    from the raw utterance + context blocks above.

BackTaskOutcome (CC-0)
  → status: completed | partial | needs_hil | cannot_execute | blocked | failed
  → submit_result with structured evidence
  → hil_request with CandidateUniverse choices

Tool invocation paradigm
  → Back invokes by binding_id, not hand-copied capability_name
  → FabricDispatchAdapter → CapabilityFabric.execute()
  → Back receives InvocationObservation, not raw provider stack traces

HIL integration
  → Back asks HIL through HILRequest with choices from CandidateUniverse
  → HIL response arrives in next BackTaskEnvelope

BackPromotionOutcome
  → escalation_reason, candidate_universe_ref, connector_constitution_refs[],
    companion_resource_roles[], known_missing_fields[]
  → structured handoff to FSM → Orchestrator (Tier 3)

Concierge Single Writer rule
  → Back returns deltas/outcomes; Concierge writes SessionState
```

**What this phase does NOT own:**

```text
- Resolution logic (Fabric, Phase 1)
- Policy enforcement (Fabric, Phase 1)
- Rich temporal/spatial/grounding prompt injection (Context Plane, Phase 3)
- Connector/tool design contracts (IFL, Phase 4)
```

**What's already wired (from service.py):**

```text
P4:  Concierge (per-session) — ConciergeFactory.create_with_ports()
     → PortBundle with llm, dispatch, temporal, spatial, grounding, memory, writer
     → BusInputAdapter, BusOutputAdapter, SSMStateAdapter, FabricDispatchAdapter
     → front_mailbox + back_mailbox registered on session_router

P6:  SessionInstance assembled + Concierge.start() + MemoryWriter.start()
     → front_dispatcher, back_dispatcher, front_ctx, back_ctx
     → self_model handle wired (P3.5 pre-start install)
```

**Phase 2 integration gate:**

```text
GATE-P2: Full Tier 2 spine proven end-to-end.

Prerequisite: GATE-P1 passed.

Required:
  ✓ Back receives BackTaskEnvelope → builds RequestFrame → calls resolve_situation
  ✓ resolve_situation returns ResolutionEnvelope with allowed_next_actions[]
  ✓ Back follows connector constitution: list before create, check conflicts
  ✓ Back invokes calendar.create_event via binding_id → Fabric → Bridge → NativeToolProvider
  ✓ InvocationObservation returns ok with event_id
  ✓ VerificationObservation confirms event exists (read_after_write)
  ✓ Back calls submit_result(completed) with structured evidence
  ✓ HIL fires on missing required field; Back presents HIL choices from CandidateUniverse
  ✓ Back promotes to Tier 3 when connector constitution declares companion_resource roles
  ✓ discover_capabilities called with discovery_mode=catalog → catalog-only marker
  ✓ Back refuses to invoke from catalog results (allowed_next_actions=[])
  ✓ Negative proof: Back cannot invoke without resolve_situation (execution mode)
  ✓ Negative proof: Back cannot call submit_result before verification
  ✓ Negative proof: Back cannot invent capability names

Tests to run:
  pytest tests/k1/concierge/actors/test_back.py -v
  pytest tests/k1/concierge/react/test_loop.py -v
  pytest tests/k1/concierge/prompt/test_back_prompt.py -v
  pytest tests/k1/concierge/tools/test_invoke_capability.py -v
  pytest tests/k1/concierge/tools/test_discover_capabilities.py -v
  pytest tests/k1/concierge/test_back_front_handoff.py -v
```

**Key design note — connector redesign continued:** Phase 1 redesigned the family tool schemas. Phase 2 is where those redesigned schemas are exercised through the FULL Tier 2 spine. If `calendar.create_event` carries a constitution that says "list before create, check chores/tasks for conflicts," then Back's ReAct loop must actually execute those steps in order. This is the first time the dumb-LLM rule is tested with a real LLM in the loop.

---

### Phase 3 — Context Plane: Spatial, Temporal, Session State Signals to Back Prompt

**Goal:** Enrich Back's prompt with the rich grounding signals already available in the kernel plumbing (P3.6–P3.8).

**What this phase owns:**

```text
Enhanced execution_grounding_block (injected at loop_start)
  → resolved temporal context: "now" in household timezone, "next Monday" → ISO 8601
  → resolved spatial context: device location, place refs, geofence hints
  → resolved participant context: space members with display_name, role, age_band
  → session state summary: active task, narrative thread, prior HIL responses
  → safety context seed: autonomy level, privacy band, risk state

Temporal prompt enrichment
  → TemporalHandle (P3.6) already resolves "tomorrow" → date
  → New: inject timezone-aware hints ("household is in US/Eastern, current time 14:32")
  → New: inject upcoming calendar context ("next 7 days: 3 events, 2 chores due")
  → New: deadline awareness ("this task references 'Monday' which is 2026-06-08")

Spatial prompt enrichment
  → SpatialHandle (P3.7) already resolves device location
  → New: inject place context ("household location: 123 Main St, radius 50km")
  → New: inject geofence-aware hints ("Riley's school is 15 min from home")

Participant/identity prompt enrichment
  → SelfModelHandle (P3.5) already provides SituationFrame = S(actor) ∩ F ∩ C
  → New: inject resolved participant list into Back's prompt
    ("household members: Riley (child, 8), Jordan (adult, caregiver), ...")
  → New: flag missing identity resolution as uncertainty_markers[]
    ("Could not resolve 'Aunt Sarah' to a known household member")

Grounding freshness signals
  → GroundingHandle (P3.8) already refreshes per-turn
  → New: inject freshness state into Back's prompt
    ("grounding snapshot age: 2.3s — fresh")
  → New: inject stale warnings
    ("spatial context last refreshed 4 hours ago — may be stale")

Context-aware PromptPack enrichment
  → PromptPack already carries candidate_summary, policy_cards, guide_cards
  → New: PromptPack carries context_summary with temporal/spatial/participant signals
  → New: decision_surface enriched with context-derived constraints
    ("Only Riley's calendar is writeable by you; Jordan's is read-only")

Participant resolution service (C-013 implementation)
  → Fabric's resolver consults GroundingProjection.space_id → SpaceGraphService
    → matches display_name against user text references
    → includes resolved participants in CandidateUniverse.impact_set_candidates[]
  → Ambiguous names → Fabric returns needs_disambiguation with member candidates
```

**What this phase does NOT own:**

```text
- Resolution logic (Fabric, Phase 1)
- ReAct loop mechanics (Back, Phase 2)
- Prompt structure or meta-tool declarations (Back, Phase 2)
- IFL standard (Phase 4)
- Temporal/spatial/grounding BUNDLE infrastructure (already built at S2.7–S2.9, P3.6–P3.8)
  → Phase 3 ENRICHES what reaches the prompt; it does not rebuild the plumbing
```

**What's already wired (from service.py):**

```text
S2.7: Temporal bundle (M1) — clock, timezone, policy stack
S2.8: Spatial bundle (M3) — place registry, geolocation
S2.9: Grounding bundle (M1.5) — composite wrapping temporal+spatial+identity

P3.6: TemporalHandle per-session — refresh_turn() before each Front turn
P3.7: SpatialHandle per-session — refresh_turn() before each Front turn
P3.8: GroundingHandle per-session — refresh_turn() + Fabric context builder binding

P3.5: SelfModelHandle per-session — SituationFrame = S(actor) ∩ F ∩ C
  → install_into_session() wires gate + capsule renderer into Concierge dispatchers
  → render_capsule() injected into DynamicPromptBuilder at stage 9.5

Front handler already receives: temporal, spatial, grounding, self_model handles
  → grounding.refresh_turn() → GroundingEnvelope → GroundingProjection
  → grounding.build_projection() → injected into Front's system prompt
  → grounding_dispatch_metadata attached to dispatch_task payload
```

**Phase 3 integration gate:**

```text
GATE-P3: Rich context signals reach Back's prompt and improve execution quality.

Prerequisite: GATE-P2 passed.

Required:
  ✓ Back's loop_start prompt includes execution_grounding_block with temporal context
  ✓ Back's loop_start prompt includes household member list with roles
  ✓ Back's prompt includes timezone-aware temporal hints
  ✓ Back's prompt flags stale grounding ("spatial context age: 4h — verify location with user")
  ✓ Participant name "Riley" resolved to member_id by Fabric's resolver
  ✓ Unresolved participant names trigger needs_disambiguation (not silent guessing)
  ✓ PromptPack.context_summary carries temporal/spatial/participant signals
  ✓ Policy-derived constraints appear in decision_surface
    ("You can write to Riley's calendar but not Jordan's")
  ✓ Grounding freshness < 5s for active turns
  ✓ Negative proof: stale grounding → Back asks HIL, does not execute
  ✓ Negative proof: unresolvable participant → Back does not guess identity

Tests to run:
  pytest tests/k1/grounding/ -v
  pytest tests/k1/temporal/ -v
  pytest tests/k1/spatial/ -v
  pytest tests/k1/selfmodel/ -v
  pytest tests/k1/concierge/prompt/test_grounding_injection.py -v
  pytest tests/k1/concierge/test_context_plane_prompt_enrichment.py -v
```

---

### Phase 4 — IFL: Connector & Tool Design Formalization

**Goal:** Produce a formal, stable standard for how connectors and tools are designed, documented, and registered. This is the design-time contract that connector authors follow.

**What this phase owns:**

```text
IFL Manifest Standard (CC-8 formalization)
  → manifest_id, connector_id, adapter_id, signing_info
  → resource_models[] with concrete resource identity fields
  → capability_templates[] with full input/output JSON schemas
  → event_topics[] for projection freshness
  → auth_scopes[], safety_metadata, verifier_affordances[]
  → freshness_guarantees

Connector Constitution Standard
  → per-connector procedural execution rules
  → preconditions (e.g., "list before create")
  → companion_resource roles
  → conflict_analysis_rules[]
  → mutation_sequencing[]
  → hil_gates[]
  → verification_requirements[]
  → constitution versioning (ships with connector, not prompt — Principle 6)

Tool Design Contract
  → capability naming: tool.{read|execute}.{connector_id}.{action}
  → input schema: JSON Schema with required/optional fields, types, constraints
  → output schema: structured result shape
  → effect_summary: side_effects, compensation hints
  → safety_requirement: min_band, autonomy_level
  → limitations[]
  → verifier_refs[]

Policy Authoring Standard
  → how new domains define PolicyCards (not how Fabric enforces them — Phase 1)
  → PolicyBundle schema for domain authors
  → guide_cards authoring patterns
  → cross-connector governance rule templates

Adapter Protocol Standard (CC-7 formalization)
  → IflCommandEnvelope (ifl_schema_version, manifest_id, auth_context_ref, params)
  → IflResultEnvelope (status, remote_correlation_id, resource_state_delta, readback_payload)
  → error codes and recovery actions
  → MCP stdio transport contract

Manifest Ingestion Pipeline (CC-8)
  → ManifestTranslator: IflManifest → CapabilityRegistrationBatch
  → FamilyOS CA adapter signing + verification
  → manifest versioning and upgrade paths

Connector Authoring Guide
  → step-by-step: how to create a new connector
  → adapter implementation template (Python MCP server)
  → credential setup (OAuth, API keys — stored in Bridge CredentialVault)
  → testing checklist: what must pass before registration
  → example: Google Calendar connector as reference implementation
```

**What this phase does NOT own:**

```text
- Runtime enforcement of constitutions (Fabric, Phase 1)
- Runtime policy selection (Fabric, Phase 1)
- CapabilityRegistry population (Fabric's ManifestTranslator handles CC-8)
- Back's prompt or ReAct loop (Phase 2)
- Context signal plumbing (Phase 3)
```

**What's already wired (from bridge/):**

```text
bridge/connector/          → ConnectorGateway, CredentialVault, MCP process manager
bridge/ifl/                → IFL runtime tier (BRIDGE-OWNED)
bridge/ifl/adapters/       → per-adapter MCP packages (e.g., google_calendar/)
bridge/ports/              → 5 protocol definitions (CMD, QRY, SSE, OBS, IFL)
bridge/core/signing.py     → Ed25519 envelope signing
bridge/ifl/mcp_stdio.py    → MCP stdio transport

architecture_diagrams/bridge/
  → bridge_architecture.mmd / v2 — Bridge owns IFL hierarchy
  → interkernel_fabric_layer.mmd — IFL runtime subsystems
```

**Phase 4 integration gate:**

```text
GATE-P4: IFL standard documented, reference connector passes.

Prerequisite: GATE-P3 passed.

Required:
  ✓ IFL Manifest Standard document complete (schema + examples)
  ✓ Connector Constitution Standard document complete
  ✓ Tool Design Contract document complete
  ✓ Policy Authoring Standard document complete
  ✓ Adapter Protocol Standard document complete (IflCommandEnvelope / IflResultEnvelope)
  ✓ Reference connector (Google Calendar) redesigned to new standard
  ✓ Reference connector passes ManifestTranslator → CapabilityRegistrationBatch
  ✓ Reference connector passes Phase 1 Fabric gate with new-schema tools
  ✓ Reference connector passes Phase 2 E2E Tier 2 spine
  ✓ Reference connector constitution gates correctly in Phase 3 Context Plane
  ✓ Connector Authoring Guide published with step-by-step template
  ✓ Negative proof: malformed manifest rejected by ManifestTranslator
  ✓ Negative proof: unsigned adapter rejected by AdapterVerifier
  ✓ Negative proof: manifest with missing constitution fields rejected

Tests to run:
  pytest tests/bridge/ifl/ -v
  pytest tests/k1/fabric/test_manifest_translator.py -v
  pytest tests/k1/fabric/test_capability_registration.py -v
  # Reference connector E2E:
  pytest tests/integration/test_google_calendar_e2e.py -v
```

---

### Phase Dependency Diagram

```text
┌─────────────────────────────────────────────────────────────┐
│                        PHASE 1                              │
│                        FABRIC                                │
│  CapabilityFabric + Registry + Providers + Meta-tools       │
│  Policy selector/enforcer + Bridge gateway + HIL            │
│  Idempotency + Verification                                 │
│                                                             │
│  Gate: Fabric standalone proven                             │
│  Depends on: ModelHub (S2), Bridge (S4), FamilyTools (S8)   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                        PHASE 2                              │
│                         BACK                                 │
│  ReAct loop + Prompt + RequestFrame + Tier classification   │
│  Tool invocation paradigm (binding_id) + HIL integration     │
│  BackPromotionOutcome → Tier 3 handoff                      │
│                                                             │
│  Gate: Full Tier 2 spine proven E2E                         │
│  Depends on: Fabric (Phase 1) + Concierge (P4/P6)           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                        PHASE 3                              │
│                    CONTEXT PLANE                             │
│  Rich temporal + spatial + participant + grounding signals  │
│  Prompt enrichment at loop_start + after_resolution         │
│  Participant resolution service (C-013)                     │
│                                                             │
│  Gate: Rich context improves execution quality              │
│  Depends on: Back + Fabric (Phase 2)                        │
│  Uses existing: P3.6-P3.8 plumbing (not rebuilding)         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                        PHASE 4                              │
│                         IFL                                  │
│  Manifest standard + Constitution standard                  │
│  Tool design contract + Policy authoring standard           │
│  Adapter protocol + Connector authoring guide               │
│  Reference connector (Google Calendar)                      │
│                                                             │
│  Gate: IFL standard published, reference connector passes   │
│  Depends on: Fabric + Back + Context Plane (Phase 3)        │
│  Uses existing: bridge/ifl/ structure, CC-7, CC-8           │
└─────────────────────────────────────────────────────────────┘
```

---

### Relationship to Existing Milestones (M0–M12)

This 4-phase development roadmap does NOT replace the M0–M12 linear milestone list. The two models coexist:

```text
M0–M12 (original)         → WHAT gets built (component-level milestones)
4-Phase Roadmap (this)     → HOW development is organized (plane-level build order)
5-Layer Model (Q21)        → WHY components depend on each other (component dependency graph)
```

Approximate mapping:

| Phase | Maps to M-milestones | Maps to 5-Layer Model |
|---|---|---|
| Phase 1 (Fabric) | M1–M4 (fabric, providers, registry, bridge) | Foundation + Resolver layers |
| Phase 2 (Back) | M5–M8 (concierge, ReAct, prompt, tools) | Resolver + Execution layers |
| Phase 3 (Context Plane) | M9–M10 (grounding, temporal, spatial, selfmodel) | Constitution layer |
| Phase 4 (IFL) | M11–M12 (IFL, adapters, manifests) | Execution + Deprecation + Tier 3 |

Phase 4 is the last phase because it formalizes what Phases 1–3 have proven. You cannot write a stable connector standard until you know what the runtime actually needs from a connector.

---

## Four-Plane Execution Workbook

**Section mode:** execution plan — current code, existing tests, required tests, implementation steps.
**Date:** 2026-06-02
**Status:** living document. Each phase section filled incrementally as work proceeds.

> This section is the HOW companion to the development roadmap (§0D). The roadmap says WHAT to build and in WHAT order. This workbook says HOW — current code reality, tests available today, tests that must be written, files to touch, and the step-by-step plan to reach each gate.

---

### Workbook Phase 1 — Fabric

> **Ground-reality audit date:** 2026-06-02. Based on full code audit of `k1/fabric/` (28 files), `tests/k1/fabric/` (113 test files), `k1/kernel/service.py` (S3, S4, S5, S8, P3 wiring), and `bridge/connector/` (11 files).

---

#### 1.1 Ground Reality — CapabilityFabric Execution Engine

**File:** `k1/fabric/fabric.py` (1643 lines). Three classes in one file.

**A. `CapabilityFabric` — the stateless execution engine (line 190)**

9-step `_execute_impl()` pipeline:

| Step | Label | What happens | Error path |
|------|-------|-------------|------------|
| 1 | Emit invoked | `EventEmitter.emit_invoked()` — `k1.capability.invoked.v1` | Non-blocking |
| 2 | Resolve provider | `Resolver.resolve(request)` → 5-sub-step chain: CapabilityRegistry lookup → ProviderRegistry lookup → PolicyEngine (4 dimensions: SecurityContext, AffectiveRouting, CognitiveLoadRouting, QoSIntegration) → ProviderSelector → ProviderFactory.create() | `resolution_failed` |
| 2.4 | Conscience gate | `IConsciencePort.get_digest(caller_id)` → checks `digest.is_forbidden(social_act)` | `conscience_forbidden` |
| 2.5 | HIL gate | `IHILPort.gate_capability()` → ALLOW/ASK_APPROVED/DENY/ASK_REJECTED/TIMEOUT | `hil_denied` / `hil_rejected_by_user` / `hil_timeout` |
| 3 | Build context | `ContextBuilder.build_async()` → `ExecutionContext` with SessionState sections, prompt template, grounding metadata | Falls through on failure |
| 4 | Instantiate provider | `ProviderFactory.create(provider_config)` — dispatches to handler by `provider_type` | Exception |
| 5 | Execute via CB | `CircuitBreaker.call(provider.execute, ...)` with retry strategy (max 2 retries) | `circuit_breaker_open` / retry exhaustion |
| 6 | Validate output | `OutputValidationPipeline` — 3-tier: structural → schema → semantic | `output_validation_failed` |
| 7 | Emit completed/failed | `k1.capability.completed.v1` or `k1.capability.failed.v1` | Non-blocking |
| 8 | Update metrics | `CapabilityRegistry.update_metrics(name, latency_ms, success)` with EMA (alpha=0.3) | Fault-isolated |
| 9 | Emit learning | `k1.fabric.learning.signal.v1` | Non-blocking |

`execute_batch()` supports 3 strategies: PARALLEL (`asyncio.gather`), SEQUENTIAL (one-by-one), DAG (Kahn wave execution with `_depends_on` references).

**B. `Fabric` — the container/dataclass (line 1643)**

```python
@dataclass
class Fabric:
    facade: CapabilityFabric        # execution engine
    retrieval: FabricRetrieval      # discovery API
    registry_api: CapabilityRegistryAPI  # registry management
    registry: Any                   # raw CapabilityRegistry
    module_loader: Any              # ModuleLoader
    health_checker: Any             # HealthChecker
    event_port: Any                 # IEventPort
    event_emitter: Optional[EventEmitter]
    gap_detector: Any               # ProactiveGapDetector
    context_builder: Any            # ContextBuilder
```

Convenience delegates: `execute()` → `facade.execute()`, `execute_batch()` → `facade.execute_batch()`, `discover_capabilities()` → `retrieval.discover_capabilities()`, `find_relevant_prompts()` → `retrieval.find_relevant_prompts()`, `register()`/`unregister()`/`lookup()` → `registry_api`.

**C. `FabricRetrieval` — discovery API (line 1421)**

Methods: `discover_capabilities(domain, intent, safety_band, session_context, top_k)` → `RetrievalResult`, `find_relevant_prompts(intent, domain, safety_band, top_k)` → `RetrievalResult`, `describe_capabilities()` → `list[dict]`.

**D. `CapabilityRegistryAPI` — registry facade (line 1521)**

Methods: `register()`, `unregister()`, `lookup(name, version)`, `contains()`, `list_all()`, `list_by_domain()`, `list_by_type()`, `update_availability()`, `update_metrics()`, `reload()`, `health()`.

---

#### 1.2 Ground Reality — Full Module Structure

```
k1/fabric/
├── fabric.py                  # CapabilityFabric, Fabric, FabricRetrieval, BatchStrategy
├── factory.py                 # FabricFactory (4 entry points)
├── manifest_translator.py     # ToolDefinition → CapabilityContract
├── types.py                   # CapabilityContract, InputSpec, SafetyBand, etc.
├── logging.py, metrics.py     # Logging + Prometheus metrics
│
├── adapters/                  # 18 files — hexagonal ports
│   ├── sessionstate_reader.py # ISessionStateReader → SSM
│   ├── bridge_connection.py   # IBridgePort → Bridge client (LOCAL COLD fallback)
│   ├── event_port_prod.py     # IEventPort → IBus
│   ├── delta_bus_prod.py      # IDeltaBusPort → IBus
│   ├── model_gateway_bridge.py # IModelGatewayPort → ModelHub (handle-based)
│   ├── prompt_system_prod.py  # IPromptSystemPort → YAML files
│   ├── auto_mcp_transport.py  # Auto-discovers MCP servers in k1/tools/mcp_servers/
│   ├── auto_wasm_runtime.py   # Auto-discovers WASM modules in k1/tools/wasm_modules/
│   └── null_state_reader.py   # NullSessionStateReaderAdapter (shared Fabric)
│
├── core/
│   └── registry.py            # CapabilityRegistry — in-memory dict indexes (NO FTS5)
│
├── provider_resolution/       # 5-step provider resolution chain
│   └── resolver.py            # Resolver: Registry → ProviderRegistry → PolicyEngine → Selector → Factory
│
├── providers/                 # Provider implementations
│   ├── native_tool_provider.py # NativeToolProvider — dispatches tool.{read|execute}.*
│   ├── mcp_provider.py        # MCPProvider
│   ├── wasm_provider.py       # WASMProvider
│   ├── bridge_provider.py     # BridgeProvider
│   ├── agent_provider.py      # AgentProvider (M3 stub)
│   ├── workflow_provider.py   # WorkflowProvider
│   └── concierge_provider.py  # ConciergeProvider
│
├── policy/                    # Policy engine (4 dimensions — Security, Affective, Cognitive, QoS)
├── retrieval/                 # RetrievalEngine (EmbeddingIndex → HardFilter → SoftRanker → TopKSelector)
├── circuit_breaker/           # CircuitBreaker (CLOSED→OPEN→HALF_OPEN state machine)
├── health/                    # HealthChecker + AvailabilityTracker
├── output_validation/         # OutputValidationPipeline (structural→schema→semantic)
├── context/                   # ContextBuilder (6-step, 128K ceiling)
├── contracts/                 # Contract parsers (tool, agent, prompt, workflow)
├── ports/                     # 6 Protocol definitions
├── concurrency/               # FabricDispatcher + TimeoutGuard
└── events/                    # Event definitions
```

---

#### 1.3 Ground Reality — ProviderFactory Handler Registry

7 handler constructors registered in `_register_provider_handlers()`:

| ProviderType | Handler | Required port deps |
|---|---|---|
| `MCP` | `MCPProvider` | `mcp_transport` |
| `WASM` | `WASMProvider` | `wasm_runtime` |
| `BRIDGE` | `BridgeProvider` | `bridge_port` |
| `AGENT` | `AgentProvider` | `context_builder`, `model_gateway_port`, `state_reader`, `delta_bus`, `registry`, `grounding_port` |
| `WORKFLOW` | `WorkflowProvider` | `workflow_registry`, `capability_lookup`, `orchestrator` |
| `CONCIERGE` | `ConciergeProvider` | `concierge_router` |
| `LOCAL_STUB` | `LocalStubProvider` | None |

Plus: `NativeToolProvider` registered separately at S8 via `bootstrap_family_tools()` → `register_provider_with_fabric()`. Provider type: `LOCAL`, provider id: `k1_native_tools`.

---

#### 1.4 Ground Reality — CapabilityRegistry (NO FTS5)

**File:** `k1/fabric/core/registry.py`

Uses in-memory Python dicts under `threading.RLock`:

| Index | Type | Purpose |
|---|---|---|
| `_by_name` | `dict[str, ContractUnion]` | O(1) exact name lookup |
| `_by_domain` | `dict[str, list[ContractUnion]]` | Inverted domain tag index |
| `_by_type` | `dict[str, list[ContractUnion]]` | Grouped by capability type prefix |
| `_by_provider` | `dict[str, list[ContractUnion]]` | Grouped by provider_id |
| `_by_version` | `dict[str, dict[str, ContractUnion]]` | name → {version_str → contract} |
| `_metadata_cache` | `dict[str, ContractMetadata]` | Hot cache: availability, latency, success rate |

**No SQLite FTS5 anywhere in the registry.** FTS5 exists only in the POC `GlobalProjectionStore`. The registry's semantic search goes through `RetrievalEngine` which has its own `EmbeddingIndex` (not FTS5).

**Version conflict resolution:** same name + same version → `VersionConflictError`; same name + newer compatible major → UPGRADE in-place; same name + different major → REGISTER BOTH as `name@major`.

---

#### 1.5 Ground Reality — How service.py Wires Fabric

**S3 (Tier 1 — Shared Fabric):**

```text
FabricFactory.create_shared(
    event_port=EventPortProdAdapter(bus),
    bridge=BridgeConnectionAdapter(client=bridge_client),
    model_gateway=ModelGatewayBridgeAdapter(hub=model_hub),
    prompt_system=PromptSystemProdAdapter(prompts_dir="k1/contracts/prompts"),
    delta_bus=DeltaBusProdAdapter(bus),
    state_reader=session_routing_reader,  # NullSSMShim for shared Fabric
    hil_port=hil_service,
)
```

SessionRoutingStateReader resolves `session_id → SSM` for multi-session use.

**S5 (Orchestrator → Fabric):**

```text
FabricGatewayAdapter(fabric=shared_fabric)
  → IFabricGatewayPort.execute() → Fabric.execute() → CapabilityFabric.execute()
```

**P3 (Per-session Fabric):**

```text
FabricFactory.create_with_ports(
    state_reader=SessionStateReaderAdapter(ssm, session_id),
    event_port=EventPortProdAdapter(session_bus),
    bridge=BridgeConnectionAdapter(client=bridge_client),
    model_gateway=ModelGatewayBridgeAdapter(hub=model_hub),
    prompt_system=shared_prompt_system,
    delta_bus=DeltaBusProdAdapter(session_bus),
    production_mode=True,
    hil_port=session_hil_service,
    capability_registry=shared_fabric.registry,  # reuses shared registry
)
```

**P3.1:** `NativeToolProvider` re-registered on per-session fabric (prevents `UnsupportedProviderTypeError: LOCAL`).

---

#### 1.6 Ground Reality — Test Coverage (113 files, full audit)

| # | Category | Files | Coverage quality |
|---|---|---|---|
| 1 | E2E tool tests | 9 | Real tools through native servers (calendar, weather, notes, recipes, date_calc, unit_convert, auto-discovery, batch composition, smoke) |
| 2 | Wiring/protocol contracts | 4 | YAML contract compliance, port interfaces, type roundtrips |
| 3 | Agent subsystem | 16 | Lifecycle FSM, AgentPool, AgentProvider, AgentComposer, meta-agent creation, schema validation, safety gates |
| 4 | Provider tests | 6 | MCP/WASM/Bridge/Workflow/Concierge/Agent providers, NativeToolProvider proof-of-path |
| 5 | Provider resolution | 4 | 5-step resolver chain, deterministic selection (FAB-10), ProviderRegistry |
| 6 | Policy/security | 7 | SecurityContext (FAB-06), AffectiveRouting, CognitiveLoadRouting, QoSIntegration, ToolScope (FAB-07) |
| 7 | Retrieval | 6 | EmbeddingIndex, HardFilter, SoftRanker (4-weight), TopKSelector, RetrievalEngine, 1K/10K benchmarks |
| 8 | Registry/versioning | 6 | Full CRUD, version conflicts, upgrades, multi-version, concurrent access, 1K/10K/100K benchmarks |
| 9 | Context builder | 6 | 6-step pipeline, ContextBudget 5-level compression, 128K ceiling (FAB-08), grounding invocation metadata |
| 10 | Adapters | 5 | All 6 production adapters + all test adapters, protocol conformance, capture, thread safety |
| 11 | Port interfaces | 2 | Protocol shapes, runtime_checkable, structural subtyping |
| 12 | Contract validation | 4 | 12 semantic rules + JSON Schema validation + all 4 parsers |
| 13 | Module loader | 2 | Lifecycle, hot-reload, scan, file tracking |
| 14 | Output validation | 3 | 3-tier pipeline, E2E through fabric.execute() |
| 15 | Circuit breaker | 3 | State machine, retry strategy, HALF_OPEN probe, E2E through fabric.execute() |
| 16 | Tier flow integration | 3 | LOW/MEDIUM/HIGH tier flows through fabric.execute() |
| 17 | Cross-subsystem | 2 | Registry→Resolution→Execution chain, ModuleLoader→Registry→Retrieval chain |
| 18 | Invariants | 5 | FAB-01 through FAB-13 — statelessness, no session write, no direct LLM, trace_id propagation, determinism |
| 19 | HIL | 4 | HIL gate in _execute_impl, ALLOW/ASK/DENY/TIMEOUT flows, factory hil_port threading |
| 20 | Health/availability | 2 | HealthChecker periodic loop, AvailabilityTracker, CB bidirectional integration |
| 21 | Concurrency | 1 | FabricDispatcher + TimeoutGuard |
| 22 | Misc/infrastructure | 8 | create_shared, execute_batch, model gateway bridge, manifest translator, prompt inventory, gap detection, specialist agent contracts |
| 23 | Performance/load | 6 | Context, overhead, registry, retrieval benchmarks + load testing |
| 24 | Observability | 2 | Prometheus metrics, structured logging |

**No-mock strategy:** All 113 files use real adapters (in-memory implementations), not `unittest.mock`. Test pattern: "ALL executions through `fabric.execute()` — NEVER direct provider access."

---

#### 1.7 Ground Reality — Complete Gaps (0 tests exist)

These Phase 1 target components have **zero** test coverage across the 113-file suite:

| Component | Search result |
|---|---|
| `resolve_situation` | 0 matches |
| `PolicySelector` (distinct from `PolicyEngine`) | 0 matches |
| `IdempotencyStore` | 0 matches |
| `VerificationPlanRunner` | 0 matches |
| `GlobalProjectionStore` / `LocalProjectionStore` | 0 matches |
| Connector constitution (`ConnectorConstitution`) | 0 matches |

**Partially covered:** `PolicyEngine` has dedicated tests for all 4 dimensions but no `PolicySelector` abstraction. `BridgeConnectionAdapter` tested with `InMemoryBridgeClient` but no real K0 bridge E2E. `RetrievalEngine` uses zero-vector stub for `EmbeddingPort`.

---

#### 1.8 Complete Fabric Component Inventory

**EXISTING components (already in code):**

| Component | File | Status |
|---|---|---|
| `CapabilityFabric` | `k1/fabric/fabric.py:190` | Production — 9-step pipeline, batch, DAG |
| `Fabric` (container) | `k1/fabric/fabric.py:1643` | Production — @dataclass, delegates |
| `FabricRetrieval` | `k1/fabric/fabric.py:1421` | Production — discover, find_prompts, describe |
| `CapabilityRegistryAPI` | `k1/fabric/fabric.py:1521` | Production — CRUD facade |
| `CapabilityRegistry` | `k1/fabric/core/registry.py` | Production — 6 in-memory indexes, versioning |
| `FabricFactory` | `k1/fabric/factory.py` | Production — 4 entry points |
| `Resolver` (5-step) | `k1/fabric/provider_resolution/resolver.py` | Production — registry→provider→policy→select→create |
| `ProviderFactory` | `k1/fabric/provider_resolution/` | Production — 7 handler constructors |
| `ProviderRegistry` | `k1/fabric/provider_resolution/` | Production — register/unregister/health |
| `ProviderMatcher` | `k1/fabric/provider_resolution/` | Production — match + health filter |
| `ProviderSelector` | `k1/fabric/provider_resolution/` | Production — deterministic tie-breaking |
| `PolicyEngine` (4 dim) | `k1/fabric/policy/` | Production — Security, Affective, Cognitive, QoS |
| `SecurityContext` | `k1/fabric/policy/` | Production — band-based authorization |
| `ToolScope` | `k1/fabric/policy/` | Production — sub-agent scoping |
| `RetrievalEngine` | `k1/fabric/retrieval/` | Production — EmbeddingIndex→HardFilter→SoftRanker→TopK |
| `ContextBuilder` | `k1/fabric/context/` | Production — 6-step, 128K ceiling |
| `CircuitBreaker` | `k1/fabric/circuit_breaker/breaker.py` | Production — CLOSED/OPEN/HALF_OPEN |
| `HealthChecker` | `k1/fabric/health/health_checker.py` | Production — periodic + CB bidirectional |
| `AvailabilityTracker` | `k1/fabric/health/` | Production — state tracking |
| `OutputValidationPipeline` | `k1/fabric/output_validation/` | Production — structural→schema→semantic |
| `ContractValidator` | `k1/fabric/contracts/` | Production — 12 semantic rules + JSON Schema |
| `ModuleLoader` | `k1/fabric/module_registry/` | Production — hot-reload, scan |
| `ManifestTranslator` | `k1/fabric/manifest_translator.py` | Production — ActionSpec→CapabilityContract |
| `FabricDispatcher` | `k1/fabric/concurrency/` | Production — async bounded parallelism |
| `TimeoutGuard` | `k1/fabric/concurrency/` | Production — deadline enforcement |
| `EventEmitter` | `k1/fabric/events/` | Production — capability lifecycle events |
| `FabricMetrics` | `k1/fabric/metrics.py` | Production — Prometheus |
| 6 production adapters | `k1/fabric/adapters/` | Production — SS reader, Bridge, Event, Delta, Model GW, Prompt |
| `NativeToolProvider` | `k1/fabric/providers/native_tool_provider.py` | Production — LOCAL provider |
| `MCPProvider` | `k1/fabric/providers/mcp_provider.py` | Production |
| `WASMProvider` | `k1/fabric/providers/wasm_provider.py` | Production |
| `BridgeProvider` | `k1/fabric/providers/bridge_provider.py` | Production |
| `AgentProvider` | `k1/fabric/providers/agent_provider.py` | M3 stub |
| `WorkflowProvider` | `k1/fabric/providers/workflow_provider.py` | Partial |
| `ConciergeProvider` | `k1/fabric/providers/concierge_provider.py` | Partial |

**NEW components (need to be built in Phase 1):**

| Component | Target location | Source | Purpose |
|---|---|---|---|
| `GlobalProjectionStore` | `k1/fabric/stores/global_projection_store.py` | Promote from `poc/back_tool_contract_v2/` | Connectors, capabilities (FTS5), resource_kinds, connector_constitutions |
| `LocalProjectionStore` | `k1/fabric/stores/local_projection_store.py` | Promote from `poc/back_tool_contract_v2/` | connected_resources, household_members, alias_index, resource_projection_snapshots |
| `IdempotencyStore` | `k1/fabric/stores/idempotency_store.py` | Promote from `poc/back_tool_contract_v2/` | in_flight→succeeded/failed state machine, immutable-succeeded invariant |
| `SituatedResolver` | `k1/fabric/resolver/situated_resolver.py` | Promote from `poc/back_tool_contract_v2/resolve_situation.py` | 10-verdict state machine, CC-1 contract (ResolveSituationRequest→ResolutionEnvelope) |
| `PolicySelector` | `k1/fabric/policy/selector.py` | New — Contract C implementation | PolicySelectionRequest→PolicyBundle with gates[], hil_triggers[], verifier_requirements[], policy_cards[], guide_selection_rules[] |
| `VerificationPlanRunner` | `k1/fabric/verification/runner.py` | Promote from `poc/back_tool_contract_v2/verification_runner.py` | build_plan→run→gate, read_after_write, output_schema |
| `ConnectorConstitution` (schema + loader) | `k1/fabric/constitution/` | New — Constitution Tooling spec | ConstitutionArtifact shape, per-connector preconditions, companion resources, conflict rules, HIL gates, verifier requirements |
| `PromptPackBuilder` | `k1/fabric/prompt_pack/` | New — Contract G implementation | Renders compact cards from resolution: connector_constitution_cards[], tool_name_cards[], policy_cards[], guide_cards[], selected_schema_cards[], allowed_tool_calls[], forbidden_tool_calls[] |
| `CapabilityNameParser` | `k1/fabric/resolver/name_parser.py` | New — Contract D enforcement | Parse `tool.{read\|execute}.{connector_id}.{action}`, extract connector_id |
| `ConnectorAliasNormalizer` | `k1/fabric/stores/alias_normalizer.py` | Promote from POC alias logic | Maps user-facing names ("Google Calendar")→connector_id |

**BRIDGE components (Phase 1 — connector gateway):**

| Component | File | Status |
|---|---|---|
| `ConnectorGateway` | `bridge/connector/gateway.py` | Production — 3-stage pipeline |
| `TokenVerifier` | `bridge/connector/token_verifier.py` | Production |
| `AdapterVerifier` | `bridge/connector/adapter_verifier.py` | Production |
| `RequestRouter` | `bridge/connector/request_router.py` | Production |
| `CredentialVault` | `bridge/connector/credential_vault.py` | Production (Protocol + InMemory) |
| `KeyringVault` | `bridge/connector/vault/keyring_vault.py` | Production (Windows DPAPI) |
| `MCPProcessManager` | `bridge/connector/mcp_process_manager.py` | Production |
| `RealMCPProcessManager` | `bridge/connector/real_mcp_process_manager.py` | Production |
| `CrashBudget` | `bridge/connector/crash_budget.py` | Production |
| `Signing` | `bridge/core/signing.py` | Production (Ed25519) |
| `LocalOutbox` | `bridge/sync/local_outbox.py` | Production (SQLite WAL) |

---

#### 1.9 New Tests Required (GATE-P1)

```text
GAP-P1-001: SituatedResolver unit tests
  File: tests/k1/fabric/resolver/test_situated_resolver.py
  Covers: 10 verdicts with sub-reason distinctions, ResolutionEnvelope shape,
    CC-1 contract compliance, disclosure phases
  Source: poc/back_tool_contract_v2/resolve_situation.py

GAP-P1-002: PolicySelector contract tests
  File: tests/k1/fabric/policy/test_policy_selector.py
  Covers: PolicySelectionRequest→PolicyBundle, gates[], hil_triggers[],
    verifier_requirements[], policy_cards[], guide_selection_rules[],
    policy vs constitution precedence (policy may tighten, not relax)
  Source: Contract C in whiteboard

GAP-P1-003: GlobalProjectionStore integration tests
  File: tests/k1/fabric/stores/test_global_projection_store.py
  Covers: connector registration, capability FTS5 indexing (content-sync,
    delete-all before bulk insert), constitution storage, alias normalization,
    resource_kinds table, connector_constitutions table
  Source: poc/back_tool_contract_v2/global_projection_store.py

GAP-P1-004: LocalProjectionStore integration tests
  File: tests/k1/fabric/stores/test_local_projection_store.py
  Covers: connected_resources, household_members, alias_index,
    resource_projection_snapshots, freshness tracking, completeness states
  Source: poc/back_tool_contract_v2/local_projection_store.py

GAP-P1-005: IdempotencyStore contract tests
  File: tests/k1/fabric/stores/test_idempotency_store.py
  Covers: in_flight→succeeded transition, in_flight→failed transition,
    immutable-succeeded invariant (replay cannot change succeeded),
    concurrent access, TTL cleanup
  Source: poc/back_tool_contract_v2/idempotency_store.py

GAP-P1-006: VerificationPlanRunner contract tests
  File: tests/k1/fabric/verification/test_verification_runner.py
  Covers: build_plan→run→gate, read_after_write verification,
    output_schema verification, deferred methods (state_compare, audit_receipt,
    external_receipt, policy_attestation)
  Source: poc/back_tool_contract_v2/verification_runner.py

GAP-P1-007: Bridge ConnectorGateway integration tests
  File: tests/bridge/connector/test_gateway_integration.py
  Covers: full 3-stage pipeline (token verify→adapter verify→route) with
    real NativeToolProvider dispatch

GAP-P1-008: ConnectorConstitution schema + loader tests
  File: tests/k1/fabric/constitution/test_constitution_schema.py
  Covers: ConstitutionArtifact JSON Schema, preconditions, companion_resource
    roles, conflict_analysis_rules[], mutation_sequencing[], hil_gates[],
    verification_requirements[], versioning, Principle 6 enforcement
  Source: Constitution Tooling section in whiteboard
  **Designed:** 5 test classes, 23 test methods — see Component 7 §7.7
  Classes: TestConstitutionSchemaValidation (7), TestSemanticRules (6),
    TestConstitutionLoader (7), TestVersionCompatibility (3),
    TestPrinciple6Enforcement (3)

GAP-P1-009: Negative proof — SituatedResolver failure modes
  File: tests/k1/fabric/resolver/test_situated_resolver_negative.py
  Covers: missing_capability, blocked_by_policy, incomplete_world_projection,
    stale_projection, cannot_execute verdicts with sub-reasons

GAP-P1-010: Negative proof — Bridge security boundary
  File: tests/bridge/connector/test_security_boundary_negative.py
  Covers: invalid token→denied, unsigned adapter→rejected,
    credential leak attempt→blocked, band escalation attempt→denied

GAP-P1-011: PromptPackBuilder contract tests
  File: tests/k1/fabric/prompt_pack/test_prompt_pack_builder.py
  Covers: PromptPack shape (Contract G), compact card rendering,
    staged disclosure (Phase 1: constitution+names, Phase 2: schemas only
    after commitment), allowed_tool_calls[], forbidden_tool_calls[],
    redaction_summary, stale_card_policy
  **Designed:** 10 test classes, 43 test methods — see Component 8 §8.8
  Classes: TestPromptPackShape (4), TestStagedDisclosure (8),
    TestRedactionProof (8), TestConstitutionCards (5), TestToolNameCards (4),
    TestPolicyCards (4), TestStaleCardPolicy (5), TestForbiddenActionGating (4),
    TestRendering (7), TestPromptPackBuilderEdgeCases (6)

GAP-P1-012: CapabilityNameParser unit tests
  File: tests/k1/fabric/resolver/test_capability_name_parser.py
  Covers: parse (13 cases — valid names, malformed names, boundary cases),
    try_parse, validate, extract (connector_id, action, operation_type),
    build (construction + roundtrip), domain queries (is_read, is_write,
    belongs_to_connector), bulk operations (filter_by_connector,
    group_by_connector, connectors_in_scope)
  **Designed:** 7 test classes, 35 test methods — see Component 9 §9.7
  Classes: TestParse (13), TestTryParse (2), TestValidate (4),
    TestExtract (4), TestBuild (5), TestDomainQueries (5),
    TestBulkOperations (6)

GAP-P1-013: ConnectorAliasNormalizer unit tests
  File: tests/k1/fabric/stores/test_alias_normalizer.py
  Covers: global alias resolution (8 cases), local alias resolution (4),
    confidence scoring (4), batch normalization (3), reverse lookup (4),
    global index rebuild (3), ambiguity detection (4),
    integration with LocalProjectionStore (2)
  **Designed:** 8 test classes, 28 test methods — see Component 10 §10.6
  Classes: TestGlobalAliasResolution (8), TestLocalAliasResolution (4),
    TestConfidenceScoring (4), TestBatchNormalization (3),
    TestReverseLookup (4), TestGlobalIndexRebuild (3),
    TestAmbiguity (4), TestIntegrationWithLocalStore (2)
```

#### 1.10 Implementation Plan

```text
Step 1.1: Create k1/fabric/stores/ — projection + idempotency
  Promote from POC:
    poc/back_tool_contract_v2/global_projection_store.py → k1/fabric/stores/global_projection_store.py
    poc/back_tool_contract_v2/local_projection_store.py → k1/fabric/stores/local_projection_store.py
    poc/back_tool_contract_v2/idempotency_store.py → k1/fabric/stores/idempotency_store.py
  Wire into FabricFactory.create_shared() at S3 (passed to Fabric container)
  Write GAP-P1-003, GAP-P1-004, GAP-P1-005

Step 1.2: Create k1/fabric/resolver/ — situated resolution
  Promote: poc/back_tool_contract_v2/resolve_situation.py → k1/fabric/resolver/situated_resolver.py
  Implement CC-1 contract: ResolveSituationRequest→ResolutionEnvelope
  Implement 10-verdict state machine with sub-reason distinctions
  Wire resolve_situation as a Fabric meta-tool (registered alongside invoke_capability)
  Write GAP-P1-001, GAP-P1-009

Step 1.3: Create k1/fabric/policy/selector.py — PolicySelector
  New implementation of Contract C: PolicySelectionRequest→PolicyBundle
  Consumes connector constitutions + actor scope + safety context
  Returns gates[], hil_triggers[], verifier_requirements[], policy_cards[],
    guide_selection_rules[]
  Distinct from existing PolicyEngine (which is about provider selection policy,
    not about execution policy for Back)
  Write GAP-P1-002

Step 1.4: Create k1/fabric/verification/ — VerificationPlanRunner
  Promote: poc/back_tool_contract_v2/verification_runner.py → k1/fabric/verification/runner.py
  Implement read_after_write, output_schema (proven in POC)
  Wire into Fabric's post-invoke pipeline (after step 6, before step 7)
  Write GAP-P1-006

Step 1.5: Create k1/fabric/constitution/ — ConnectorConstitution
  New: ConstitutionArtifact schema (JSON Schema)
  New: ConstitutionLoader — loads from connector_constitutions table
  Implements 6 Principles from Constitution Tooling section
  Write GAP-P1-008

Step 1.6: Create k1/fabric/prompt_pack/ — PromptPackBuilder
  New: PromptPackBuilder — renders Contract G PromptPack from resolution
  Implements staged disclosure (CC-10): Phase 1=constitution+names, Phase 2=schemas after commitment
  Implements allowed_tool_calls[], forbidden_tool_calls[], redaction_summary
  Write GAP-P1-011

Step 1.6a: Create k1/fabric/resolver/name_parser.py — CapabilityNameParser
  New: CapabilityNameParser — validates and parses tool.{read|execute}.{connector_id}.{action}
  Enforces Contract D naming convention: capability names embed connector identity
  Used by: CapabilityBinder, PolicySelector, VerificationPlanRunner, PromptPackBuilder,
    NativeToolProvider, CapabilityRegistry (registration validation)
  Write GAP-P1-012

Step 1.6b: Create k1/fabric/stores/alias_normalizer.py — ConnectorAliasNormalizer
  New: ConnectorAliasNormalizer — maps user-facing names → connector_id
  Two scopes: global (connector catalog LABELS) + local (per-household resource aliases)
  Used by: RequestFrameBuilder, ResolveResourcesService, SituatedResolver, Back prompt builder
  Write GAP-P1-013

Step 1.7: Redesign family tool schemas
  Add ConnectorConstitution to each adapter (calendar, tasks, reminders, chores, shopping)
  Upgrade ActionSpec→full JSON Schema input/output
  Add verifier affordances, side-effect declarations, freshness guarantees
  Existing 51 family tool tests continue passing — schemas are additive

Step 1.8: Bridge gateway hardening
  Audit ConnectorGateway 3-stage pipeline against CC-6 contract
  Ensure TokenVerifier checks user_band >= safety_band
  Ensure AdapterVerifier checks FamilyOS CA signature + revocation
  Write GAP-P1-007, GAP-P1-010

Step 1.9: Integration gate
  Run GATE-P1 checklist (14 items in roadmap §0D)
  Run ALL 113 existing fabric tests — must all pass
  Run ALL 48 existing bridge tests — must all pass
  Run ALL 51 existing family tools tests — must all pass
  Run ALL 11 existing HIL tests — must all pass
  Run new tests (GAP-P1-001 through GAP-P1-011)
  Benchmark: rerun scripts/probe_back_tool_contract_benchmark.py — must match POC results
```

**Files to create:**

```text
k1/fabric/stores/__init__.py
k1/fabric/stores/global_projection_store.py       (promoted from POC)
k1/fabric/stores/local_projection_store.py        (promoted from POC)
k1/fabric/stores/idempotency_store.py             (promoted from POC)
k1/fabric/stores/alias_normalizer.py              (promoted from POC alias logic)
k1/fabric/resolver/__init__.py
k1/fabric/resolver/situated_resolver.py           (promoted from POC resolve_situation.py)
k1/fabric/resolver/name_parser.py                 (new — capability name parsing)
k1/fabric/policy/selector.py                      (new — Contract C)
k1/fabric/verification/__init__.py
k1/fabric/verification/runner.py                  (promoted from POC verification_runner.py)
k1/fabric/constitution/__init__.py
k1/fabric/constitution/schema.py                  (new — ConstitutionArtifact JSON Schema)
k1/fabric/constitution/loader.py                  (new — loads from projection store)
k1/fabric/prompt_pack/__init__.py
k1/fabric/prompt_pack/builder.py                  (new — Contract G PromptPack)
tests/k1/fabric/resolver/test_situated_resolver.py
tests/k1/fabric/resolver/test_situated_resolver_negative.py
tests/k1/fabric/policy/test_policy_selector.py
tests/k1/fabric/stores/test_global_projection_store.py
tests/k1/fabric/stores/test_local_projection_store.py
tests/k1/fabric/stores/test_idempotency_store.py
tests/k1/fabric/verification/test_verification_runner.py
tests/k1/fabric/constitution/test_constitution_schema.py
tests/k1/fabric/prompt_pack/test_prompt_pack_builder.py
tests/bridge/connector/test_gateway_integration.py
tests/bridge/connector/test_security_boundary_negative.py
```

**Files to modify:**

```text
k1/fabric/factory.py                              (wire stores, resolver, policy selector, verification, constitution, prompt pack)
k1/fabric/fabric.py                               (register resolve_situation meta-tool, add new container fields)
k1/fabric/providers/native_tool_provider.py       (consume new schemas + constitutions)
k1/tools/family/calendar/service.py               (add constitution + upgraded JSON Schema)
k1/tools/family/tasks/service.py                  (add constitution + upgraded JSON Schema)
k1/tools/family/reminders/service.py              (add constitution + upgraded JSON Schema)
k1/tools/family/chores/service.py                 (add constitution + upgraded JSON Schema)
k1/tools/family/shopping/service.py               (add constitution + upgraded JSON Schema)
k1/kernel/service.py                              (wire new stores at S3, pass to P3)
```

---

## Phase 1 Component Designs

> **Status:** sequential design — each component designed one at a time, with full API, internal design, wiring, and E2E data flow. Components are designed in dependency order: stores first, then resolver, then policy, then verification, then constitution, then prompt pack.

---

### Component 1 — GlobalProjectionStore

**Target file:** `k1/fabric/stores/global_projection_store.py`
**Source:** Promote + harden from `poc/back_tool_contract_v2/stores/global_projection_store.py`
**Depends on:** Nothing (foundation component — stores are the bottom layer)

#### 1.1 What It Is

The single source of truth for ALL connectors, capabilities, resource kinds, and connector constitutions known to the kernel. This is the "what tools exist in the universe" store. It is GLOBAL — shared across all sessions, read by the resolver, written by manifest ingestion.

In the current code, `CapabilityRegistry` (`k1/fabric/core/registry.py`) holds capabilities in in-memory Python dicts. That works for the current scale (41 family tools) but has no persistence, no FTS5, no constitution storage, and no connector-level grouping. `GlobalProjectionStore` replaces the registry's storage layer while the registry keeps its in-memory hot cache.

#### 1.2 SQL Schema (5 tables + 1 FTS5 content table)

```sql
-- Connectors: one row per registered connector/adapter
CREATE TABLE IF NOT EXISTS connectors (
    connector_id    TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    connector_type  TEXT NOT NULL,   -- 'native', 'bridge', 'ifl'
    provider_type   TEXT NOT NULL,   -- 'LOCAL', 'MCP', 'BRIDGE', etc.
    version         TEXT NOT NULL DEFAULT '1.0.0',
    admission_verdict TEXT NOT NULL, -- 'admitted', 'pending', 'rejected'
    registration_type TEXT NOT NULL, -- 'static', 'dynamic', 'discovered'
    constitution_json TEXT NOT NULL DEFAULT '{}',
    policy_json     TEXT NOT NULL DEFAULT '{}',
    resource_kinds_json TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Capabilities: one row per capability contract
CREATE TABLE IF NOT EXISTS capabilities (
    capability_name TEXT PRIMARY KEY,
    connector_id    TEXT NOT NULL REFERENCES connectors(connector_id),
    operation       TEXT NOT NULL,   -- 'read', 'execute'
    effect          TEXT NOT NULL,   -- 'read', 'write', 'delete', 'compute'
    resource_kind   TEXT,
    description     TEXT NOT NULL DEFAULT '',
    required_inputs_json TEXT NOT NULL DEFAULT '[]',
    optional_inputs_json TEXT NOT NULL DEFAULT '[]',
    output_schema_ref   TEXT,
    safety_band_min TEXT NOT NULL DEFAULT 'GREEN',
    risk_class      TEXT NOT NULL DEFAULT 'benign',
    idempotency     TEXT,            -- 'safe', 'unsafe', NULL
    compensation_capability TEXT,
    record_type     TEXT NOT NULL,   -- 'executable_capability', 'activity_profile', 'workflow', 'agent'
    created_at      TEXT NOT NULL,
    contract_json   TEXT NOT NULL,   -- full CapabilityContract serialized
    synthetic       INTEGER NOT NULL DEFAULT 0  -- 1 = generated at scale, 0 = real
);

-- FTS5 content table for full-text search over capabilities
CREATE VIRTUAL TABLE IF NOT EXISTS capabilities_fts USING fts5(
    capability_name,
    description,
    resource_kind,
    connector_id,
    content='capabilities',
    content_rowid='rowid'
);

-- Resource kinds: the types of resources connectors manage
CREATE TABLE IF NOT EXISTS resource_kinds (
    kind_id         TEXT PRIMARY KEY, -- e.g., 'calendar.event', 'task.item'
    connector_id    TEXT NOT NULL REFERENCES connectors(connector_id),
    label           TEXT NOT NULL,
    schema_json     TEXT NOT NULL DEFAULT '{}',
    verifier_affordances_json TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL
);

-- Connector constitutions: extracted from connectors.constitution_json
-- for direct access without JSON parsing
CREATE TABLE IF NOT EXISTS connector_constitutions (
    connector_id        TEXT PRIMARY KEY REFERENCES connectors(connector_id),
    constitution_id     TEXT NOT NULL,
    schema_version      TEXT NOT NULL DEFAULT '1.0.0',
    authored_by         TEXT,
    authored_at         TEXT,
    last_proven_at      TEXT,
    execution_phases_json       TEXT NOT NULL DEFAULT '[]',
    prerequisite_reads_json     TEXT NOT NULL DEFAULT '[]',
    conflict_analysis_rules_json TEXT NOT NULL DEFAULT '[]',
    hil_gates_json              TEXT NOT NULL DEFAULT '[]',
    mutation_sequencing_json    TEXT NOT NULL DEFAULT '[]',
    verification_requirements_json TEXT NOT NULL DEFAULT '[]',
    companion_resource_roles_json  TEXT NOT NULL DEFAULT '[]',
    precondition_summary        TEXT,
    companion_resource_summary  TEXT,
    hil_trigger_summary         TEXT,
    degradation_policy          TEXT
);
```

#### 1.3 Public API

```python
class GlobalProjectionStore:
    """Single source of truth for all connectors, capabilities, resource kinds,
    and constitutions. SQLite WAL. Shared across sessions."""

    # ── Lifecycle ──────────────────────────────────────────
    def __init__(self, db_path: str | Path) -> None: ...
    def open(self) -> None: ...
    def close(self) -> None: ...

    # ── Connector CRUD ─────────────────────────────────────
    def upsert_connector(self, connector: ConnectorRecord) -> None: ...
    def get_connector(self, connector_id: str) -> ConnectorRecord | None: ...
    def list_connectors(
        self, *, connector_type: str | None = None
    ) -> list[ConnectorRecord]: ...
    def delete_connector(self, connector_id: str) -> None: ...
    def connector_exists(self, connector_id: str) -> bool: ...

    # ── Capability CRUD ────────────────────────────────────
    def upsert_capability(self, capability: CapabilityRecord) -> None: ...
    def bulk_upsert_capabilities(
        self, capabilities: list[CapabilityRecord], *, chunk_size: int = 25_000
    ) -> None: ...
    def get_capability(self, capability_name: str) -> CapabilityRecord | None: ...
    def get_capabilities_by_connector(
        self, connector_id: str
    ) -> list[CapabilityRecord]: ...
    def delete_capability(self, capability_name: str) -> None: ...
    def capability_exists(self, capability_name: str) -> bool: ...
    def count_capabilities(self) -> int: ...

    # ── FTS5 Full-Text Search ──────────────────────────────
    def search_capabilities(
        self, query: str, *, top_k: int = 20, connector_ids: list[str] | None = None
    ) -> list[CapabilityRecord]: ...
    def search_capabilities_by_domain(
        self, query: str, domains: list[str], *, top_k: int = 20
    ) -> list[CapabilityRecord]: ...

    # ── Resource Kinds ─────────────────────────────────────
    def upsert_resource_kind(self, kind: ResourceKindRecord) -> None: ...
    def get_resource_kinds_by_connector(
        self, connector_id: str
    ) -> list[ResourceKindRecord]: ...
    def get_resource_kind(self, kind_id: str) -> ResourceKindRecord | None: ...

    # ── Connector Constitutions ─────────────────────────────
    def upsert_constitution(
        self, constitution: ConstitutionRecord
    ) -> None: ...
    def get_constitution(
        self, connector_id: str
    ) -> ConstitutionRecord | None: ...
    def list_constitutions(self) -> list[ConstitutionRecord]: ...

    # ── Bulk Operations ────────────────────────────────────
    def load_from_manifest_batch(
        self, batch: CapabilityRegistrationBatch
    ) -> LoadResult: ...
    def rebuild_fts_index(self) -> None: ...
```

#### 1.4 Internal Design

**FTS5 content-sync model:** Capabilities table is the content source for the FTS5 virtual table. On every upsert, a trigger inserts `'rebuild'` into `capabilities_fts`. Before bulk loads, `'delete-all'` is inserted. After bulk loads, `rebuild_fts_index()` runs a full rebuild. This is the proven POC approach — it handles 100K+ capabilities at <1ms indexed lookup.

**Thread safety:** SQLite WAL mode + `check_same_thread=False`. Write operations are serialized by SQLite's internal locking. The store does NOT add its own mutex — Fabric already serializes registry writes through `CapabilityRegistryAPI`.

**JSON columns:** `constitution_json`, `policy_json`, `resource_kinds_json`, `required_inputs_json`, `optional_inputs_json`, `contract_json`, and all `*_json` columns on `connector_constitutions` are stored as TEXT with `json.dumps(sort_keys=True)`. Python-side they are dicts/lists. Serialization happens in the store, not at the call site.

**`record_type` enumeration on capabilities:** `'executable_capability'`, `'activity_profile'`, `'workflow'`, `'agent'`. This maps to BTC-001 fix — the resolver can filter to only `'executable_capability'` when building the CandidateUniverse.

**`synthetic` flag:** `1` = generated at scale for benchmarking (POC 100K test). `0` = real connector capability. The resolver MAY deprioritize synthetic records but must not filter them out — some benchmarks need them.

#### 1.5 Wiring — Where It Hooks Into service.py

**S3 (shared Fabric creation):**

```text
# Before S3: create the store
global_store = GlobalProjectionStore(db_path="./data/global_projection.db")
global_store.open()

# S3: pass to FabricFactory
self._shared_fabric = FabricFactory.create_shared(
    ...,
    global_projection_store=global_store,
)
```

**FabricFactory modification:** `create_shared()` and `create_with_ports()` accept optional `global_projection_store: GlobalProjectionStore | None = None`. If provided, it's stored on the `Fabric` dataclass as `fabric.global_projection_store`.

**S8 (family tools bootstrap):** After `bootstrap_family_tools()` registers capabilities in the in-memory `CapabilityRegistry`, the same capabilities are bulk-inserted into `GlobalProjectionStore`:

```text
# After ManifestTranslator registers contracts in CapabilityRegistry:
capability_records = [
    CapabilityRecord.from_contract(c) for c in registry.list_all()
]
global_store.bulk_upsert_capabilities(capability_records)
global_store.rebuild_fts_index()
```

**P3 (per-session Fabric):** Per-session Fabric gets a reference to the SAME `GlobalProjectionStore` instance — it is shared, not copied. `FabricFactory.create_with_ports()` receives `global_projection_store=shared_fabric.global_projection_store`.

**Shutdown (reverse S3):** During `KernelService.shutdown()`, after `shared_fabric.shutdown()`:

```text
if global_store is not None:
    global_store.close()
```

#### 1.6 E2E Data Flow

```text
┌─────────────────────────────────────────────────────────────┐
│ BOOT: KernelService._startup_tier1()                        │
│                                                             │
│  Before S3:                                                 │
│    GlobalProjectionStore(db_path).open()                    │
│                                                             │
│  S3:                                                        │
│    FabricFactory.create_shared(                             │
│      global_projection_store=global_store,                  │
│      ...                                                    │
│    )                                                        │
│    → fabric.global_projection_store = global_store          │
│                                                             │
│  S8:                                                        │
│    bootstrap_family_tools(fabric)                           │
│    → ManifestTranslator registers contracts in Registry     │
│    → global_store.bulk_upsert_capabilities(records)         │
│    → global_store.rebuild_fts_index()                       │
│    → global_store.upsert_connector(calendar_connector)      │
│    → global_store.upsert_constitution(calendar_constitution) │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ RUNTIME: SituatedResolver.resolve()                         │
│                                                             │
│  1. resolver receives ResolveSituationRequest               │
│  2. Calls global_store.get_connector(connector_id)          │
│     → returns ConnectorRecord with resource_kinds,          │
│       constitution_json, policy_json                        │
│  3. Calls global_store.get_constitution(connector_id)       │
│     → returns ConstitutionRecord with preconditions,        │
│       companion_resource_roles, hil_gates, verifiers        │
│  4. Calls global_store.get_capabilities_by_connector(cid)   │
│     → returns all executable_capability records for this    │
│       connector (filtered: record_type='executable')        │
│  5. Calls global_store.get_resource_kinds_by_connector(cid) │
│     → returns resource kind definitions                    │
│  6. Builds CandidateUniverse from all of the above          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ COLD DISCOVERY: discover_capabilities (legacy catalog path) │
│                                                             │
│  1. Calls global_store.search_capabilities(intent, top_k)   │
│     → FTS5 full-text search over capabilities table         │
│  2. Returns catalog results with catalog_only marker        │
│  3. No execution authority — record_type preserved          │
└─────────────────────────────────────────────────────────────┘
```

#### 1.7 Record Types (Python dataclasses)

```python
@dataclass
class ConnectorRecord:
    connector_id: str
    label: str
    connector_type: str       # 'native' | 'bridge' | 'ifl'
    provider_type: str        # 'LOCAL' | 'MCP' | 'BRIDGE' | ...
    version: str
    admission_verdict: str    # 'admitted' | 'pending' | 'rejected'
    registration_type: str    # 'static' | 'dynamic' | 'discovered'
    constitution: dict        # parsed from constitution_json
    policy_declarations: dict # parsed from policy_json
    resource_kinds: list[str] # parsed from resource_kinds_json
    created_at: str
    updated_at: str

@dataclass
class CapabilityRecord:
    capability_name: str
    connector_id: str
    operation: str            # 'read' | 'execute'
    effect: str               # 'read' | 'write' | 'delete' | 'compute'
    resource_kind: str | None
    description: str
    required_inputs: list[dict]
    optional_inputs: list[dict]
    output_schema_ref: str | None
    safety_band_min: str      # 'GREEN' | 'AMBER' | 'RED'
    risk_class: str           # 'benign' | 'safety_sensitive'
    idempotency: str | None   # 'safe' | 'unsafe'
    compensation_capability: str | None
    record_type: str          # 'executable_capability' | 'activity_profile' | 'workflow' | 'agent'
    created_at: str
    contract_json: dict       # full CapabilityContract
    synthetic: bool

@dataclass
class ResourceKindRecord:
    kind_id: str              # 'calendar.event', 'task.item', etc.
    connector_id: str
    label: str
    schema: dict
    verifier_affordances: list[str]

@dataclass
class ConstitutionRecord:
    connector_id: str
    constitution_id: str
    schema_version: str
    authored_by: str | None
    authored_at: str | None
    last_proven_at: str | None
    execution_phases: list[str]
    prerequisite_reads: list[dict]
    conflict_analysis_rules: list[dict]
    hil_gates: list[dict]
    mutation_sequencing: list[dict]
    verification_requirements: list[dict]
    companion_resource_roles: list[dict]
    precondition_summary: str | None
    companion_resource_summary: str | None
    hil_trigger_summary: str | None
    degradation_policy: str | None
```

#### 1.8 Test Coverage

```text
GAP-P1-003: GlobalProjectionStore integration tests
  File: tests/k1/fabric/stores/test_global_projection_store.py

  Test classes:
    TestGlobalProjectionStoreLifecycle
      - test_open_creates_db_and_schema
      - test_close_releases_connection
      - test_reopen_preserves_data

    TestConnectorCRUD
      - test_upsert_connector_insert
      - test_upsert_connector_update
      - test_get_connector_exists
      - test_get_connector_missing_returns_none
      - test_list_connectors_all
      - test_list_connectors_filter_by_type
      - test_delete_connector
      - test_delete_connector_cascades_to_capabilities
      - test_connector_exists

    TestCapabilityCRUD
      - test_upsert_capability_insert
      - test_upsert_capability_update
      - test_get_capability_exists
      - test_get_capability_missing_returns_none
      - test_get_capabilities_by_connector
      - test_delete_capability
      - test_bulk_upsert_capabilities_10k
      - test_count_capabilities

    TestFTSSearch
      - test_search_capabilities_exact_match
      - test_search_capabilities_partial_match
      - test_search_capabilities_no_results
      - test_search_capabilities_filtered_by_connector
      - test_search_capabilities_by_domain
      - test_fts_rebuild_after_bulk_load

    TestResourceKinds
      - test_upsert_resource_kind
      - test_get_resource_kinds_by_connector
      - test_get_resource_kind

    TestConstitutionCRUD
      - test_upsert_constitution
      - test_get_constitution
      - test_constitution_json_roundtrip
      - test_list_constitutions

    TestScale
      - test_bulk_load_100k_capabilities
      - test_search_100k_under_5ms
      - test_concurrent_readers_during_bulk_load
```

---

### Component 2 — LocalProjectionStore

**Target file:** `k1/fabric/stores/local_projection_store.py`
**Source:** Promote + harden from `poc/back_tool_contract_v2/stores/local_projection_store.py`
**Depends on:** `GlobalProjectionStore` (Component 1) — reads connector admission_verdict during resource resolution

#### 2.1 What It Is

The household-scoped store for "what resources does THIS family/actor actually have connected?" While `GlobalProjectionStore` knows ALL possible tools in the universe, `LocalProjectionStore` knows only the ones this household has set up — Riley's Google Calendar, the family chores list, the shared shopping list. It also tracks household members, alias resolution (so "Riley's calendar" → `resource_id`), and time-windowed projection snapshots for freshness.

This is the LOCAL-WORLD-PROJECTION store. Per-session Fabric gets its own instance (different from the shared GlobalProjectionStore). Each session sees only its actor's connected resources.

In the current code, there is NO equivalent. The current `CapabilityRegistry` is global-only. There is no per-household resource projection. Back currently invents resources (BTC-A3 risk) or guesses from discovery results.

#### 2.2 SQL Schema (4 tables)

```sql
-- Connected resources: one row per resource this actor has linked
CREATE TABLE IF NOT EXISTS connected_resources (
    resource_id     TEXT PRIMARY KEY,
    actor_id        TEXT NOT NULL,
    space_id        TEXT NOT NULL,
    connector_id    TEXT NOT NULL,
    resource_kind   TEXT NOT NULL,   -- 'calendar.primary', 'tasks.personal', etc.
    label           TEXT NOT NULL,   -- "Riley's Google Calendar"
    aliases_json    TEXT,            -- ["Riley calendar", "my cal"]
    status          TEXT NOT NULL CHECK(status IN ('active','suspended','revoked','pending')),
    actor_permission TEXT NOT NULL CHECK(actor_permission IN ('read_write','read_only','restricted','none')),
    last_synced_at  TEXT,
    freshness_state TEXT NOT NULL CHECK(freshness_state IN ('fresh','stale','unknown')),
    created_at      TEXT NOT NULL
);

-- Household members: who lives in this household
CREATE TABLE IF NOT EXISTS household_members (
    person_id       TEXT PRIMARY KEY,  -- stable member UUID
    actor_id        TEXT NOT NULL,     -- session actor who can see this member
    space_id        TEXT NOT NULL,     -- which household/space
    display_name    TEXT NOT NULL,     -- "Riley"
    aliases_json    TEXT,              -- ["Riles", "Rye"]
    role            TEXT NOT NULL CHECK(role IN ('parent','child','guardian','guest','system')),
    resource_ids_json TEXT,            -- {"calendar":"res_cal_riley","tasks":"res_tasks_riley"}
    created_at      TEXT NOT NULL
);

-- Alias index: fast O(1) name-to-entity resolution
CREATE TABLE IF NOT EXISTS alias_index (
    alias_lower     TEXT NOT NULL,     -- normalized lowercase alias
    entity_type     TEXT NOT NULL CHECK(entity_type IN ('resource','person')),
    entity_id       TEXT NOT NULL,     -- resource_id or person_id
    actor_id        TEXT NOT NULL,
    space_id        TEXT NOT NULL,
    PRIMARY KEY (alias_lower, actor_id, entity_type, entity_id)
);

-- Resource projection snapshots: time-windowed "what did this resource look like at time T?"
CREATE TABLE IF NOT EXISTS resource_projection_snapshots (
    snapshot_id         TEXT PRIMARY KEY,
    resource_id         TEXT NOT NULL,
    connector_id        TEXT NOT NULL,
    resource_kind       TEXT NOT NULL,
    actor_id            TEXT NOT NULL,
    query_window_json   TEXT NOT NULL DEFAULT '{}',   -- {"start":"...","end":"..."}
    result_summary_json TEXT NOT NULL DEFAULT '{}',   -- {"count":3,"ids":["a","b","c"]}
    raw_ref             TEXT,                          -- pointer to raw connector response
    freshness_state     TEXT NOT NULL CHECK(freshness_state IN ('fresh','stale','unknown')),
    observed_at         TEXT NOT NULL,
    expires_at          TEXT NOT NULL
);
```

#### 2.3 Public API

```python
class LocalProjectionStore:
    """Household-scoped resource projection. Per-session instance.
    Knows what resources THIS actor has connected. SQLite WAL."""

    # ── Lifecycle ──────────────────────────────────────────
    def __init__(self, db_path: str | Path) -> None: ...
    def open(self) -> None: ...
    def close(self) -> None: ...
    def reset(self) -> None:
        """Delete all data for this actor (session teardown)."""

    # ── Connected Resources ────────────────────────────────
    def upsert_connected_resource(self, resource: ConnectedResourceRecord) -> None: ...
    def get_connected_resource(self, resource_id: str) -> ConnectedResourceRecord | None: ...
    def list_connected_resources(
        self, actor_id: str, *, resource_kind: str | None = None, status: str = "active"
    ) -> list[ConnectedResourceRecord]: ...
    def mark_resource_stale(self, resource_id: str) -> None: ...
    def mark_resource_fresh(self, resource_id: str, observed_at: str | None = None) -> None: ...

    # ── Household Members ──────────────────────────────────
    def upsert_household_member(self, member: HouseholdMemberRecord) -> None: ...
    def get_household_member(self, person_id: str) -> HouseholdMemberRecord | None: ...
    def list_household_members(
        self, actor_id: str
    ) -> list[HouseholdMemberRecord]: ...

    # ── Alias Resolution ───────────────────────────────────
    def rebuild_alias_index(self, actor_id: str, space_id: str) -> None:
        """Rebuild from connected_resources + household_members labels/aliases."""
    def resolve_alias(
        self, alias: str, actor_id: str, *, entity_type: str | None = None
    ) -> list[AliasEntry]:
        """Exact match on alias_lower. Returns [] if no match."""
    def fuzzy_resolve_alias(
        self, alias: str, actor_id: str, *, entity_type: str | None = None
    ) -> list[AliasEntry]:
        """LIKE '%alias%' match. Raises if exact match exists (caller must check exact first)."""

    # ── Projection Snapshots ───────────────────────────────
    def upsert_projection_snapshot(self, snapshot: ProjectionSnapshotRecord) -> None: ...
    def get_fresh_snapshot(
        self, resource_id: str, *, max_age_seconds: int = 300, now: datetime | None = None
    ) -> ProjectionSnapshotRecord | None: ...
```

#### 2.4 Internal Design

**Alias resolution algorithm (two-pass):**

```text
Pass 1 — exact match:
  SELECT * FROM alias_index WHERE alias_lower = ? AND actor_id = ?

Pass 2 — fuzzy match (only if Pass 1 returns []):
  SELECT * FROM alias_index WHERE alias_lower LIKE '%alias%' AND actor_id = ?

Resolution rules:
  - 0 matches → unresolved (not_found)
  - 1 match → resolved
  - >1 matches → unresolved (ambiguous) with candidate list
```

**Alias rebuild:** `rebuild_alias_index(actor_id, space_id)` reads all `connected_resources` and `household_members` for the actor, extracts `label` + `aliases_json` entries, normalizes to lowercase, and bulk-inserts into `alias_index`. This is called after connector adoption or member changes, not on every resolution.

**Freshness state machine:**

```text
fresh   → resource was synced recently, snapshot is current
stale   → resource hasn't been synced within TTL, or connector reports degraded
unknown → resource was just added, never synced
```

**Permission gating:** During resource resolution, `actor_permission` gates whether the resource can be used for the intended operation:

```text
'none'        → excluded (permission_denied)
'restricted'  → excluded (permission_denied)
'read_only'   → allowed for reads, excluded for writes
'read_write'  → allowed for all
```

**Snapshot TTL:** `get_fresh_snapshot()` checks two conditions: (1) `(now - observed_at) <= max_age_seconds` (default 300s = 5 min), (2) `expires_at > now`. Both must pass. Returns the most recent fresh snapshot or None.

**Per-session isolation:** Each session gets its own `LocalProjectionStore` instance with its own SQLite file (path: `./data/local_projection_{session_id}.db`). The `actor_id` filter on every query ensures data isolation. At session teardown, `reset()` clears all data.

#### 2.5 Wiring — Where It Hooks Into service.py

**P3 (per-session Fabric creation):**

```text
# During _create_session_tier2(), after P2 (SessionState):
local_store = LocalProjectionStore(
    db_path=f"./data/local_projection_{session_id}.db"
)
local_store.open()

# P3: pass to FabricFactory
session_fabric = FabricFactory.create_with_ports(
    ...,
    local_projection_store=local_store,
    global_projection_store=shared_fabric.global_projection_store,
)
```

**FabricFactory modification:** `create_with_ports()` accepts optional `local_projection_store: LocalProjectionStore | None = None`. If provided, it's stored on the per-session `Fabric` dataclass as `fabric.local_projection_store`.

**Population (connector adoption):** When a user connects a new resource (e.g., "Link Google Calendar"), the adapter onboarding flow calls:

```text
local_store.upsert_connected_resource(ConnectedResourceRecord(
    resource_id="res_cal_riley_001",
    actor_id=actor_id,
    space_id=space_id,
    connector_id="google_calendar",
    resource_kind="calendar.primary",
    label="Riley's Google Calendar",
    aliases=["Riley calendar", "my cal"],
    status="active",
    actor_permission="read_write",
    freshness_state="fresh",
))
local_store.rebuild_alias_index(actor_id, space_id)
```

**P3.8 (grounding → Fabric context binding):** The grounding handle's `refresh_turn()` can trigger a freshness check:

```text
# In grounding refresh:
stale_resources = [
    r for r in local_store.list_connected_resources(actor_id)
    if r.freshness_state != 'fresh'
]
for r in stale_resources:
    local_store.mark_resource_stale(r.resource_id)
```

**Session teardown (reverse P3):** During `destroy_session()`, after Fabric shutdown:

```text
if local_store is not None:
    local_store.reset()
    local_store.close()
```

#### 2.6 E2E Data Flow

```text
┌─────────────────────────────────────────────────────────────┐
│ SETUP: Connector adoption (user links Google Calendar)      │
│                                                             │
│  1. User connects Google Calendar via UI                    │
│  2. Adapter onboarding creates resource record:             │
│     local_store.upsert_connected_resource(cal_resource)     │
│  3. Alias index rebuilt:                                    │
│     local_store.rebuild_alias_index(actor_id, space_id)     │
│  4. Initial snapshot taken:                                 │
│     local_store.upsert_projection_snapshot(cal_snapshot)    │
│  5. Household member record created/updated:                │
│     local_store.upsert_household_member(riley_record)       │
│     → links Riley's person_id to her calendar resource_id   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ RUNTIME: ResolveResourcesService.resolve()                  │
│                                                             │
│  Input: RequestFrame (person_refs=["Riley"],                │
│         resource_refs=["Riley's calendar"])                 │
│                                                             │
│  Step 1 — Resolve person references:                        │
│    local_store.resolve_alias("Riley", actor_id,             │
│      entity_type="person")                                  │
│    → 1 match → person_id="person_riley_001"                 │
│    local_store.get_household_member("person_riley_001")     │
│    → {display_name:"Riley", role:"child",                   │
│       resource_ids:{"calendar":"res_cal_riley_001"}}        │
│                                                             │
│  Step 2 — Resolve resource references:                      │
│    local_store.resolve_alias("Riley's calendar", actor_id,  │
│      entity_type="resource")                                │
│    → 1 match → resource_id="res_cal_riley_001"              │
│    local_store.get_connected_resource("res_cal_riley_001")  │
│    → {label:"Riley's Google Calendar",                      │
│       connector_id:"google_calendar",                       │
│       resource_kind:"calendar.primary",                     │
│       actor_permission:"read_write",                        │
│       freshness_state:"fresh"}                              │
│                                                             │
│  Step 3 — Cross-reference with GlobalProjectionStore:       │
│    global_store.get_connector("google_calendar")            │
│    → admission_verdict="admitted" ✓                         │
│                                                             │
│  Step 4 — Check permission for intended operation:          │
│    frame has write intent + actor_permission="read_write"   │
│    → allowed ✓                                             │
│                                                             │
│  Step 5 — Check freshness:                                  │
│    local_store.get_fresh_snapshot("res_cal_riley_001")      │
│    → snapshot exists, observed 12s ago, fresh ✓             │
│                                                             │
│  Output: ResourceUniverse with:                             │
│    resource_candidates=[ResourceCandidate(                  │
│      resource_id="res_cal_riley_001",                       │
│      connector_id="google_calendar",                        │
│      ...)],                                                 │
│    person_candidates=[PersonCandidate(                      │
│      person_id="person_riley_001",                          │
│      linked_resource_ids={"calendar":"res_cal_riley_001"},  │
│      ...)],                                                 │
│    completeness="complete", freshness="fresh"               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ RUNTIME: SituatedResolver (Component 4) consumes both       │
│                                                             │
│  resolver.resolve(request_frame)                            │
│    → ResolveResourcesService.resolve()  ← uses LocalStore   │
│    → GlobalProjectionStore.get_constitution(connector_id)   │
│    → GlobalProjectionStore.get_capabilities_by_connector()  │
│    → PolicySelector.select()                                │
│    → Builds CandidateUniverse + ResolutionEnvelope          │
└─────────────────────────────────────────────────────────────┘
```

#### 2.7 Record Types (Python dataclasses)

```python
@dataclass
class ConnectedResourceRecord:
    resource_id: str
    actor_id: str
    space_id: str
    connector_id: str
    resource_kind: str         # 'calendar.primary', 'tasks.personal', etc.
    label: str                 # "Riley's Google Calendar"
    aliases: list[str]         # ["Riley calendar", "my cal"]
    status: str                # 'active' | 'suspended' | 'revoked' | 'pending'
    actor_permission: str      # 'read_write' | 'read_only' | 'restricted' | 'none'
    last_synced_at: str | None
    freshness_state: str       # 'fresh' | 'stale' | 'unknown'
    created_at: str

@dataclass
class HouseholdMemberRecord:
    person_id: str
    actor_id: str
    space_id: str
    display_name: str          # "Riley"
    aliases: list[str]         # ["Riles", "Rye"]
    role: str                  # 'parent' | 'child' | 'guardian' | 'guest' | 'system'
    resource_ids: dict[str, str]  # {"calendar": "res_cal_riley_001", "tasks": "res_tasks_riley_001"}
    created_at: str

@dataclass
class AliasEntry:
    alias_lower: str
    entity_type: str           # 'resource' | 'person'
    entity_id: str             # resource_id or person_id
    actor_id: str
    space_id: str

@dataclass
class ProjectionSnapshotRecord:
    snapshot_id: str
    resource_id: str
    connector_id: str
    resource_kind: str
    actor_id: str
    query_window: dict         # {"start": "2026-06-02T00:00:00Z", "end": "2026-06-09T00:00:00Z"}
    result_summary: dict       # {"count": 3, "ids": ["evt_1", "evt_2", "evt_3"]}
    raw_ref: str | None        # pointer to raw connector response (not the payload itself)
    freshness_state: str       # 'fresh' | 'stale' | 'unknown'
    observed_at: str
    expires_at: str
```

#### 2.8 Test Coverage

```text
GAP-P1-004: LocalProjectionStore integration tests
  File: tests/k1/fabric/stores/test_local_projection_store.py

  Test classes:
    TestLocalProjectionStoreLifecycle
      - test_open_creates_db_and_schema
      - test_close_releases_connection
      - test_reset_clears_all_tables

    TestConnectedResourceCRUD
      - test_upsert_connected_resource_insert
      - test_upsert_connected_resource_update
      - test_get_connected_resource_exists
      - test_get_connected_resource_missing_returns_none
      - test_list_connected_resources_all
      - test_list_connected_resources_filter_by_kind
      - test_list_connected_resources_filter_by_status
      - test_mark_resource_stale
      - test_mark_resource_fresh

    TestHouseholdMemberCRUD
      - test_upsert_household_member_insert
      - test_upsert_household_member_update
      - test_get_household_member_exists
      - test_get_household_member_missing_returns_none
      - test_list_household_members

    TestAliasResolution
      - test_resolve_alias_exact_match
      - test_resolve_alias_no_match
      - test_resolve_alias_multiple_matches
      - test_resolve_alias_filtered_by_entity_type
      - test_fuzzy_resolve_alias_finds_like_match
      - test_fuzzy_resolve_alias_raises_on_exact_match
      - test_rebuild_alias_index_from_resources_and_members
      - test_alias_case_insensitive

    TestProjectionSnapshots
      - test_upsert_projection_snapshot
      - test_get_fresh_snapshot_within_ttl
      - test_get_fresh_snapshot_expired_by_age
      - test_get_fresh_snapshot_expired_by_expires_at
      - test_get_fresh_snapshot_no_snapshots_returns_none

    TestPermissionGating
      - test_read_write_allows_write
      - test_read_only_blocks_write
      - test_restricted_blocks_all
      - test_none_blocks_all

    TestPerSessionIsolation
      - test_different_actor_ids_see_different_resources
      - test_different_space_ids_see_different_members
```

---

### Component 3 — IdempotencyStore

**Target file:** `k1/fabric/stores/idempotency_store.py`
**Source:** Promote + harden from `poc/back_tool_contract_v2/stores/idempotency_store.py`
**Depends on:** Nothing (standalone store — only needs SQLite)

#### 3.1 What It Is

Prevents duplicate execution of the same capability invocation. Every `InvocationRequest` carries an `idempotency_key` (deterministically derived from `binding_id + params_hash + actor_id`). Before Fabric executes, it checks the store. After execution, it records the outcome.

The core invariant: **once `succeeded`, immutable.** No replay, no retry, no state transition can change a `succeeded` record. `failed` records CAN be retried (they transition back to `in_flight` on retry).

In the current code, there is NO idempotency enforcement. `CapabilityFabric._execute_impl()` has no deduplication. The current `K1FamilyStore` has its own idempotency for family-tool writes, but it's adapter-specific, not kernel-level.

#### 3.2 SQL Schema (1 table)

```sql
CREATE TABLE IF NOT EXISTS idempotency_records (
    idempotency_key   TEXT PRIMARY KEY,
    state             TEXT NOT NULL CHECK(state IN ('in_flight','succeeded','failed')),
    invocation_id     TEXT NOT NULL,
    observation_json  TEXT,       -- full InvocationObservation when succeeded
    error             TEXT,       -- error message when failed
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
```

#### 3.3 State Machine

```text
                    ┌──────────────┐
                    │  not_seen    │  (no row exists)
                    └──────┬───────┘
                           │ mark_in_flight()
                           ▼
                    ┌──────────────┐
            ┌───────│  in_flight   │
            │       └──────┬───────┘
            │              │
            │    ┌─────────┴──────────┐
            │    ▼                    ▼
            │ ┌──────────┐     ┌──────────┐
            │ │succeeded │     │  failed  │
            │ └──────────┘     └────┬─────┘
            │    IMMUTABLE          │
            │    (no transition     │ mark_in_flight()
            │     out allowed)      │ (retry — goes back to in_flight IF state != 'succeeded')
            │                       ▼
            │                ┌──────────────┐
            └────────────────│  in_flight   │ (retry)
                             └──────────────┘
```

**Transition rules (enforced in SQL):**

```text
not_seen → in_flight:      INSERT with state='in_flight'
in_flight → succeeded:     UPDATE state='succeeded' WHERE idempotency_key=?
in_flight → failed:        UPDATE state='failed' WHERE idempotency_key=? AND state NOT IN ('succeeded')
failed → in_flight:        UPDATE state='in_flight' WHERE idempotency_key=? AND state NOT IN ('succeeded')
succeeded → ANYTHING:      BLOCKED — WHERE clause prevents transition
```

#### 3.4 Public API

```python
@dataclass(frozen=True)
class IdempotencyCheckResult:
    state: str                      # "not_seen" | "in_flight" | "succeeded" | "failed"
    prior_observation: dict | None  # the succeeded InvocationObservation (for replay)
    error: str | None               # error message if failed

class IdempotencyStore:
    """Prevents duplicate capability execution. SQLite WAL."""

    # ── Lifecycle ──────────────────────────────────────────
    def __init__(self, db_path: str | Path) -> None: ...
    def open(self) -> None: ...
    def close(self) -> None: ...

    # ── State Machine ─────────────────────────────────────
    def check(self, idempotency_key: str) -> IdempotencyCheckResult:
        """Return current state. Does NOT modify."""

    def mark_in_flight(self, idempotency_key: str, invocation_id: str) -> None:
        """Claim the key for this invocation. Fails if already succeeded."""

    def mark_success(self, idempotency_key: str, observation: dict) -> None:
        """Record successful execution. Idempotent — no-op if already succeeded."""

    def mark_failed(self, idempotency_key: str, error: str) -> None:
        """Record failed execution. Does NOT overwrite succeeded."""

    # ── Maintenance ───────────────────────────────────────
    def cleanup_expired(self, max_age_hours: int = 24) -> int:
        """Delete records older than max_age_hours. Returns count deleted."""
```

#### 3.5 Internal Design

**Idempotency key derivation (caller responsibility, not the store):**

```python
def derive_idempotency_key(
    binding_id: str, params: dict, actor_id: str
) -> str:
    """Deterministic idempotency key from binding + params + actor."""
    import hashlib, json
    canonical = json.dumps({
        "binding_id": binding_id,
        "params": params,
        "actor_id": actor_id,
    }, sort_keys=True)
    return hashlib.blake2b(canonical.encode(), digest_size=16).hex()
```

**Immutable-succeeded invariant:** The WHERE clause `state NOT IN ('succeeded')` on `mark_in_flight()` and `mark_failed()` UPDATE statements is the enforcement point. SQLite's `total_changes == 0` after UPDATE means the row was not modified because it was already `succeeded`. `mark_success()` uses an explicit `check()` call first — if already succeeded, it early-returns.

**Replay semantics:** When `check()` returns `state='succeeded'` with `prior_observation`, the caller gets back the original `InvocationObservation`. This is treated as a cache hit — the same observation is returned to Back without re-executing.

**TTL cleanup:** `cleanup_expired()` deletes records where `updated_at < now - max_age_hours`. This prevents unbounded growth. The default 24h window is conservative; succeeded records could theoretically live forever, but cleanup handles the practical case.

#### 3.6 Wiring — Where It Hooks Into Fabric

**Hooks into CapabilityFabric._execute_impl() — step 0 (before step 1):**

```text
def _execute_impl(self, request: CapabilityRequest) -> CapabilityResult:
    # NEW: Step 0 — Idempotency check
    if request.idempotency_key:
        check = self._idempotency_store.check(request.idempotency_key)
        if check.state == "succeeded":
            # Replay — return prior observation
            return CapabilityResult.success_result(
                data=check.prior_observation.get("data"),
                invocation_id=check.prior_observation.get("invocation_id"),
            )
        if check.state == "in_flight":
            # Another invocation is in progress — wait or reject
            return CapabilityResult.failure_result(
                error_code="idempotency_in_flight",
                retriable=True,
            )
        # not_seen or failed — proceed
        self._idempotency_store.mark_in_flight(
            request.idempotency_key, request.invocation_id
        )

    # ... existing 9-step pipeline ...

    # Step 7.5 — After emit completed/failed, record outcome
    if request.idempotency_key:
        if result.status == "success":
            self._idempotency_store.mark_success(
                request.idempotency_key, observation=result.to_dict()
            )
        else:
            self._idempotency_store.mark_failed(
                request.idempotency_key, error=result.error_code or "unknown"
            )
```

**FabricFactory modification:** `create_shared()` and `create_with_ports()` accept optional `idempotency_store: IdempotencyStore | None = None`. If provided, `CapabilityFabric.__init__` receives `idempotency_store=idempotency_store`.

**Fabric container:** New field on `Fabric` dataclass: `idempotency_store: Any = None`.

**service.py — S3 wiring:**

```text
# Before S3:
idempotency_store = IdempotencyStore(db_path="./data/idempotency.db")
idempotency_store.open()

# S3:
self._shared_fabric = FabricFactory.create_shared(
    ...,
    idempotency_store=idempotency_store,
)
```

**Shutdown:** After `shared_fabric.shutdown()`, call `idempotency_store.close()`.

#### 3.7 E2E Data Flow

```text
┌─────────────────────────────────────────────────────────────┐
│ Back invokes capability with idempotency_key                │
│                                                             │
│  InvocationRequest {                                        │
│    binding_id: "bind_cal_create_riley_001",                 │
│    params: {title: "Dentist", start: "...", end: "..."},   │
│    idempotency_key: "a1b2c3d4e5f6a7b8",                    │
│    actor_ref: "person_riley_001"                            │
│  }                                                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ CapabilityFabric._execute_impl() — Step 0                   │
│                                                             │
│  check = idempotency_store.check("a1b2c3d4e5f6a7b8")       │
│                                                             │
│  ┌─ state="not_seen" ──────────────────────────────────┐   │
│  │  → mark_in_flight(key, invocation_id)                │   │
│  │  → proceed with 9-step pipeline                     │   │
│  │  → on success: mark_success(key, observation)        │   │
│  │  → on failure: mark_failed(key, error)               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─ state="in_flight" ─────────────────────────────────┐   │
│  │  → return failure_result("idempotency_in_flight")    │   │
│  │  → Back can retry later (retriable=True)             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─ state="succeeded" ─────────────────────────────────┐   │
│  │  → return success_result(prior_observation)          │   │
│  │  → Back gets the SAME result as the first call       │   │
│  │  → No re-execution                                  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─ state="failed" ────────────────────────────────────┐   │
│  │  → mark_in_flight(key, new_invocation_id)            │   │
│  │  → proceed with 9-step pipeline (retry)              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

#### 3.8 Test Coverage

```text
GAP-P1-005: IdempotencyStore contract tests
  File: tests/k1/fabric/stores/test_idempotency_store.py

  Test classes:
    TestIdempotencyStoreStateMachine
      - test_not_seen_returns_not_seen
      - test_mark_in_flight_transitions_from_not_seen
      - test_mark_success_transitions_from_in_flight
      - test_mark_failed_transitions_from_in_flight
      - test_mark_in_flight_on_failed_allows_retry
      - test_mark_in_flight_on_succeeded_is_blocked
      - test_mark_failed_on_succeeded_is_blocked
      - test_mark_success_on_succeeded_is_idempotent

    TestReplay
      - test_succeeded_returns_prior_observation
      - test_succeeded_observation_matches_original
      - test_multiple_identical_keys_see_same_result

    TestConcurrency
      - test_concurrent_mark_in_flight_only_one_wins
      - test_concurrent_mark_success_only_records_once

    TestCleanup
      - test_cleanup_expired_removes_old_records
      - test_cleanup_expired_preserves_recent_records
```

---

### Component 4 — SituatedResolver

**Target file:** `k1/fabric/resolver/situated_resolver.py`
**Source:** Promote + harden from `poc/back_tool_contract_v2/resolve_situation.py`
**Depends on:** `GlobalProjectionStore` (C1), `LocalProjectionStore` (C2), `PolicySelector` (C5), `CapabilityBinder` (deferred to C5), `ResolveResourcesService` (from C2)

#### 4.1 What It Is

The core brain of Fabric's resolution layer. Takes a `ResolveSituationRequest` (from Back, containing a `RequestFrame`) and returns a `ResolutionEnvelope` (to Back, containing `CandidateUniverse`, `PolicyBundle`, `BindingBundle`, `PromptPack`, verdict, and `allowed_next_actions[]`).

This is the component that answers: "Given this task, this actor, and this household — what can Back legally do right now?" It is the single authority for execution-level decisions. Back cannot invoke a capability without going through this resolver first.

In the current code, there is NO equivalent. Back discovers capabilities via `discover_capabilities` (semantic search) and invokes by name. The target replaces that with `resolve_situation` (situated resolution).

#### 4.2 Verdict Cascade (10 verdicts, evaluated in order)

The `_determine_verdict()` method evaluates conditions in strict priority order. The first matching condition wins:

| # | Verdict | Condition | Sub-reasons |
|---|---|---|---|
| 1 | `cannot_execute` | Budget exhausted (max_iterations ≤ 0, max_fabric_calls ≤ 0, or prompt_budget ≤ 1) | `budget_exhausted` |
| 2 | `cannot_execute` | Idempotency says already succeeded | `duplicate_success` |
| 3 | `needs_disambiguation` | Ambiguous person reference (>1 person matched for a name) | `ambiguous_person` |
| 4 | `stale_projection` | Write candidate has `freshness_state = 'stale'` | `stale_write_candidate` |
| 5 | `needs_disambiguation` | Any unresolved ref with `reason = 'ambiguous'` | `ambiguous_resource` |
| 6 | `missing_required_params` | Any unresolved ref with `reason = 'not_found'` | `resource_not_found` |
| 7 | `missing_required_params` | Required params missing for write intent (e.g., no time_window for calendar write) | `missing_time_window`, `missing_subject` |
| 8 | `promote_to_tier3` | Complexity exceeds Tier 2 threshold: (distinct connectors ≥ 6) OR (dependency_depth ≥ 3) OR (companion_resources AND connectors ≥ 4) | `cross_connector`, `deep_dependency_chain`, `companion_cross_actor` |
| 9 | `blocked_by_policy` | PolicyBundle.policy_verdict = 'deny' | `policy_deny` |
| 10 | `stale_projection` | Any unbound role with `reason = 'stale_projection'` | `binding_stale` |
| 11 | `missing_capability` | Any unbound role with reason in {missing_capability, missing_connector, guide_only} | `missing_capability`, `missing_connector` |
| 12 | `can_execute_with_gate` | Prerequisite reads exist AND not all completed | `incomplete_prerequisites` |
| 13 | `can_execute` | All checks passed, prerequisites completed (or none required) | — |

#### 4.3 Public API

```python
@dataclass(frozen=True)
class ResolveSituationRequest:
    request_frame: RequestFrame                     # Contract A
    actor_scope: dict                               # {actor_id, space_id, device_id}
    safety_context: dict                            # {safety_band, actor_role, budget, session_id}
    resolution_mode: str                            # 'execution' | 'catalog' | 'diagnostic'
    target_tier: str                                # 'tier2' | 'tier3' | 'unknown'
    disclosure_phase: str                           # 'connector_summary' | 'tool_name_selection' | 'schema_binding' | 'execution'
    freshness_policy: str                           # 'require_fresh' | 'allow_stale_reads'
    prompt_budget: int                              # max tokens for PromptPack
    completed_prerequisite_bindings: list[str]      # binding_ids of already-completed prerequisite reads
    previous_resolution_id: str | None              # for refinement without repeating work

@dataclass(frozen=True)
class ResolutionEnvelope:
    resolution_id: str
    request_id: str
    request_frame: RequestFrame
    candidate_universe: ResourceUniverse            # from ResolveResourcesService
    policy_bundle: PolicyBundle                     # from PolicySelector
    binding_bundle: BindingBundle                   # from CapabilityBinder
    prompt_pack: PromptPack                         # from PromptPackBuilder (Component 8)
    policy_bundle_ref: str                          # stable hash ref
    binding_bundle_ref: str                         # stable hash ref
    completeness: str                               # from ResourceUniverse
    freshness: str                                  # from ResourceUniverse
    verdict: str                                    # one of 10 verdicts above
    allowed_next_actions: list[str]                 # human-readable action descriptions
    allowed_capability_names: list[str]             # capability names Back can invoke
    capability_name_to_binding: dict[str, str]      # capability_name → binding_id
    diagnostics: list[dict]                         # trace of resolution decisions
    created_at: str
    expires_at: str                                 # 5-minute TTL from creation

class SituatedResolver:
    """Core resolution engine. Takes a RequestFrame, returns a ResolutionEnvelope."""

    def __init__(
        self,
        global_store: GlobalProjectionStore,
        local_store: LocalProjectionStore,
        *,
        resource_resolver: ResolveResourcesService | None = None,
        policy_selector: PolicySelector | None = None,       # Component 5
        capability_binder: CapabilityBinderService | None = None,  # uses Component 5 output
    ) -> None: ...

    def resolve(self, request: ResolveSituationRequest) -> ResolutionEnvelope:
        """Main entry point. Called by Back via resolve_situation meta-tool."""

    # ── Internal ─────────────────────────────────────────
    def _determine_verdict(
        self, request, universe, policy_bundle, binding_bundle, diagnostics
    ) -> str: ...
    def _allowed_next_actions(
        self, verdict, binding_bundle, completed_prerequisite_bindings
    ) -> list[dict]: ...
    def _build_prompt_pack(
        self, request, universe, verdict, allowed, binding_bundle
    ) -> PromptPack: ...
    def _has_ambiguous_person_reference(self, request) -> bool: ...
```

#### 4.4 Internal Design

**Resolution flow (6-step pipeline):**

```text
Step 1: Resolve resources
  resource_resolver.resolve(frame, actor_id, space_id)
  → ResourceUniverse {resource_candidates, person_candidates, unresolved, scope_proof}

Step 2: Select policy
  policy_selector.select(universe, operations, actor_role, safety_band)
  → PolicyBundle {gates, hil_triggers, verifier_requirements, policy_verdict, deny_reason}

Step 3: Bind capabilities
  capability_binder.bind(universe, policy_bundle, operations, actor_id, session_id, disclosure_phase)
  → BindingBundle {bindings, unbound_roles, tool_name_cards, selected_schema_cards}

Step 4: Determine verdict
  _determine_verdict(request, universe, policy_bundle, binding_bundle, diagnostics)
  → verdict string (one of 10)

Step 5: Compute allowed_next_actions
  _allowed_next_actions(verdict, binding_bundle, completed_prerequisite_bindings)
  → list of {description, capability_name, binding_id}

Step 6: Build PromptPack
  _build_prompt_pack(request, universe, verdict, allowed, binding_bundle)
  → PromptPack with visible_summary + hidden_refs
```

**Allowed-next-actions logic:**

```text
If verdict = 'can_execute_with_gate':
  → Return only incomplete prerequisite_read bindings
    (Back must finish prerequisite reads before the write)

If verdict = 'can_execute':
  → Return primary_read bindings
  → Return primary_write bindings ONLY IF:
      - no prerequisite reads exist, OR
      - all prerequisite reads are completed

Any other verdict:
  → Return [] (no actions allowed — Back must HIL, promote, or submit cannot_execute)
```

**Disclosure phases (CC-10):** The `disclosure_phase` field on the request controls what the `BindingBundle` includes:

| Phase | What's disclosed |
|---|---|
| `connector_summary` | Connector names + constitutions + tool names ONLY (no schemas) |
| `tool_name_selection` | Back commits exact tool names; binder validates selection |
| `schema_binding` | Full schemas returned ONLY for committed tools |
| `execution` | Bindings include invocation-ready contract refs + schemas |

**Ambiguous person detection:** `_has_ambiguous_person_reference()` queries `local_store.resolve_alias(raw_name, actor_id, entity_type='person')` for every person ref in the RequestFrame. If any name resolves to >1 `entity_id`, it's ambiguous → `needs_disambiguation`.

#### 4.5 Wiring — Where It Hooks Into Fabric

**Registered as a Fabric meta-tool:**

The `SituatedResolver.resolve()` method is exposed to Back as a callable meta-tool named `resolve_situation`. This is NOT a capability in the registry — it's a kernel-level tool registered alongside `invoke_capability` and `submit_result`.

```text
# In FabricFactory, after creating CapabilityFabric:
resolver = SituatedResolver(
    global_store=global_projection_store,
    local_store=local_projection_store,  # None for shared Fabric, set for per-session
    policy_selector=policy_selector,
    capability_binder=capability_binder,
)
fabric = Fabric(
    facade=capability_fabric,
    ...,
    situated_resolver=resolver,  # NEW field on Fabric dataclass
)
```

**Tool schema (exposed to Back LLM):**

```json
{
  "name": "resolve_situation",
  "description": "Resolve the execution universe for a task. Returns what you are allowed to do.",
  "parameters": {
    "type": "object",
    "properties": {
      "request_frame_json": {"type": "object", "description": "The RequestFrame for this task"},
      "disclosure_phase": {"type": "string", "enum": ["connector_summary", "tool_name_selection", "schema_binding", "execution"]},
      "committed_tool_names": {"type": "array", "items": {"type": "string"}, "description": "Tool names Back commits to using (Phase 2 only)"},
      "completed_prerequisite_bindings": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["request_frame_json", "disclosure_phase"]
  }
}
```

**Call flow:**

```text
Back (via ToolDispatcher)
  → execute_resolve_situation()
    → build ResolveSituationRequest from Back's tool call args
    → situated_resolver.resolve(request)
    → return ResolutionEnvelope as ToolResult
```

**service.py — S3 wiring:**

```text
# S3: SituatedResolver uses shared GlobalProjectionStore + per-session LocalProjectionStore
# Created in FabricFactory, not directly in service.py
```

**P3 (per-session):** The per-session `SituatedResolver` is created with the per-session `LocalProjectionStore`. The shared `GlobalProjectionStore` is the same instance.

#### 4.6 E2E Data Flow

```text
┌─────────────────────────────────────────────────────────────┐
│ Back builds RequestFrame, calls resolve_situation           │
│                                                             │
│  ResolveSituationRequest {                                  │
│    request_frame: {                                         │
│      user_goal: "Add dentist for Riley Monday 3pm",        │
│      person_refs: [{raw: "Riley"}],                         │
│      operation_hints: ["create"],                           │
│      resource_kind_hint: "calendar_event",                  │
│      time_window_hint: {start: "2026-06-08T15:00:00"},     │
│      actor_id: "person_jordan_001",                         │
│      space_id: "space_family_001"                           │
│    },                                                       │
│    actor_scope: {actor_id: "person_jordan_001"},            │
│    safety_context: {safety_band: "GREEN", actor_role:       │
│      "parent"},                                             │
│    disclosure_phase: "connector_summary"                    │
│  }                                                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ SituatedResolver.resolve()                                  │
│                                                             │
│  Step 1 — Resolve resources:                                │
│    local_store.resolve_alias("Riley", actor_id, "person")   │
│    → 1 match: person_id="person_riley_001"                  │
│    local_store.get_household_member("person_riley_001")     │
│    → {display_name:"Riley", role:"child",                   │
│       resource_ids:{"calendar":"res_cal_riley_001"}}        │
│    local_store.get_connected_resource("res_cal_riley_001")  │
│    → {connector_id:"calendar", freshness:"fresh",           │
│       actor_permission:"read_write"}                        │
│    → ResourceUniverse with 1 person, 1 resource, 0 unresolved│
│                                                             │
│  Step 2 — Select policy:                                    │
│    policy_selector.select(universe, ["create"], "parent",   │
│      "GREEN")                                               │
│    → PolicyBundle {policy_verdict:"allow", gates:[...],     │
│       hil_triggers:[...], verifier_requirements:{...}}      │
│                                                             │
│  Step 3 — Bind capabilities:                                │
│    capability_binder.bind(universe, policy, ["create"],     │
│      actor_id, session_id, "connector_summary")             │
│    → BindingBundle {                                        │
│         bindings: [                                         │
│           {role:"prerequisite_read",                        │
│            capability_name:"tool.read.calendar.list_events"},│
│           {role:"primary_write",                            │
│            capability_name:"tool.execute.calendar.          │
│             create_event"},                                 │
│           {role:"verifier",                                 │
│            capability_name:"tool.read.calendar.get_event"}  │
│         ],                                                  │
│         tool_name_cards: [calendar tool names],             │
│         selected_schema_cards: []  # Phase 1: no schemas yet│
│       }                                                     │
│                                                             │
│  Step 4 — Determine verdict:                                │
│    Checks in order:                                         │
│    ✓ budget OK                                              │
│    ✓ no duplicate idempotency                               │
│    ✓ person not ambiguous                                   │
│    ✓ resource fresh                                         │
│    ✓ no unresolved refs                                     │
│    ✓ params present (has time_window, subject)              │
│    ✓ single connector                                       │
│    ✓ policy allows                                          │
│    ✓ capabilities exist                                     │
│    ✗ prerequisites NOT completed → can_execute_with_gate    │
│                                                             │
│  Step 5 — Allowed next actions:                             │
│    Verdict = "can_execute_with_gate"                        │
│    → Return prerequisite_read bindings:                     │
│      {description: "run prerequisite tool.read.calendar.    │
│       list_events", binding_id: "bind_list_riley_001"}      │
│                                                             │
│  Step 6 — Build PromptPack:                                 │
│    visible_summary: {                                       │
│      verdict: "can_execute_with_gate",                      │
│      resources: [{label: "Riley's Google Calendar", ...}],  │
│      persons: [{label: "Riley", role: "child"}],            │
│      tool_name_cards: ["list_events","create_event",        │
│        "get_event"]                                         │
│    }                                                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Back receives ResolutionEnvelope                            │
│                                                             │
│  Back sees:                                                 │
│    verdict: "can_execute_with_gate"                         │
│    allowed_next_actions: ["run prerequisite tool.read.      │
│      calendar.list_events"]                                 │
│    tool_name_cards: [list_events, create_event, get_event]  │
│    NO schemas yet (Phase 1 disclosure)                      │
│                                                             │
│  Back acts:                                                 │
│    "I must run list_events first. Then I can create_event."  │
│    → invokes list_events (prerequisite read)                │
│    → marks binding_id as completed                          │
│    → calls resolve_situation again with                     │
│      completed_prerequisite_bindings=["bind_list_riley_001"]│
│    → this time verdict = "can_execute"                      │
│    → invokes create_event (primary write)                   │
│    → calls submit_result(completed)                         │
└─────────────────────────────────────────────────────────────┘
```

#### 4.7 Test Coverage

```text
GAP-P1-001: SituatedResolver unit tests
  File: tests/k1/fabric/resolver/test_situated_resolver.py

  Test classes:
    TestVerdictCascade
      - test_cannot_execute_budget_exhausted
      - test_cannot_execute_duplicate_idempotency
      - test_needs_disambiguation_ambiguous_person
      - test_stale_projection_stale_write_candidate
      - test_needs_disambiguation_ambiguous_resource
      - test_missing_required_params_resource_not_found
      - test_missing_required_params_missing_time_window
      - test_promote_to_tier3_cross_connector
      - test_blocked_by_policy_deny
      - test_stale_projection_binding_stale
      - test_missing_capability_no_capability_found
      - test_can_execute_with_gate_incomplete_prerequisites
      - test_can_execute_all_clear
      - test_verdict_ordering_first_match_wins

    TestAllowedNextActions
      - test_can_execute_with_gate_returns_prerequisites_only
      - test_can_execute_returns_primary_reads_and_writes
      - test_can_execute_blocks_write_when_prereq_incomplete
      - test_can_execute_allows_write_when_no_prereq_exists
      - test_can_execute_allows_write_when_prereq_completed
      - test_other_verdicts_return_empty_actions

    TestDisclosurePhases
      - test_connector_summary_discloses_names_only
      - test_tool_name_selection_validates_commitment
      - test_schema_binding_discloses_schemas_for_committed_only
      - test_execution_discloses_full_contract_refs

    TestPromptPack
      - test_prompt_pack_includes_verdict_and_resources
      - test_prompt_pack_includes_tool_name_cards
      - test_prompt_pack_hides_raw_bundle_refs

GAP-P1-009: SituatedResolver negative proof
  File: tests/k1/fabric/resolver/test_situated_resolver_negative.py

  Test classes:
    TestNegativeProof
      - test_missing_connector_returns_missing_capability
      - test_policy_deny_returns_blocked_by_policy
      - test_incomplete_projection_returns_needs_disambiguation
      - test_stale_projection_blocks_write
      - test_budget_exhausted_returns_cannot_execute_not_silent
      - test_unresolvable_person_does_not_guess_identity
```

---

### Component 5 — PolicySelector

**Target file:** `k1/fabric/policy/selector.py`
**Source:** New implementation based on `poc/back_tool_contract_v2/policy_selector.py` + Contract C in whiteboard
**Depends on:** `GlobalProjectionStore` (C1) — reads connector policy_declarations, capability safety_band_min, connector constitutions

#### 5.1 What It Is

The execution-policy authority. Given a resolved `ResourceUniverse` (which resources and people are in play), the intended operations, the actor's role, and the current safety band, it returns a `PolicyBundle` declaring: whether execution is allowed, what gates must be satisfied, what triggers HIL, what verification is required, and what safety mapping evidence was evaluated.

This is DISTINCT from the existing `PolicyEngine` (`k1/fabric/policy/`). The existing `PolicyEngine` is about **provider selection** — which provider to route a capability to (SecurityContext, AffectiveRouting, CognitiveLoadRouting, QoSIntegration). The new `PolicySelector` is about **execution authority** — whether Back can legally invoke this capability for this actor on this resource right now.

In the current code, there is NO execution-level policy selector. The existing `SecurityContext.check_band` and `VisibilityPolicy.check_band` conflict (BTC-004). Back currently invokes whatever it discovers, with only soft prompt nudges.

#### 5.2 Policy Verdict Cascade (4 verdicts)

Evaluated in order. First match wins:

| # | Verdict | Condition |
|---|---|---|
| 1 | `deny` | Connector missing from GlobalProjectionStore (`missing_connector`) |
| 2 | `deny` | Actor role not in `write_requires_actor_role` for write operation |
| 3 | `deny` | Safety band below `capability.safety_band_min` (band escalation) |
| 4 | `needs_hil` | Any HIL trigger fires (delete of shared resource, cross-user impact, etc.) |
| 5 | `allow_with_gate` | Precondition gates exist (prerequisite reads required by constitution) |
| 6 | `allow` | All checks passed |

#### 5.3 Public API

```python
@dataclass(frozen=True)
class PolicyGate:
    gate_id: str
    gate_type: str              # 'precondition' | 'verifier' | 'safety' | 'consent'
    description: str            # human-readable for Back's prompt
    condition: dict             # machine-evaluable condition
    action_required: str        # 'run_read_first' | 'verify_after' | 'confirm_with_user'

@dataclass(frozen=True)
class SafetyMappingEvidence:
    evidence_id: str
    operation: str
    required_band: str          # minimum band the capability requires
    actual_band: str            # current session safety band
    connector_id: str
    capability_name: str
    mapping_result: str         # 'allow' | 'deny' | 'escalated'
    hard_block_reason: str | None

@dataclass(frozen=True)
class PolicyBundle:
    policy_id: str
    connector_ids: list[str]                    # connectors in scope
    operations: list[str]                       # intended operations
    actor_role: str                             # 'parent' | 'child' | 'guardian' | 'guest' | 'system'
    safety_band: str                            # 'GREEN' | 'AMBER' | 'RED'
    roles_allowed: dict[str, list[str]]         # operation → allowed roles
    gates: list[PolicyGate]                     # preconditions that must be satisfied
    hil_triggers: list[dict]                    # conditions that force HIL
    protected_read_policy: dict | None          # if resource has protected_reads declared
    verifier_requirements: dict[str, str]       # operation → verifier capability name
    guide_refs: list[str]                       # guide card references
    policy_verdict: str                         # 'allow' | 'allow_with_gate' | 'needs_hil' | 'deny'
    deny_reason: str | None                     # why denied, if denied
    safety_mapping_evidence: dict | None        # band check evidence

class PolicySelector:
    """Execution-policy authority. Consumes ResourceUniverse, returns PolicyBundle."""

    def __init__(self, global_store: GlobalProjectionStore) -> None: ...

    def select(
        self,
        resource_universe: ResourceUniverse,
        operations: list[str],                  # ['create', 'list', ...]
        actor_role: str,                        # 'parent' | 'child' | ...
        safety_band: str,                       # 'GREEN' | 'AMBER' | 'RED'
    ) -> PolicyBundle: ...
```

#### 5.4 Internal Design

**Policy evaluation flow (per resource candidate, per operation):**

```text
For each resource_candidate in resource_universe:
  1. Look up connector in GlobalProjectionStore
     → If missing → deny_reason = "missing_connector"

  2. Read connector.policy_declarations
     → protected_resources → builds protected_read_policy
     → write_requires_actor_role → checks actor_role membership
     → read_allowed_roles → checks actor_role membership

  3. Find capability for the operation in GlobalProjectionStore
     → capability.safety_band_min vs. current safety_band
     → If band insufficient → SafetyMappingEvidence with mapping_result="deny"

  4. Check constitution for this connector + operation
     → preconditions → creates PolicyGate(gate_type="precondition")
     → verification → populates verifier_requirements
     → hil_gates → populates hil_triggers

  5. Special case: delete operations on shared resources
     → Force HIL trigger regardless of role
```

**Key distinction from PolicyEngine (BTC-004 fix):**

```text
PolicyEngine (existing, k1/fabric/policy/):
  Owns: PROVIDER selection policy
  Scope: "which provider should execute this capability?"
  Dimensions: SecurityContext, AffectiveRouting, CognitiveLoadRouting, QoSIntegration
  Does NOT answer: "is this actor allowed to do this?"

PolicySelector (new, k1/fabric/policy/selector.py):
  Owns: EXECUTION authority policy
  Scope: "can this actor invoke this capability on this resource?"
  Dimensions: role authorization, safety band, preconditions, HIL triggers, verification
  Does NOT answer: "which provider should handle it?"
```

**Safety band resolution (BTC-004):** `PolicySelector` is the single authority for safety band decisions. It compares `session_safety_band` against `capability.safety_band_min` using rank ordering: `GREEN(1) < AMBER(2) < RED(3)`. If `session_band < min_band`, it produces `SafetyMappingEvidence` with `mapping_result="deny"`. This replaces the conflicting `SecurityContext.check_band` (Fabric) vs `VisibilityPolicy.check_band` (family tools) — the selector's verdict is final.

**Constitution→policy interaction:** The constitution declares what must happen (preconditions, HIL gates, verification). The policy selector reads the constitution and translates it into `PolicyBundle.gates[]` and `PolicyBundle.hil_triggers[]`. Policy may TIGHTEN constitution gates (e.g., add extra HIL requirements for child actors) but cannot RELAX them. This is enforced by the selector: if the constitution says "HIL before delete," the policy cannot override that.

#### 5.5 Wiring

**Created in FabricFactory alongside SituatedResolver:**

```text
# FabricFactory:
policy_selector = PolicySelector(global_store=global_projection_store)

situated_resolver = SituatedResolver(
    global_store=global_projection_store,
    local_store=local_projection_store,
    policy_selector=policy_selector,  # ← injected
    capability_binder=capability_binder,
)
```

**Called by SituatedResolver at Step 2:**

```text
# Inside SituatedResolver.resolve():
policy_bundle = self.policy_selector.select(
    resource_universe=universe,
    operations=[intent.operation_hint for intent in frame.intents],
    actor_role=str(frame.safety_context.get("actor_role") or "parent"),
    safety_band=str(frame.safety_context.get("safety_band") or "GREEN"),
)
```

**Does NOT hook into CapabilityFabric._execute_impl().** PolicySelector runs at RESOLUTION time (before invocation), not at EXECUTION time. The existing PolicyEngine continues to run at execution time (step 2 of _execute_impl) for provider selection. These are different concerns, different pipelines.

#### 5.6 E2E Data Flow

```text
┌─────────────────────────────────────────────────────────────┐
│ SituatedResolver calls policy_selector.select()             │
│                                                             │
│  Input:                                                     │
│    resource_universe: {                                     │
│      resource_candidates: [{                                │
│        connector_id: "calendar",                            │
│        resource_kind: "calendar.primary",                   │
│        freshness_state: "fresh"                             │
│      }]                                                     │
│    }                                                        │
│    operations: ["create"]                                   │
│    actor_role: "parent"                                     │
│    safety_band: "GREEN"                                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ PolicySelector.select()                                     │
│                                                             │
│  For resource: calendar.primary (connector: calendar)       │
│                                                             │
│  1. global_store.get_connector("calendar")                  │
│     → connector exists ✓                                    │
│                                                             │
│  2. connector.policy_declarations:                          │
│     write_requires_actor_role: ["parent", "guardian"]       │
│     → actor_role="parent" is allowed ✓                      │
│                                                             │
│  3. global_store.find_capability(operation="create",        │
│     effect="write", connector_id="calendar")                │
│     → capability: {                                         │
│         capability_name: "tool.execute.calendar.            │
│           create_event",                                    │
│         safety_band_min: "GREEN"                            │
│       }                                                     │
│     → safety_band="GREEN" >= min_band="GREEN" ✓             │
│                                                             │
│  4. global_store.get_constitution("calendar", "create")     │
│     → constitution: {                                       │
│         preconditions: ["list_events before create"],       │
│         verification: {"read_after_write": "get_event"}     │
│       }                                                     │
│     → creates PolicyGate: "Run prerequisite read before     │
│       create" (gate_type="precondition")                    │
│     → verifier_requirements: {"create": "get_event"}        │
│                                                             │
│  5. No HIL triggers (not a delete, not cross-user)          │
│                                                             │
│  Verdict: "allow_with_gate" (gates exist)                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ PolicyBundle returned to SituatedResolver                   │
│                                                             │
│  {                                                          │
│    policy_verdict: "allow_with_gate",                       │
│    gates: [{                                                │
│      gate_type: "precondition",                             │
│      description: "Run prerequisite read before create",    │
│      action_required: "run_read_first"                      │
│    }],                                                      │
│    verifier_requirements: {"create": "get_event"},          │
│    roles_allowed: {"create": ["parent", "guardian"]},       │
│    deny_reason: null,                                       │
│    safety_mapping_evidence: null                            │
│  }                                                          │
│                                                             │
│  SituatedResolver uses this to:                             │
│    → Include gates in verdict logic                         │
│    → Pass verifier_requirements to CapabilityBinder         │
│    → Include policy cards in PromptPack                     │
└─────────────────────────────────────────────────────────────┘
```

#### 5.7 Test Coverage

```text
GAP-P1-002: PolicySelector contract tests
  File: tests/k1/fabric/policy/test_policy_selector.py

  Test classes:
    TestPolicyVerdicts
      - test_allow_when_all_checks_pass
      - test_allow_with_gate_when_preconditions_exist
      - test_needs_hil_when_delete_triggers_hil
      - test_deny_missing_connector
      - test_deny_role_not_allowed_for_write
      - test_deny_safety_band_below_minimum
      - test_verdict_ordering_first_deny_wins

    TestSafetyBandEnforcement (BTC-004)
      - test_green_session_allows_green_capability
      - test_amber_session_denies_green_capability
      - test_amber_session_allows_amber_capability
      - test_red_session_denies_amber_capability
      - test_safety_mapping_evidence_produced_on_deny

    TestRoleAuthorization
      - test_parent_allowed_for_write
      - test_child_denied_for_write_without_guardian
      - test_guardian_allowed_for_write
      - test_guest_denied_for_write
      - test_read_operations_use_read_allowed_roles

    TestConstitutionIntegration
      - test_preconditions_create_policy_gates
      - test_verification_requirements_populated_from_constitution
      - test_hil_gates_populated_from_constitution
      - test_policy_cannot_relax_constitution_gates

    TestProtectedReads
      - test_protected_read_policy_created_when_declared
      - test_protected_read_policy_null_when_not_declared
```

---

### Component 6 — VerificationPlanRunner

**Target file:** `k1/fabric/verification/runner.py`
**Source:** Promote + harden from `poc/back_tool_contract_v2/verification_runner.py`
**Depends on:** `GlobalProjectionStore` (C1) — reads capability contracts for verifier refs; `NativeToolProvider` — executes readback capabilities

#### 6.1 What It Is

The post-write verification authority. After Fabric executes a write capability (e.g., `calendar.create_event`), the `VerificationPlanRunner` confirms the write actually happened in the system of record. It answers: "Did the event really get created?" by reading it back from the provider.

**Principle 5 enforcement:** `submit_result(completed)` requires verification pass or explicit degraded-completion policy. Provider success (HTTP 200) is not verified completion — the verifier confirms the data exists in persistence.

In the current code, there is NO verification step. `CapabilityFabric._execute_impl()` validates output schema (step 6) but does NOT verify the write persisted. Back currently calls `submit_result(complete)` on provider status alone — this is Problem #4 from the POC problem statement.

#### 6.2 Verification Methods (6 total, 3 implemented)

| Method | Status | What it does |
|---|---|---|
| `read_after_write` | ✅ Implemented (POC-proven) | Reads back the created/updated entity via a read capability. Confirms event_id exists, title/start/end match. |
| `output_schema` | ✅ Implemented (POC-proven) | Validates the invocation output contains required fields (e.g., `event_id` in response). Lighter-weight than read_after_write. |
| `none_available` | ✅ Implemented | No verifier method declared. Returns `unavailable` status. `submit_result(completed)` blocked unless `degraded_completion_policy` allows it. |
| `state_compare` | 🔲 Deferred | Compare pre-write and post-write resource state snapshots. For resources that don't support read-by-id. |
| `audit_receipt` | 🔲 Deferred | Validate a signed audit receipt from the connector (for external systems). |
| `external_receipt` | 🔲 Deferred | Validate a third-party attestation (e.g., blockchain receipt, notary). |
| `policy_attestation` | 🔲 Deferred | Attestation from policy authority that the write complies with governance rules. |

#### 6.3 Public API

```python
@dataclass(frozen=True)
class VerificationPlan:
    verification_plan_id: str
    resolution_id: str
    binding_id: str
    invocation_id: str
    verifier_ref: str | None                    # capability name of the verifier
    verifier_method: str                        # 'read_after_write' | 'output_schema' | 'none_available' | 'state_compare' | 'audit_receipt'
    expected_effect: str                        # 'write' | 'delete' | 'compute'
    expected_resource_state: dict               # fields expected to exist after write
    readback_capability_ref: str | None         # e.g., 'tool.read.calendar.get_event'
    readback_params: dict | None                # params for the readback call
    max_staleness_ms: int                       # max allowed age of readback (default 300_000 = 5 min)
    degraded_completion_policy: str | None      # policy for when verification is unavailable
    required_for_submit_status: str             # 'completed' — submit_result requires this

@dataclass(frozen=True)
class VerificationObservation:
    verification_id: str
    verification_plan_id: str
    status: str                                 # 'verified' | 'degraded_verified' | 'failed' | 'inconclusive' | 'skipped_by_policy' | 'unavailable'
    observed_effect: str | None
    observed_resource_state_ref: str | None     # "event:evt_abc123" — pointer to observed entity
    mismatch_summary: str | None                # what didn't match, if failed
    stale_read_summary: str | None              # if readback was stale
    degraded_reason: str | None                 # why degraded, if degraded_verified
    recovery_directive: dict | None             # what Back should do next
    proof_refs: list[str]                       # evidence references

class VerificationPlanRunner:
    """Post-write verification authority. Confirms writes persisted."""

    def __init__(
        self,
        native_provider: NativeToolProvider,    # for executing readback capabilities
        global_store: GlobalProjectionStore,    # for looking up capability contracts
    ) -> None: ...

    # ── Plan ─────────────────────────────────────────────
    def build_plan(
        self,
        binding: CapabilityBinding,             # the binding that was invoked
        observation: InvocationObservation,     # the invocation result
        constitution: dict | None,              # connector constitution with verification requirements
        *,
        degraded_completion_policy: str | None = None,
        max_staleness_ms: int = 300_000,
    ) -> VerificationPlan: ...

    # ── Execute ──────────────────────────────────────────
    def run(
        self,
        plan: VerificationPlan,
        observation: InvocationObservation | None = None,
        *,
        now: datetime | None = None,
    ) -> VerificationObservation: ...

    # ── Gate ─────────────────────────────────────────────
    def gate(
        self,
        observation: VerificationObservation,
        policy: str | None = None,
    ) -> bool:
        """Returns True if submit_result(completed) is legal."""
```

#### 6.4 Internal Design

**build_plan() logic:**

```text
1. Look up capability contract from GlobalProjectionStore
   → capability = global_store.get_capability(binding.capability_name)

2. Read constitution.verification for this operation
   → If constitution declares "read_after_write" for this operation:
       - Extract event_id from observation.structured_result
       - Build readback capability ref: "tool.read.{connector_id}.get_event"
       - Build readback params: {event_id, resource_id}
       - Build expected_resource_state: {event_id, title, start, end}
       → verifier_method = "read_after_write"

   → If constitution declares "output_schema":
       - expected_resource_state = {required_output_fields: ["event_id"]}
       → verifier_method = "output_schema"

   → If no verifier declared:
       → verifier_method = "none_available"

3. Return VerificationPlan with all fields populated
```

**run() logic per method:**

```text
read_after_write:
  1. Extract event_id from readback_params
  2. If no event_id → failed("no target event_id available for readback")
  3. Call native_provider.dispatch(readback_capability_ref, readback_params)
  4. If provider not found → unavailable
  5. If data.found == false → failed("readback found no event")
  6. Compare expected_resource_state fields against readback data:
     - title mismatch → failed with mismatch_summary
     - start mismatch → failed
     - end mismatch → failed
  7. All fields match → verified

output_schema:
  1. Check observation.structured_result has all required_output_fields
  2. All present → verified
  3. Missing fields → failed with mismatch_summary

none_available:
  1. If degraded_completion_policy allows → degraded_verified
  2. Otherwise → unavailable with recovery_directive={action: "block_and_submit"}
```

**gate() logic:**

```text
Returns True (submit_result legal) when:
  - status == "verified"
  - status == "degraded_verified" AND policy allows degraded completion
  - status == "skipped_by_policy"

Returns False (submit_result blocked) when:
  - status == "failed"
  - status == "inconclusive"
  - status == "unavailable" AND no degraded_completion_policy
```

#### 6.5 Wiring — Where It Hooks Into Fabric

**Hooks into CapabilityFabric._execute_impl() — step 7.5 (after emit, before metrics):**

```text
# After step 7 (emit completed) and before step 8 (update metrics):

# NEW: Step 7.5 — Verification
if binding.verifier_ref is not None:
    plan = self._verification_runner.build_plan(
        binding=binding,
        observation=observation,
        constitution=constitution,
    )
    verification = self._verification_runner.run(plan, observation=observation)

    if not self._verification_runner.gate(verification):
        # Verification failed — override result
        result = CapabilityResult.failure_result(
            error_code="verification_failed",
            data={"verification_observation": verification.to_dict()},
        )
```

**FabricFactory wiring:**

```text
verification_runner = VerificationPlanRunner(
    native_provider=native_tool_provider,
    global_store=global_projection_store,
)

capability_fabric = CapabilityFabric(
    ...,
    verification_runner=verification_runner,  # NEW constructor param
)
```

**Fabric container:** New field on `Fabric` dataclass: `verification_runner: Any = None`.

**Constitution→verifier mapping:** The connector constitution's `verification_requirements` are translated by `PolicySelector` (Component 5) into `PolicyBundle.verifier_requirements`. The `CapabilityBinder` reads those and sets `CapabilityBinding.verifier_ref`. The `VerificationPlanRunner` reads `binding.verifier_ref` and executes accordingly. This chain means the constitution author declares verification intent; the runtime enforces it.

#### 6.6 E2E Data Flow

```text
┌─────────────────────────────────────────────────────────────┐
│ Back invokes calendar.create_event → returns ok             │
│                                                             │
│  InvocationObservation {                                    │
│    status: "success",                                       │
│    data: {                                                  │
│      result: {                                              │
│        success: true,                                       │
│        event_id: "evt_abc123",                              │
│        title: "Dentist",                                    │
│        start: "2026-06-08T15:00:00",                        │
│        end: "2026-06-08T16:00:00"                           │
│      }                                                      │
│    }                                                        │
│  }                                                          │
│                                                             │
│  BindingBundle {                                            │
│    binding: {                                               │
│      verifier_ref: "tool.read.calendar.get_event",          │
│      connector_id: "calendar",                              │
│      resource_id: "res_cal_riley_001"                       │
│    }                                                        │
│  }                                                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ VerificationPlanRunner.build_plan()                         │
│                                                             │
│  1. global_store.get_capability("tool.execute.calendar.     │
│     create_event")                                          │
│     → operation: "create"                                   │
│                                                             │
│  2. constitution.verification["create"]                     │
│     → "read_after_write"                                    │
│                                                             │
│  3. Build plan:                                             │
│     verifier_method: "read_after_write"                     │
│     readback_capability_ref: "tool.read.calendar.get_event" │
│     readback_params: {event_id: "evt_abc123",               │
│       resource_id: "res_cal_riley_001"}                     │
│     expected_resource_state: {                               │
│       event_id: "evt_abc123",                               │
│       title: "Dentist",                                     │
│       start: "2026-06-08T15:00:00",                         │
│       end: "2026-06-08T16:00:00"                            │
│     }                                                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ VerificationPlanRunner.run() — _run_read_after_write()      │
│                                                             │
│  1. Extract event_id: "evt_abc123" ✓                        │
│                                                             │
│  2. native_provider.dispatch(                               │
│       "tool.read.calendar.get_event",                       │
│       {event_id: "evt_abc123", resource_id: "res_cal_riley_001"})│
│     → data: {                                               │
│         found: true,                                        │
│         title: "Dentist",                                   │
│         start: "2026-06-08T15:00:00",                       │
│         end: "2026-06-08T16:00:00"                          │
│       }                                                     │
│                                                             │
│  3. Compare expected vs actual:                             │
│     title: "Dentist" == "Dentist" ✓                         │
│     start: "2026-06-08T15:00:00" ✓                          │
│     end: "2026-06-08T16:00:00" ✓                            │
│                                                             │
│  4. All match → status: "verified"                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ VerificationPlanRunner.gate()                               │
│                                                             │
│  status = "verified"                                        │
│  → True — submit_result(completed) is legal                 │
│                                                             │
│  Back calls submit_result(completed)                        │
│  → includes verification_observation as evidence            │
└─────────────────────────────────────────────────────────────┘
```

**Failure scenario — write didn't persist:**

```text
native_provider.dispatch("get_event", {event_id: "evt_abc123"})
  → data: {found: false}

VerificationObservation {
  status: "failed",
  mismatch_summary: "readback found no event for id evt_abc123"
}

gate() → False
→ CapabilityFabric returns failure_result("verification_failed")
→ Back CANNOT call submit_result(completed)
→ Back calls submit_result(partial) or retries
```

#### 6.7 Test Coverage

```text
GAP-P1-006: VerificationPlanRunner contract tests
  File: tests/k1/fabric/verification/test_verification_runner.py

  Test classes:
    TestBuildPlan
      - test_build_plan_read_after_write_from_constitution
      - test_build_plan_output_schema_from_constitution
      - test_build_plan_none_available_when_no_verifier_declared
      - test_build_plan_extracts_event_id_from_structured_result
      - test_build_plan_constructs_readback_capability_ref

    TestRunReadAfterWrite
      - test_verified_when_all_fields_match
      - test_failed_when_title_mismatches
      - test_failed_when_start_mismatches
      - test_failed_when_readback_finds_no_event
      - test_unavailable_when_readback_capability_not_found
      - test_failed_when_no_event_id_in_params

    TestRunOutputSchema
      - test_verified_when_required_fields_present
      - test_failed_when_required_fields_missing

    TestRunNoneAvailable
      - test_degraded_verified_when_policy_allows
      - test_unavailable_when_no_policy

    TestGate
      - test_gate_allows_verified
      - test_gate_allows_degraded_verified_with_policy
      - test_gate_blocks_failed
      - test_gate_blocks_inconclusive
      - test_gate_blocks_unavailable_without_policy

    TestIntegration
      - test_full_read_after_write_cycle_through_fabric_execute
      - test_verification_blocks_submit_result_on_failure
```

---

### Component 7 — ConnectorConstitution (Schema + Loader)

**Target files:** `k1/fabric/constitution/schema.py` + `k1/fabric/constitution/loader.py`
**Source:** New implementation based on whiteboard Constitution Tooling section + POC `connector_constitutions` table
**Depends on:** `GlobalProjectionStore` (C1) — reads/writes to `connector_constitutions` table

#### 7.1 What It Is

The **connector constitution** is the knowledge carrier that makes the Dumb-LLM Principle satisfiable. It is a structured, versioned, runtime-enforced contract that declares: what prerequisite reads must happen, what conflicts to check, when to ask HIL, in what order to mutate, and how to verify. The constitution ships WITH the connector (Principle 6), is authored once per connector (not per tool), and is consumed by `PolicySelector` (C5), `SituatedResolver` (C4), `CapabilityBinder`, and `VerificationPlanRunner` (C6).

This component has TWO sub-components:

- **`ConstitutionSchema`** — The JSON Schema definition for `ConstitutionArtifact`. Validates that every constitution has the required machine-enforceable core fields and optional prompt-card material. This is the DESIGN-TIME contract.

- **`ConstitutionLoader`** — Loads constitutions from the `connector_constitutions` table in `GlobalProjectionStore`. Handles JSON parsing, version checking, and provides typed access. This is the RUNTIME bridge.

In the current code, the POC has a simpler `connector_constitutions` table with only `connector_id`, `operation`, `preconditions_json`, `companion_roles_json`, `verification_json`. The target constitution is significantly richer — it adds execution phases, conflict analysis rules, HIL gates, mutation sequencing, and prompt-card summaries.

#### 7.2 ConstitutionArtifact JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://familyos.dev/schemas/constitution-artifact-v1.json",
  "title": "ConstitutionArtifact",
  "type": "object",
  "required": [
    "constitution_id",
    "connector_id",
    "schema_version",
    "execution_phases",
    "prerequisite_reads",
    "verification_requirements"
  ],
  "properties": {
    "constitution_id": {
      "type": "string",
      "description": "Unique identifier for this constitution version"
    },
    "connector_id": {
      "type": "string",
      "description": "The connector this constitution governs"
    },
    "capability_refs": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Capability names this constitution governs (empty = all capabilities on connector)"
    },
    "schema_version": {
      "type": "string",
      "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$",
      "description": "Semantic version of the constitution schema"
    },
    "authored_by": {"type": "string"},
    "authored_at": {"type": "string", "format": "date-time"},
    "last_proven_at": {
      "type": "string",
      "format": "date-time",
      "description": "Last time a POC proved these rules hold"
    },

    "execution_phases": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["grounding", "prerequisite_reads", "conflict_analysis", "hil_gating", "coordinated_mutation"]
      },
      "description": "Ordered phases the runtime must enforce"
    },
    "prerequisite_reads": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["description", "capability_hint"],
        "properties": {
          "description": {"type": "string"},
          "capability_hint": {"type": "string", "description": "e.g., 'list_events', 'list_tasks'"},
          "parallelizable": {"type": "boolean", "default": true},
          "scope": {"type": "string", "enum": ["self", "participant", "conflict_subject", "guardian"]},
          "timeout_ms": {"type": "integer", "default": 30000}
        }
      },
      "description": "Reads that MUST complete before writes"
    },
    "conflict_analysis_rules": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rule_id", "description", "predicate"],
        "properties": {
          "rule_id": {"type": "string"},
          "description": {"type": "string"},
          "predicate": {
            "type": "string",
            "description": "Machine-evaluable: 'overlap_time_window', 'duplicate_title', 'any_in_category'"
          },
          "severity": {"type": "string", "enum": ["blocking", "warning"]}
        }
      }
    },
    "hil_gates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["gate_id", "trigger", "action"],
        "properties": {
          "gate_id": {"type": "string"},
          "trigger": {
            "type": "string",
            "description": "Condition that fires HIL: 'time_missing', 'conflict_detected', 'guardian_impact', 'cross_user'"
          },
          "action": {
            "type": "string",
            "enum": ["ask_for_time", "propose_alternatives", "confirm_with_user", "require_approval"]
          },
          "require_actor_role": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Roles that must approve (empty = any role)"
          }
        }
      }
    },
    "mutation_sequencing": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["step", "capability_hint", "depends_on"],
        "properties": {
          "step": {"type": "integer"},
          "capability_hint": {"type": "string"},
          "depends_on": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Step indices this step depends on"
          },
          "produces_artifact": {"type": "string", "description": "e.g., 'event_id'"}
        }
      }
    },
    "verification_requirements": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["operation", "method"],
        "properties": {
          "operation": {"type": "string"},
          "method": {"type": "string", "enum": ["read_after_write", "output_schema", "state_compare", "audit_receipt"]},
          "readback_capability_hint": {"type": "string", "description": "e.g., 'get_event'"},
          "required_output_fields": {
            "type": "array",
            "items": {"type": "string"}
          }
        }
      }
    },
    "companion_resource_roles": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["role_type", "description"],
        "properties": {
          "role_type": {"type": "string", "description": "e.g., 'participants', 'conflict_subjects', 'guardians'"},
          "description": {"type": "string"},
          "resource_kinds": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Resource kinds to read for this role"
          }
        }
      }
    },

    "precondition_summary": {
      "type": "string",
      "description": "Compact text for Back/Planner: 'Before create: list events to detect duplicates'"
    },
    "companion_resource_summary": {
      "type": "string",
      "description": "Compact text: 'Check participant calendars, chores, and caregiver schedules'"
    },
    "hil_trigger_summary": {
      "type": "string",
      "description": "Compact text: 'Ask user if: time missing, conflict exists, or affects guardians'"
    },
    "degradation_policy": {
      "type": "string",
      "enum": ["block", "allow_degraded_completion", "ask_hil"],
      "description": "What happens when a prerequisite read fails"
    }
  }
}
```

#### 7.3 Public API

```python
# ── k1/fabric/constitution/schema.py ──────────────────────

class ConstitutionSchema:
    """Validates ConstitutionArtifact against JSON Schema + semantic rules."""

    # Class-level access to the JSON Schema
    SCHEMA: dict  # the full JSON Schema above

    @classmethod
    def validate(cls, constitution: dict) -> list[str]:
        """Validate against JSON Schema. Returns list of error messages (empty = valid)."""

    @classmethod
    def validate_semantic_rules(cls, constitution: dict) -> list[str]:
        """Validate semantic rules beyond JSON Schema:
          1. prerequisite_reads must not be empty for write-capable connectors
          2. execution_phases must contain prerequisite_reads if prerequisite_reads[] is non-empty
          3. verification_requirements must declare method for each write operation
          4. companion_resource_roles must reference valid resource kinds
          5. mutation_sequencing step indices must be sequential and depends_on must be valid
          6. constitution_id must include connector_id prefix
        """


# ── k1/fabric/constitution/loader.py ──────────────────────

@dataclass(frozen=True)
class ConstitutionArtifact:
    """Typed representation of a connector constitution."""
    constitution_id: str
    connector_id: str
    capability_refs: list[str]
    schema_version: str
    authored_by: str | None
    authored_at: str | None
    last_proven_at: str | None

    # Machine-enforceable core
    execution_phases: list[str]
    prerequisite_reads: list[dict]
    conflict_analysis_rules: list[dict]
    hil_gates: list[dict]
    mutation_sequencing: list[dict]
    verification_requirements: list[dict]
    companion_resource_roles: list[dict]

    # Prompt-card material
    precondition_summary: str | None
    companion_resource_summary: str | None
    hil_trigger_summary: str | None
    degradation_policy: str | None

    def get_verification_method(self, operation: str) -> str | None:
        """Return verifier method for an operation, or None."""
    def get_prerequisite_reads_for_scope(self, scope: str) -> list[dict]:
        """Filter prerequisite reads by scope: 'self', 'participant', etc."""
    def get_hil_gates_for_trigger(self, trigger: str) -> list[dict]:
        """Filter HIL gates by trigger type."""


class ConstitutionLoader:
    """Loads and caches constitutions from GlobalProjectionStore."""

    def __init__(self, global_store: GlobalProjectionStore) -> None: ...

    def load(self, connector_id: str) -> ConstitutionArtifact | None:
        """Load the current constitution for a connector. Cached in-memory."""

    def load_for_operation(
        self, connector_id: str, operation: str
    ) -> ConstitutionArtifact | None:
        """Load constitution filtered to the given operation's relevant rules."""

    def upsert(
        self, artifact: ConstitutionArtifact
    ) -> None:
        """Validate + store constitution in GlobalProjectionStore.
        Raises ValueError if validation fails."""

    def invalidate_cache(self, connector_id: str | None = None) -> None:
        """Clear cache for a connector, or all if None."""

    def list_all(self) -> list[ConstitutionArtifact]: ...
```

#### 7.4 Internal Design

**Storage in GlobalProjectionStore:**

The `ConstitutionLoader` writes to the `connector_constitutions` table using the schema defined in Component 1. Each JSON array field is serialized with `json.dumps(sort_keys=True)`. The constitution is keyed by `connector_id` (one constitution per connector — NOT per operation). Operation-specific rules are accessed by filtering the arrays on `operation` field.

**POC→Target migration:**

```text
POC connector_constitutions table:
  connector_id | operation | preconditions_json | companion_roles_json | verification_json

Target connector_constitutions table (Component 1):
  connector_id (PK) | constitution_id | schema_version | authored_by | authored_at |
  last_proven_at | execution_phases_json | prerequisite_reads_json |
  conflict_analysis_rules_json | hil_gates_json | mutation_sequencing_json |
  verification_requirements_json | companion_resource_roles_json |
  precondition_summary | companion_resource_summary | hil_trigger_summary |
  degradation_policy

Migration: The POC table's operation-level granularity is FLATTENED into arrays.
The target table has ONE row per connector. All operations' rules are in the
JSON arrays with an "operation" discriminator field.
```

**Caching:** `ConstitutionLoader` maintains an in-memory `dict[connector_id, ConstitutionArtifact]`. On `load()`, it checks the cache first. On `upsert()`, it validates via `ConstitutionSchema.validate()` + `validate_semantic_rules()`, writes to the store, and updates the cache. On `invalidate_cache()`, it clears one or all entries.

**Version enforcement:** The `schema_version` field follows semver. The loader checks that the version is compatible (same major). If a connector constitution has a different major version, the loader logs a warning and attempts best-effort parsing of known fields.

#### 7.5 Wiring — Where It Hooks Into Fabric

**Created in FabricFactory, passed to dependent components:**

```text
# FabricFactory:
constitution_loader = ConstitutionLoader(global_store=global_projection_store)

# Injected into:
policy_selector = PolicySelector(
    global_store=global_projection_store,
    constitution_loader=constitution_loader,  # reads constitutions for policy gates
)

situated_resolver = SituatedResolver(
    ...,
    constitution_loader=constitution_loader,  # reads constitutions for verdict logic
)

verification_runner = VerificationPlanRunner(
    ...,
    constitution_loader=constitution_loader,  # reads verification requirements
)
```

**Populated at S8 (family tools bootstrap):**

```text
# After ManifestTranslator registers contracts:
for connector_id in ["calendar", "tasks", "reminders", "chores", "shopping"]:
    constitution = ConstitutionArtifact(
        constitution_id=f"const_{connector_id}_v1.0.0",
        connector_id=connector_id,
        schema_version="1.0.0",
        execution_phases=["grounding", "prerequisite_reads", "conflict_analysis", "hil_gating", "coordinated_mutation"],
        prerequisite_reads=[
            {"description": "List events before create", "capability_hint": "list_events",
             "parallelizable": True, "scope": "self"},
        ],
        conflict_analysis_rules=[
            {"rule_id": "dup_check", "description": "Check for duplicate events",
             "predicate": "overlap_time_window", "severity": "blocking"},
        ],
        hil_gates=[
            {"gate_id": "time_missing", "trigger": "time_missing",
             "action": "ask_for_time"},
        ],
        verification_requirements=[
            {"operation": "create", "method": "read_after_write",
             "readback_capability_hint": "get_event"},
        ],
        companion_resource_roles=[],
        precondition_summary="Before creating an event, list existing events to check for duplicates and time conflicts.",
        degradation_policy="block",
    )
    constitution_loader.upsert(constitution)
```

**Consumed by PolicySelector (step 4):**

```text
# In PolicySelector.select():
constitution = self.constitution_loader.load(candidate.connector_id)
if constitution:
    # Preconditions → PolicyGate objects
    for rule in constitution.prerequisite_reads:
        gates.append(PolicyGate(
            gate_type="precondition",
            description=rule["description"],
            action_required="run_read_first",
        ))
    # Verification requirements → verifier_requirements dict
    for vr in constitution.verification_requirements:
        verifier_requirements[vr["operation"]] = vr["method"]
    # HIL gates → hil_triggers
    for gate in constitution.hil_gates:
        hil_triggers.append(gate)
```

**Consumed by VerificationPlanRunner.build_plan():**

```text
# In VerificationPlanRunner.build_plan():
constitution = self.constitution_loader.load(binding.connector_id)
if constitution:
    method = constitution.get_verification_method(operation)
    if method == "read_after_write":
        # Build read_after_write plan using constitution's readback_capability_hint
```

#### 7.6 E2E Data Flow

```text
┌─────────────────────────────────────────────────────────────┐
│ AUTHORING: Connector developer writes constitution           │
│                                                             │
│  Connector author creates a constitution JSON file          │
│  alongside the connector manifest:                          │
│                                                             │
│  calendar.constitution.json:                                │
│  {                                                          │
│    "constitution_id": "const_calendar_v1.0.0",              │
│    "connector_id": "calendar",                              │
│    "schema_version": "1.0.0",                               │
│    "execution_phases": ["grounding", "prerequisite_reads",  │
│      "conflict_analysis", "hil_gating",                     │
│      "coordinated_mutation"],                               │
│    "prerequisite_reads": [                                  │
│      {"description": "List events before create",           │
│       "capability_hint": "list_events",                     │
│       "parallelizable": true, "scope": "self"}              │
│    ],                                                       │
│    "conflict_analysis_rules": [                             │
│      {"rule_id": "dup_check",                               │
│       "predicate": "overlap_time_window",                   │
│       "severity": "blocking"}                               │
│    ],                                                       │
│    "verification_requirements": [                           │
│      {"operation": "create", "method": "read_after_write",  │
│       "readback_capability_hint": "get_event"}              │
│    ],                                                       │
│    "precondition_summary": "Before create: list events to   │
│      check duplicates and conflicts.",                      │
│    "degradation_policy": "block"                            │
│  }                                                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ INGESTION: ConstitutionLoader.upsert()                      │
│                                                             │
│  1. ConstitutionSchema.validate(constitution_dict)          │
│     → JSON Schema validation                                │
│     → Returns [] (no errors)                                │
│                                                             │
│  2. ConstitutionSchema.validate_semantic_rules(dict)        │
│     → prerequisite_reads not empty ✓                        │
│     → execution_phases includes prerequisite_reads ✓        │
│     → verification_requirements has "create" ✓              │
│     → Returns [] (no errors)                                │
│                                                             │
│  3. global_store.upsert_constitution(record)                │
│     → Writes to connector_constitutions table               │
│                                                             │
│  4. Updates in-memory cache                                 │
│     → cache["calendar"] = ConstitutionArtifact(...)         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ RUNTIME: PolicySelector reads constitution                  │
│                                                             │
│  constitution = constitution_loader.load("calendar")        │
│                                                             │
│  → Returns ConstitutionArtifact:                            │
│    prerequisite_reads: [{description: "List events...",     │
│      capability_hint: "list_events", scope: "self"}]        │
│    verification_requirements: [{operation: "create",        │
│      method: "read_after_write"}]                           │
│    hil_gates: [{gate_id: "time_missing", ...}]              │
│    precondition_summary: "Before create: list events to     │
│      check duplicates and conflicts."                       │
│                                                             │
│  PolicySelector uses this to:                               │
│    → Create PolicyGate for each prerequisite_read           │
│    → Populate verifier_requirements dict                    │
│    → Populate hil_triggers list                             │
│    → Render precondition_summary into policy_cards          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ RUNTIME: VerificationPlanRunner reads constitution          │
│                                                             │
│  constitution = constitution_loader.load("calendar")        │
│  method = constitution.get_verification_method("create")    │
│  → "read_after_write"                                       │
│                                                             │
│  Runner builds plan:                                        │
│    verifier_method = "read_after_write"                     │
│    readback_capability_ref = "tool.read.calendar.get_event" │
│    (derived from readback_capability_hint: "get_event")     │
└─────────────────────────────────────────────────────────────┘
```

#### 7.7 Test Coverage

```text
GAP-P1-008: ConnectorConstitution schema + loader tests
  File: tests/k1/fabric/constitution/test_constitution_schema.py

  Test classes:
    TestConstitutionSchemaValidation
      - test_valid_minimal_constitution_passes
      - test_valid_full_constitution_passes
      - test_missing_constitution_id_fails
      - test_missing_connector_id_fails
      - test_invalid_schema_version_format_fails
      - test_empty_prerequisite_reads_for_write_connector_warns
      - test_unknown_execution_phase_fails

    TestSemanticRules
      - test_prerequisite_reads_empty_for_write_capable_warns
      - test_execution_phases_missing_prerequisite_reads_when_declared_fails
      - test_verification_requirements_missing_for_write_operation_warns
      - test_companion_roles_reference_valid_resource_kinds
      - test_mutation_sequencing_depends_on_valid
      - test_constitution_id_includes_connector_prefix

    TestConstitutionLoader
      - test_load_returns_cached_on_second_call
      - test_load_returns_none_for_missing_connector
      - test_upsert_validates_before_writing
      - test_upsert_rejects_invalid_constitution
      - test_invalidate_cache_clears_entry
      - test_invalidate_cache_all_clears_everything
      - test_load_for_operation_filters_correctly

    TestVersionCompatibility
      - test_same_major_version_loads
      - test_different_major_version_logs_warning_and_loads_known_fields
      - test_older_patch_version_loads_normally

    TestPrinciple6Enforcement
      - test_constitution_stored_with_connector_not_prompt
      - test_constitution_loaded_by_connector_id_at_resolution_time
      - test_promptpack_renders_compact_cards_not_raw_artifact
```

---

### Component 8 — PromptPackBuilder

**Target file:** `k1/fabric/prompt_pack/builder.py`
**Source:** Promote + harden from `poc/back_tool_contract_v2/prompt_injection.py` (PromptPackBuilder + render_prompt_pack)
**Depends on:** `GlobalProjectionStore` (C1) — reads capability contracts for schema cards; `ConstitutionLoader` (C7) — reads connector constitutions for constitution cards; `ResolutionEnvelope` (C4) — consumed as input source

#### 8.1 What It Is

The **PromptPack builder** renders the resolution output into a compact, state-specific, LLM-consumable view. It is the physical manifestation of Contract G: the typographic sink between Plane 2/3/4 internals and Plane 1's prompt context. PromptPack is prompt-sized, typed, and disposable — its `source_refs[]` point to authoritative contracts; the pack itself is never execution authority.

This is the component that answers: "What does Back see right now?" It enforces:

- **Staged disclosure (CC-10):** Phase 1 = connector constitutions + tool names + policy cards. Phase 2 = schemas only after Back commits tool names.
- **Redaction proof:** raw catalogs, secrets, provider payloads, and full manifests never cross into model context.
- **Stale card marking:** Side-effecting actions require fresh cards. Stale cards are marked explicitly.
- **Forbidden-action gating:** `forbidden_tool_calls[]` is runtime-enforced by the dispatcher.

In the POC, the primary source is `poc/back_tool_contract_v2/prompt_injection.py` (280 lines) with `PromptPackBuilder`, `PromptPack`, five card dataclasses, `render_prompt_pack()`, and `redaction_check()`. The promotion hardens these into production contract shapes aligned with Contract G.

#### 8.2 Card Types (5 card dataclasses)

These are the atomic units of PromptPack. Each card type has a specific prompt-purpose:

```python
# ── k1/fabric/prompt_pack/builder.py ──────────────────────

@dataclass(frozen=True)
class ConstitutionCard:
    """Per-connector governance: what must happen before/after this connector's tools."""
    connector_id: str
    label: str                           # "Google Calendar"
    precondition_summary: str | None     # "Before create: list events to check conflicts"
    companion_resource_summary: str | None  # "Check participants' calendars, chores"
    hil_trigger_summary: str | None      # "Ask user if: time missing, conflict exists"
    verification_requirement: str | None # "After create: read-back event to confirm"
    degradation_policy: str | None       # "block" | "allow_degraded_completion" | "ask_hil"


@dataclass(frozen=True)
class ToolNameCard:
    """A capability available for invocation — name + role only, NO schema."""
    capability_name: str                 # "tool.execute.calendar.create_event"
    description: str                     # "Create a calendar event for a person"
    role: str                            # "prerequisite_read" | "primary_read" | "primary_write" | "verifier"
    safety_band_min: str                 # "GREEN" | "AMBER" | "RED"
    effect: str                          # "read" | "write" | "delete" | "compute"
    connector_id: str                    # which connector this capability belongs to


@dataclass(frozen=True)
class PolicyCard:
    """Cross-connector governance: what is required, what triggers HIL, what is denied."""
    connector_id: str
    what_is_required: str                # "Parent or guardian role required for scheduling"
    what_triggers_hil: list[str]         # ["time_missing", "conflict_detected", "guardian_impact"]
    what_is_denied: list[str]            # ["Guest cannot create events", "Child requires guardian"]
    actor_role: str                      # the role this policy was evaluated for
    safety_band: str                     # the safety band this policy was evaluated under


@dataclass(frozen=True)
class GuideCard:
    """Usage guidance — patterns, examples, parameter hints. NEVER execution authority."""
    guide_id: str
    title: str                           # "How to use ISO 8601 dates"
    content: str                         # "Always use YYYY-MM-DDTHH:MM:SS±HH:MM format"
    relevance: str                       # "calendar_create" — which operations this applies to


@dataclass(frozen=True)
class SchemaCard:
    """Full JSON Schema for a committed tool. DISCLOSED ONLY AFTER Back commits tool names."""
    capability_name: str
    binding_id: str
    input_schema: dict                   # full JSON Schema for input params
    required_fields: list[str]           # required input field names
    optional_fields: list[str]           # optional input field names
    output_schema_ref: str | None        # reference to output schema
```

#### 8.3 PromptPack Dataclass (Contract G shape)

```python
@dataclass(frozen=True)
class RedactionEvidence:
    """Proof that restricted artifacts did not cross into model context."""
    redaction_id: str
    prompt_hash: str                     # SHA-256 of the prompt-visible pack content
    fields_redacted: list[str]           # fields that were redacted before model context
    fields_verified_absent: list[str]    # fields confirmed absent from prompt
    prompt_visible_leak_count: int       # must be 0 for pass
    verdict: str                         # "pass" | "fail"


@dataclass(frozen=True)
class PromptPack:
    """Contract G: compact, typed, state-specific view for Back LLM. Prompt-sized. Disposable."""
    prompt_pack_id: str
    react_state: str                     # "initial" | "waiting_prerequisites" | "ready_for_write" | "needs_hil" | "blocked" | "complete"
    target_tier: str                     # "tier2" | "tier3" | "unknown"
    disclosure_phase: str                # "connector_summary" | "tool_name_selection" | "schema_binding" | "execution"
    source_refs: list[str]               # [resolution_id, request_id, binding_bundle_ref, policy_bundle_ref]
    source_versions: dict[str, str]      # {"resolution_envelope": "v2", "prompt_pack": "v1"}
    candidate_summary: dict              # compact resource+person summary
    connector_constitution_cards: list[ConstitutionCard]
    tool_name_cards: list[ToolNameCard]
    policy_cards: list[PolicyCard]
    guide_cards: list[GuideCard]
    selected_schema_cards: list[SchemaCard]  # empty at Phase 1, populated at Phase 2+
    contract_cards: list[dict]           # compact contract refs (not full manifests)
    decision_surface: str                # human-readable: "You can: invoke binding X, ask HIL, refresh Y, or submit blocked"
    uncertainty_markers: list[str]       # "Could not resolve 'Aunt Sarah' — ask user"
    omission_summary: str                # "3 connectors omitted: insufficient safety band"
    option_budget: int                   # remaining tool calls allowed
    context_load_shedding_summary: str | None  # what was trimmed from context, if any
    allowed_tool_calls: list[str]        # capability names Back CAN invoke
    forbidden_tool_calls: list[str]      # capability names Back MUST NOT invoke (runtime-enforced)
    allowed_next_actions: list[str]      # human-readable action descriptions
    forbidden_next_actions: list[str]    # human-readable blocked action descriptions
    hil_options: list[dict] | None       # HIL questions from CandidateUniverse
    stale_card_policy: str               # "strict" | "warn" | "allow_reads"
    redaction_summary: RedactionEvidence
    output_schema: dict                  # the schema of THIS PromptPack (for tool output parsing)
    max_tool_calls: int                  # hard limit on concurrent tool calls
    expires_at: str                      # ISO 8601, 5-minute TTL
```

#### 8.4 Public API

```python
class PromptPackBuilder:
    """Renders ResolutionEnvelope → PromptPack per Contract G.
    Enforces staged disclosure (CC-10) and redaction proof."""

    def __init__(
        self,
        global_store: GlobalProjectionStore,
        constitution_loader: ConstitutionLoader | None = None,
    ) -> None: ...

    def build(
        self,
        resolution_envelope: ResolutionEnvelope,
        *,
        disclosure_phase: str,                       # "connector_summary" | "tool_name_selection" | "schema_binding" | "execution"
        prompt_budget_tokens: int = 8000,
        committed_tool_names: list[str] | None = None,  # required for schema_binding+
        max_tool_calls: int = 5,
        stale_card_policy: str = "strict",
    ) -> PromptPack:
        """Main entry. Builds a phase-appropriate PromptPack from a resolution envelope.

        Raises:
            PromptPackPhaseError: if disclosure_phase is invalid or requires committed_tool_names
            PromptPackLeakError: if redaction check fails (restricted fields detected in prompt content)
        """


# ── Renderer (separate function, not a class method) ──────

def render_prompt_pack(pack: PromptPack) -> str:
    """Render a PromptPack to markdown text for LLM injection.
    Compact, typed, no raw JSON dumps of contracts."""
```

#### 8.5 Internal Design

**Phase-aware field selection (PHASE_ALLOWED_FIELDS):**

```text
loop_start:          [candidate_summary, uncertainty_markers, option_budget, decision_surface]
connector_summary:   [connector_constitution_cards, tool_name_cards, policy_cards, guide_cards,
                      candidate_summary, omission_summary, allowed_next_actions,
                      forbidden_next_actions, decision_surface, uncertainty_markers,
                      option_budget, hil_options]
tool_name_selection: [tool_name_cards, allowed_next_actions, decision_surface, hil_options]
schema_binding:      [selected_schema_cards, allowed_tool_calls]
execution:           [allowed_tool_calls, allowed_next_actions, option_budget]
```

Each phase gets an `_apply_phase(pack, disclosure_phase)` call that zeroes out fields not allowed at that phase. This is a defense-in-depth layer: even if the builder accidentally populates schema cards at Phase 1, `_apply_phase` strips them before `redaction_check()`.

**Card construction pipeline (build order):**

```text
1. Redaction gate: redaction_check(resolution_envelope.to_dict())
   → Blocks if any SECRET_MARKERS appear in content headed to prompt.
   → This runs BEFORE any card construction — fail fast.

2. Candidate summary: compact dict of resolved resources + persons.
   → From ResourceUniverse.resource_candidates + person_candidates.
   → Fields: label, kind, freshness, permission, role.

3. Constitution cards: one per connector in scope.
   → ConstitutionLoader.load(connector_id) for each candidate's connector.
   → Renders compact text cards, NOT raw JSON artifacts.

4. Tool name cards: from BindingBundle.bindings.
   → capability_name, description, role, safety_band, effect, connector_id.
   → NO schemas. Schema cards are built separately.

5. Policy cards: from PolicyBundle.
   → what_is_required (from gates), what_triggers_hil (from hil_triggers),
     what_is_denied (from deny_reason if denied, else empty).

6. Guide cards: from GlobalProjectionStore guide inventory.
   → Filtered by connector_id + operation relevance.

7. Schema cards (Phase 2+ only): from GlobalProjectionStore + BindingBundle.
   → Built ONLY for committed_tool_names that match a binding.
   → Contains full JSON Schema input shapes.

8. Decision surface: human-readable prose from verdict + allowed_next_actions.

9. Uncertainty markers: from unresolved refs, ambiguous persons, stale projections.

10. Omission summary: what was excluded and why (connectors below band, etc.).

11. Redaction evidence: SHA-256 of prompt-visible content, verified-absent fields, leak count.

12. Phase application: _apply_phase() zeros out non-phase fields.

13. Final redaction check: on the phase-applied dict — must pass before returning.
```

**Redaction enforcement (what must never reach the LLM):**

```text
SECRET_MARKERS (from POC proof.py):
  - "raw_catalog_results"        — full FTS5 search hits, not compact cards
  - "connector_credentials"      — API keys, OAuth tokens
  - "provider_payload"           — raw provider response bodies
  - "full_manifest"              — complete IFL manifests
  - "policy_machinery"           — internal policy evaluation state
  - "restricted_prompt_fields"   — catch-all for fields marked restricted
  - "constitution_json"          — raw constitution JSON (only compact cards allowed)

REDACTION_CHECK (recursive dict walk):
  Traverses every key in the pack dict.
  Any key containing a SECRET_MARKER substring → verdict="fail".
  All clear → verdict="pass".
```

**Stale card policy:**

```text
"strict" (default):
  - Write bindings with stale projection → marked in forbidden_tool_calls[].
  - Read bindings with stale projection → allowed but marked.
  - Stale marker included in tool_name_cards (role suffix: "_stale").

"warn":
  - Stale cards included with staleness noted in decision_surface.
  - Back is warned but not blocked.

"allow_reads":
  - Only writes with stale projection are blocked.
  - Reads always allowed with freshness warnings.
```

**Disclosure phase enforcement (CC-10 in code):**

```text
Phase "connector_summary":
  → connector_constitution_cards populated (compact summaries, not raw JSON)
  → tool_name_cards populated (names + descriptions, no schemas)
  → policy_cards populated
  → guide_cards populated
  → selected_schema_cards EMPTY

Phase "tool_name_selection":
  → Back receives tool_name_cards + decision_surface
  → Back commits: committed_tool_names = ["tool.execute.calendar.create_event", ...]
  → Builder validates all committed names exist in tool_name_cards

Phase "schema_binding":
  → REQUIRES committed_tool_names (raises PromptPackPhaseError if missing)
  → selected_schema_cards populated ONLY for committed names
  → New resolution_envelope built with committed tools
  → allowed_tool_calls populated from committed bindings

Phase "execution":
  → allowed_tool_calls present (from prior schema_binding phase)
  → allowed_next_actions reflect current state
  → option_budget reflects remaining calls
```

#### 8.6 Wiring — Where It Hooks Into Fabric

**Created in FabricFactory:**

```text
# FabricFactory:
prompt_pack_builder = PromptPackBuilder(
    global_store=global_projection_store,
    constitution_loader=constitution_loader,
)

# Injected into:
situated_resolver = SituatedResolver(
    ...,
    prompt_pack_builder=prompt_pack_builder,  # builds PromptPack at step 6
)
```

**Called by SituatedResolver at Step 6:**

```text
# Inside SituatedResolver.resolve():
prompt_pack = self.prompt_pack_builder.build(
    resolution_envelope=ResolutionEnvelope(...),  # being constructed
    disclosure_phase=request.disclosure_phase,
    prompt_budget_tokens=request.prompt_budget,
    committed_tool_names=request.committed_tool_names,
)
```

**Consumed by resolve_situation tool handler:**

```text
# In execute_resolve_situation() (k1/fabric/tools/resolve_situation_handler.py):
resolution = situated_resolver.resolve(request)
prompt_pack = prompt_pack_builder.build(
    resolution,
    disclosure_phase=disclosure_phase,
    committed_tool_names=committed_tool_names,
)
# prompt_pack is returned in the ToolResult data, then injected into Back's prompt
# by the concierge prompt builder at the appropriate CC-10 phase
```

**Back prompt injection (CC-10 schedule):**

```text
loop_start:
  Back receives: meta-tool declarations + execution_grounding_block

after_resolution (connector_summary phase):
  Back receives: render_prompt_pack(pack) → constitution cards, tool names, policy cards,
  guide cards, candidate summary, decision surface
  NO schemas, NO raw contracts

after_tool_commitment (schema_binding phase):
  Back receives: render_prompt_pack(pack) → selected_schema_cards for committed tools ONLY

after_invocation (execution phase):
  Back receives: invocation observations + refreshed prompt pack
```

#### 8.7 E2E Data Flow

```text
┌─────────────────────────────────────────────────────────────┐
│ SituatedResolver.resolve() — Step 6                         │
│                                                             │
│  After verdict = "can_execute_with_gate":                    │
│                                                             │
│  prompt_pack_builder.build(                                 │
│      resolution_envelope=envelope,                          │
│      disclosure_phase="connector_summary",                  │
│      prompt_budget_tokens=8000,                             │
│  )                                                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ PromptPackBuilder.build()                                   │
│                                                             │
│  Step 1 — Redaction gate:                                   │
│    redaction_check(envelope.to_dict())                      │
│    → verdict="pass" ✓                                       │
│                                                             │
│  Step 2 — Candidate summary:                                │
│    candidate_summary = {                                    │
│      "resources": [{                                        │
│        "label": "Riley's Google Calendar",                  │
│        "kind": "calendar.primary",                          │
│        "freshness": "fresh",                                │
│        "permission": "read_write"                           │
│      }],                                                    │
│      "persons": [{                                          │
│        "label": "Riley",                                    │
│        "role": "child",                                     │
│        "linked_resources": ["calendar", "chores"]           │
│      }]                                                     │
│    }                                                        │
│                                                             │
│  Step 3 — Constitution cards:                               │
│    constitution_loader.load("calendar")                     │
│    → ConstitutionCard(                                      │
│        connector_id="calendar",                             │
│        label="Calendar",                                    │
│        precondition_summary="Before create: list events to  │
│          check duplicates and conflicts.",                  │
│        companion_resource_summary="Check participants'      │
│          calendars, chores, and caregiver schedules.",      │
│        hil_trigger_summary="Ask user if: time missing,      │
│          conflict exists, or affects guardians.",           │
│        verification_requirement="After create: read-back    │
│          event via get_event.",                             │
│        degradation_policy="block"                           │
│      )                                                      │
│                                                             │
│  Step 4 — Tool name cards:                                  │
│    For each binding in binding_bundle.bindings:             │
│    → ToolNameCard(                                          │
│        capability_name="tool.read.calendar.list_events",    │
│        description="List calendar events in a time window", │
│        role="prerequisite_read",                            │
│        safety_band_min="GREEN",                              │
│        effect="read"                                        │
│      )                                                      │
│    → ToolNameCard(                                          │
│        capability_name="tool.execute.calendar.create_event",│
│        description="Create a calendar event",               │
│        role="primary_write",                                │
│        safety_band_min="GREEN",                              │
│        effect="write"                                       │
│      )                                                      │
│    → ToolNameCard(                                          │
│        capability_name="tool.read.calendar.get_event",      │
│        description="Get a calendar event by ID",            │
│        role="verifier",                                     │
│        safety_band_min="GREEN",                              │
│        effect="read"                                        │
│      )                                                      │
│                                                             │
│  Step 5 — Policy cards:                                     │
│    → PolicyCard(                                            │
│        connector_id="calendar",                             │
│        what_is_required="Parent or guardian role for write",│
│        what_triggers_hil=["time_missing", "conflict_        │
│          detected", "guardian_impact"],                     │
│        what_is_denied=[],                                   │
│        actor_role="parent",                                 │
│        safety_band="GREEN"                                   │
│      )                                                      │
│                                                             │
│  Step 6 — Guide cards:                                      │
│    global_store.get_guides_by_connector("calendar")         │
│    → GuideCard(title="How to format dates", ...)            │
│                                                             │
│  Step 7 — Schema cards:                                     │
│    disclosure_phase="connector_summary"                     │
│    → selected_schema_cards = []  (NO schemas at Phase 1!)  │
│                                                             │
│  Step 8 — Decision surface:                                 │
│    verdict="can_execute_with_gate"                          │
│    → "You must first run the prerequisite read 'list_events'│
│       before you can create the event. After the read, call │
│       resolve_situation again with the completed binding."  │
│                                                             │
│  Step 9 — Uncertainty markers:                              │
│    → [] (all refs resolved)                                 │
│                                                             │
│  Step 10 — Omission summary:                                │
│    → "" (nothing omitted from scope)                        │
│                                                             │
│  Step 11 — Allowed/forbidden tool calls:                    │
│    Allowed: ["tool.read.calendar.list_events"]              │
│             (prereq only — write blocked until completed)   │
│    Forbidden: ["tool.execute.calendar.create_event"]        │
│             (cannot invoke write before prereq done)        │
│                                                             │
│  Step 12 — Phase application:                               │
│    _apply_phase(pack, "connector_summary")                  │
│    → selected_schema_cards zeroed out                       │
│    → contract_cards zeroed out                              │
│                                                             │
│  Step 13 — Redaction check:                                 │
│    redaction_check(phase_applied_dict)                      │
│    → verdict="pass" ✓                                       │
│                                                             │
│  Returns PromptPack with compact cards, NO raw JSON.        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Back prompt injection (concierge/prompt/back_prompt.py)     │
│                                                             │
│  rendered = render_prompt_pack(pack)                        │
│                                                             │
│  ## Situated Execution Update                               │
│  Phase: connector_summary                                   │
│                                                             │
│  ## Candidate Summary                                       │
│  - Riley's Google Calendar (calendar, fresh, read_write)    │
│  - Riley (child, linked: calendar, chores)                  │
│                                                             │
│  ## Connector Guide: Calendar                               │
│  Before create: list events to check duplicates and         │
│    conflicts.                                               │
│  Check: participants' calendars, chores, caregiver          │
│    schedules.                                               │
│  Ask user if: time missing, conflict exists, or affects     │
│    guardians.                                               │
│  After create: read-back event via get_event.               │
│                                                             │
│  ## Available Actions                                       │
│  - list_events (prerequisite_read): List calendar events    │
│  - create_event (primary_write): Create a calendar event    │
│  - get_event (verifier): Get a calendar event by ID         │
│                                                             │
│  ## Decision Surface                                        │
│  You must first run the prerequisite read 'list_events'     │
│  before you can create the event.                           │
│                                                             │
│  ## Allowed Next Actions                                    │
│  - Run prerequisite: tool.read.calendar.list_events         │
│                                                             │
│  ## Forbidden                                              │
│  - DO NOT call create_event before completing list_events   │
│                                                             │
│  → Back now knows exactly what it can do, with constitution │
│    guidance, NO schemas, NO raw contracts, NO secrets.      │
└─────────────────────────────────────────────────────────────┘
```

**Phase 2 flow — Back commits tools, gets schemas:**

```text
Back calls resolve_situation(
    disclosure_phase="schema_binding",
    committed_tool_names=["tool.execute.calendar.create_event"],
)

→ PromptPackBuilder.build():
    disclosure_phase="schema_binding"
    committed_tool_names=["tool.execute.calendar.create_event"]

    Step 7 — Schema cards:
      capability = global_store.get_capability("tool.execute.calendar.create_event")
      → SchemaCard(
          capability_name="tool.execute.calendar.create_event",
          binding_id="bind_create_riley_001",
          input_schema={... full JSON Schema ...},
          required_fields=["title", "start", "end", "resource_id"],
          optional_fields=["description", "location", "attendees"],
          output_schema_ref="calendar_event_output_v1",
        )

    Phase application:
      → selected_schema_cards has 1 card (committed tool only)
      → connector_constitution_cards EMPTY (already disclosed)
      → tool_name_cards EMPTY (already disclosed)
      → Allowed tool calls: ["tool.execute.calendar.create_event"]
```

#### 8.8 Test Coverage

```text
GAP-P1-011: PromptPackBuilder contract tests
  File: tests/k1/fabric/prompt_pack/test_prompt_pack_builder.py

  Test classes:
    TestPromptPackShape
      - test_prompt_pack_matches_contract_g_shape
      - test_all_required_fields_present
      - test_source_refs_point_to_authoritative_contracts
      - test_prompt_pack_is_not_execution_authority

    TestStagedDisclosure (CC-10)
      - test_connector_summary_has_constitution_cards
      - test_connector_summary_has_tool_name_cards
      - test_connector_summary_has_NO_schema_cards
      - test_connector_summary_has_NO_contract_cards
      - test_schema_binding_requires_committed_tool_names
      - test_schema_binding_produces_schema_cards_for_committed_only
      - test_schema_binding_produces_NO_schema_cards_for_uncommitted
      - test_execution_has_allowed_tool_calls

    TestRedactionProof
      - test_redaction_check_blocks_raw_catalog_results
      - test_redaction_check_blocks_connector_credentials
      - test_redaction_check_blocks_provider_payload
      - test_redaction_check_blocks_full_manifest
      - test_redaction_check_blocks_constitution_json
      - test_redaction_evidence_has_zero_leak_count_on_pass
      - test_prompt_hash_is_stable_for_same_input
      - test_leak_detected_fails_build

    TestConstitutionCards
      - test_constitution_card_uses_compact_summary_not_raw_json
      - test_constitution_card_includes_precondition_summary
      - test_constitution_card_includes_companion_resource_summary
      - test_constitution_card_includes_verification_requirement
      - test_constitution_card_includes_degradation_policy

    TestToolNameCards
      - test_tool_name_card_has_no_schema
      - test_tool_name_card_has_role
      - test_tool_name_card_has_safety_band_min
      - test_tool_name_card_has_effect

    TestPolicyCards
      - test_policy_card_reflects_gates
      - test_policy_card_reflects_hil_triggers
      - test_policy_card_reflects_deny_reason
      - test_policy_card_includes_actor_role_and_safety_band

    TestStaleCardPolicy
      - test_strict_policy_blocks_stale_write_cards
      - test_strict_policy_allows_stale_read_cards
      - test_warn_policy_marks_stale_but_allows
      - test_allow_reads_policy_blocks_stale_writes_only
      - test_stale_card_marker_in_tool_name_cards

    TestForbiddenActionGating
      - test_forbidden_tool_calls_includes_stale_writes
      - test_forbidden_tool_calls_includes_policy_denied
      - test_forbidden_tool_calls_includes_band_insufficient
      - test_forbidden_next_actions_describes_why_forbidden

    TestRendering
      - test_render_prompt_pack_produces_markdown
      - test_render_includes_verdict_and_phase
      - test_render_includes_constitution_guidance
      - test_render_includes_available_actions
      - test_render_includes_decision_surface
      - test_render_includes_forbidden_section
      - test_render_omits_selected_schema_cards_at_phase_1

    TestPromptPackBuilderEdgeCases
      - test_build_with_no_connector_constitution_graceful
      - test_build_with_no_guide_cards_graceful
      - test_build_with_empty_candidate_universe
      - test_build_with_blocked_by_policy_verdict
      - test_build_with_cannot_execute_verdict
      - test_build_respects_prompt_budget_tokens
```

---

### Component 9 — CapabilityNameParser

**Target file:** `k1/fabric/resolver/name_parser.py`
**Source:** New implementation — Contract D enforcement. POC uses inline string splitting (`tool.read.calendar.list_events` → connector_id extraction at positions); this formalizes it into a reusable parser.
**Depends on:** Nothing (standalone utility — pure string parsing, no store access)

#### 9.1 What It Is

The **capability name parser** is the single authority for parsing, validating, and constructing capability names in the `tool.{read|execute}.{connector_id}.{action}` format. It enforces Contract D's naming convention: capability names embed connector identity, and the format itself is the collision prevention mechanism — no two admitted connectors may share a `connector_id` because the capability name embeds it structurally.

This is a tiny but load-bearing utility. Every component that reads or constructs capability names — `SituatedResolver`, `PolicySelector`, `CapabilityBinder`, `VerificationPlanRunner`, `PromptPackBuilder`, `NativeToolProvider`, and Back's tool dispatcher — depends on the naming convention. Centralizing the parse/validate/construct logic prevents drift.

In the current code, capability names are constructed via string concatenation (`"tool.read." + connector_id + "." + action`) and parsed via ad-hoc `.split(".")` calls scattered across multiple files. There is no validation that a name conforms to the convention before it enters the registry, and no single place that defines the grammar.

#### 9.2 Capability Name Grammar

```text
CAPABILITY_NAME ::= "tool." OPERATION_TYPE "." CONNECTOR_ID "." ACTION

OPERATION_TYPE ::= "read" | "execute"

CONNECTOR_ID ::= [a-z][a-z0-9_]*    -- lowercase alphanumeric + underscores, starts with letter
                                     -- Must match a registered connector_id in GlobalProjectionStore

ACTION ::= [a-z][a-z0-9_]*           -- lowercase alphanumeric + underscores, starts with letter
                                     -- Examples: "list_events", "create_event", "get_event",
                                     -- "search", "delete", "update", "cancel"

FULLY_QUALIFIED ::= CAPABILITY_NAME   -- exactly 4 segments, dot-separated
```

**Examples of valid names:**

```text
tool.read.calendar.list_events          # Read capability: connector=calendar, action=list_events
tool.execute.calendar.create_event      # Execute capability: connector=calendar, action=create_event
tool.read.tasks.list                    # Read capability: connector=tasks, action=list
tool.execute.shopping.create_item       # Execute capability: connector=shopping, action=create_item
tool.read.google_calendar_read.search   # Read capability (bridge connector with compound name)
tool.execute.appointment_book.create    # Write capability (IFL connector)
```

**Examples of invalid names:**

```text
read.calendar.list_events               # Missing "tool." prefix
tool.read.calendar                      # Too few segments (need 4)
tool.write.calendar.create_event        # Invalid operation_type (must be "read" or "execute")
tool.read.CALENDAR.list_events          # Uppercase connector_id
tool.read.calendar.ListEvents           # Uppercase action
tool.execute..create_event              # Empty connector_id
tool.read.calendar.create event         # Space in action
tool.execute.calendar.create_event.     # Trailing dot
```

#### 9.3 Public API

```python
# ── k1/fabric/resolver/name_parser.py ──────────────────────

@dataclass(frozen=True)
class ParsedCapabilityName:
    """Result of parsing a capability name."""
    raw: str                            # original string
    operation_type: str                 # "read" | "execute"
    connector_id: str                   # extracted connector_id
    action: str                         # extracted action


class CapabilityNameParser:
    """Single authority for capability name parsing, validation, and construction.
    Enforces Contract D naming convention."""

    # ── Grammar constants ─────────────────────────────────
    VALID_OPERATION_TYPES = frozenset({"read", "execute"})
    SEGMENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")  # connector_id + action segments

    # ── Parse ─────────────────────────────────────────────
    @classmethod
    def parse(cls, name: str) -> ParsedCapabilityName:
        """Parse a capability name into its 4 segments.

        Raises:
            InvalidCapabilityNameError: if the name doesn't match the grammar.
            Returns ParsedCapabilityName on success.
        """

    @classmethod
    def try_parse(cls, name: str) -> ParsedCapabilityName | None:
        """Non-raising variant. Returns None if invalid."""

    # ── Validate ───────────────────────────────────────────
    @classmethod
    def is_valid(cls, name: str) -> bool:
        """True if the name conforms to the grammar (segments, types, patterns)."""

    @classmethod
    def validate(cls, name: str) -> list[str]:
        """Returns list of validation error messages (empty = valid).

        Checks:
          1. Exactly 4 dot-separated segments
          2. Segment 0 == "tool"
          3. Segment 1 in {"read", "execute"}
          4. Segment 2 matches SEGMENT_PATTERN (connector_id)
          5. Segment 3 matches SEGMENT_PATTERN (action)
        """

    # ── Extract ────────────────────────────────────────────
    @classmethod
    def extract_connector_id(cls, name: str) -> str:
        """Extract connector_id from a capability name. Raises if invalid."""

    @classmethod
    def extract_action(cls, name: str) -> str:
        """Extract action from a capability name. Raises if invalid."""

    @classmethod
    def extract_operation_type(cls, name: str) -> str:
        """Extract operation_type ("read" or "execute"). Raises if invalid."""

    # ── Construct ──────────────────────────────────────────
    @classmethod
    def build(
        cls,
        operation_type: str,              # "read" | "execute"
        connector_id: str,
        action: str,
    ) -> str:
        """Construct a valid capability name from parts.

        Raises ValueError if any component is invalid.
        Returns e.g. "tool.read.calendar.list_events"
        """

    # ── Domain queries ─────────────────────────────────────
    @classmethod
    def is_read(cls, name: str) -> bool:
        """True if operation_type == "read"."""

    @classmethod
    def is_write(cls, name: str) -> bool:
        """True if operation_type == "execute"."""

    @classmethod
    def belongs_to_connector(cls, name: str, connector_id: str) -> bool:
        """True if the capability name's connector_id matches."""

    # ── Bulk operations ────────────────────────────────────
    @classmethod
    def filter_by_connector(
        cls,
        names: list[str],
        connector_id: str,
        *,
        operation_type: str | None = None,  # optionally filter to "read" or "execute"
    ) -> list[str]:
        """Return only names that belong to the given connector."""

    @classmethod
    def group_by_connector(
        cls,
        names: list[str],
    ) -> dict[str, list[str]]:
        """Group capability names by connector_id. Invalid names are skipped with warning."""

    @classmethod
    def connectors_in_scope(cls, names: list[str]) -> set[str]:
        """Return the set of unique connector_ids across all names."""
```

#### 9.4 Internal Design

**Parsing algorithm (single-pass split):**

```text
parse(name):
  segments = name.split(".")
  if len(segments) != 4:
      raise InvalidCapabilityNameError(name, "expected 4 segments, got {len}")
  prefix, op_type, connector_id, action = segments
  if prefix != "tool":
      raise InvalidCapabilityNameError(name, "segment 0 must be 'tool'")
  if op_type not in VALID_OPERATION_TYPES:
      raise InvalidCapabilityNameError(name, "segment 1 must be 'read' or 'execute'")
  if not SEGMENT_PATTERN.match(connector_id):
      raise InvalidCapabilityNameError(name, "segment 2 must match [a-z][a-z0-9_]*")
  if not SEGMENT_PATTERN.match(action):
      raise InvalidCapabilityNameError(name, "segment 3 must match [a-z][a-z0-9_]*")
  return ParsedCapabilityName(
      raw=name,
      operation_type=op_type,
      connector_id=connector_id,
      action=action,
  )
```

**Construction algorithm:**

```text
build(op_type, connector_id, action):
  if op_type not in VALID_OPERATION_TYPES:
      raise ValueError(f"operation_type must be 'read' or 'execute', got '{op_type}'")
  if not SEGMENT_PATTERN.match(connector_id):
      raise ValueError(f"connector_id must match [a-z][a-z0-9_]*, got '{connector_id}'")
  if not SEGMENT_PATTERN.match(action):
      raise ValueError(f"action must match [a-z][a-z0-9_]*, got '{action}'")
  return f"tool.{op_type}.{connector_id}.{action}"
```

**Collision prevention (Contract D):** Two connectors with the same `connector_id` would produce capability names that collide. The name parser itself doesn't prevent this — it's the `GlobalProjectionStore.upsert_connector()` that rejects duplicate `connector_id` values (PRIMARY KEY constraint). The parser ensures the format is correct; the store ensures uniqueness is enforced.

**Why this is a class (static methods) not a module of functions:** All methods are `@classmethod` — no instance state. The class serves as a namespace that groups the grammar, parse, validate, construct, and query operations. This makes it injectable as a dependency (e.g., `policy_selector = PolicySelector(..., name_parser=CapabilityNameParser)`) if needed, though most consumers will call `CapabilityNameParser.parse()` directly.

#### 9.5 Wiring — Where It's Used

```text
Used BY:
  CapabilityBinder.bind()
    → Parses capability names from GlobalProjectionStore to build tool_name_cards
    → Groups capabilities by connector_id for constitution binding

  PolicySelector.select()
    → Extracts connector_id from candidate capability names
    → Validates capability names before safety band comparison

  VerificationPlanRunner.build_plan()
    → Parses binding.capability_name to construct readback_capability_ref
    → "tool.execute.calendar.create_event" → connector_id="calendar"
    → Builds: "tool.read.calendar.get_event" from connector_id + verifier action

  PromptPackBuilder.build()
    → Parses tool name cards to group by connector for constitution cards
    → Validates committed_tool_names against grammar before schema disclosure

  NativeToolProvider.dispatch()
    → Parses capability_name to route to the correct tool handler
    → "tool.read.calendar.list_events" → handler="calendar", method="list_events"

  CapabilityRegistry (registration validation)
    → NEW: before registering a capability, validates the capability_name against the grammar
    → Prevents malformed names from entering the registry

  ManifestTranslator.translate()
    → Validates that generated capability names conform to the convention
    → Ensures IFL→Fabric capability names are well-formed

  Back tool dispatcher
    → Validates that Back's tool calls use well-formed capability names
    → Rejects invented/abbreviated names early
```

#### 9.6 E2E Data Flow

```text
┌─────────────────────────────────────────────────────────────┐
│ CONSTRUCTION: CapabilityBinder builds a capability name     │
│                                                             │
│  CapabilityNameParser.build(                                │
│      operation_type="read",                                 │
│      connector_id="calendar",                               │
│      action="list_events",                                  │
│  )                                                          │
│  → "tool.read.calendar.list_events"                         │
│                                                             │
│  Validated:                                                 │
│    ✓ operation_type in {"read", "execute"}                  │
│    ✓ connector_id matches [a-z][a-z0-9_]*                   │
│    ✓ action matches [a-z][a-z0-9_]*                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PARSING: VerificationPlanRunner builds readback ref         │
│                                                             │
│  parsed = CapabilityNameParser.parse(                       │
│      "tool.execute.calendar.create_event"                   │
│  )                                                          │
│  → ParsedCapabilityName(                                    │
│      raw="tool.execute.calendar.create_event",              │
│      operation_type="execute",                              │
│      connector_id="calendar",                               │
│      action="create_event"                                  │
│    )                                                        │
│                                                             │
│  readback_ref = CapabilityNameParser.build(                 │
│      operation_type="read",                                 │
│      connector_id=parsed.connector_id,  # "calendar"        │
│      action="get_event",                                    │
│  )                                                          │
│  → "tool.read.calendar.get_event"                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ GROUPING: PolicySelector groups by connector                │
│                                                             │
│  names = [                                                   │
│      "tool.read.calendar.list_events",                      │
│      "tool.execute.calendar.create_event",                  │
│      "tool.read.calendar.get_event",                        │
│      "tool.read.tasks.list",                                │
│  ]                                                          │
│                                                             │
│  CapabilityNameParser.group_by_connector(names)             │
│  → {                                                        │
│      "calendar": [                                          │
│          "tool.read.calendar.list_events",                  │
│          "tool.execute.calendar.create_event",              │
│          "tool.read.calendar.get_event",                    │
│      ],                                                     │
│      "tasks": ["tool.read.tasks.list"],                     │
│    }                                                        │
│                                                             │
│  CapabilityNameParser.connectors_in_scope(names)            │
│  → {"calendar", "tasks"}                                    │
│                                                             │
│  SituatedResolver uses this to detect cross-connector tasks │
│  → len(connectors) > 1 → promote_to_tier3                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ VALIDATION: Registry rejects malformed names                │
│                                                             │
│  CapabilityNameParser.validate("calendar.list_events")      │
│  → ["expected 4 segments, got 3",                           │
│     "segment 0 must be 'tool'"]                             │
│                                                             │
│  CapabilityNameParser.validate("tool.write.calendar.create")│
│  → ["segment 1 must be 'read' or 'execute'"]                │
│                                                             │
│  CapabilityNameParser.validate("tool.read.CALENDAR.list")   │
│  → ["segment 2 must match [a-z][a-z0-9_]*"]                 │
│                                                             │
│  All rejected before entering CapabilityRegistry.           │
└─────────────────────────────────────────────────────────────┘
```

#### 9.7 Test Coverage

```text
GAP-P1-012: CapabilityNameParser unit tests
  File: tests/k1/fabric/resolver/test_capability_name_parser.py

  Test classes:
    TestParse
      - test_parse_valid_read_name
      - test_parse_valid_execute_name
      - test_parse_name_with_compound_connector_id
      - test_parse_name_with_underscore_action
      - test_parse_returns_all_four_segments
      - test_parse_raises_on_too_few_segments
      - test_parse_raises_on_too_many_segments
      - test_parse_raises_on_missing_tool_prefix
      - test_parse_raises_on_invalid_operation_type
      - test_parse_raises_on_uppercase_connector_id
      - test_parse_raises_on_uppercase_action
      - test_parse_raises_on_empty_connector_id
      - test_parse_raises_on_space_in_action

    TestTryParse
      - test_try_parse_valid_returns_parsed
      - test_try_parse_invalid_returns_none

    TestValidate
      - test_validate_valid_returns_empty_list
      - test_validate_invalid_returns_error_messages
      - test_validate_missing_segment_reports_correct_index
      - test_validate_invalid_operation_type_reports_allowed_values

    TestExtract
      - test_extract_connector_id
      - test_extract_action
      - test_extract_operation_type
      - test_extract_connector_id_raises_on_invalid

    TestBuild
      - test_build_produces_correct_format
      - test_build_roundtrip_parse_build
      - test_build_raises_on_invalid_operation_type
      - test_build_raises_on_invalid_connector_id
      - test_build_raises_on_invalid_action

    TestDomainQueries
      - test_is_read_returns_true_for_read
      - test_is_read_returns_false_for_execute
      - test_is_write_returns_true_for_execute
      - test_belongs_to_connector_true
      - test_belongs_to_connector_false

    TestBulkOperations
      - test_filter_by_connector_returns_only_matching
      - test_filter_by_connector_and_operation_type
      - test_group_by_connector_groups_correctly
      - test_group_by_connector_skips_invalid_with_warning
      - test_connectors_in_scope_returns_unique_set
      - test_connectors_in_scope_empty_list_returns_empty_set
```

---

### Component 10 — ConnectorAliasNormalizer

**Target file:** `k1/fabric/stores/alias_normalizer.py`
**Source:** New implementation — formalizes the scattered alias logic from POC `connectors/catalog.py` (LABELS dict + RESOURCE_KIND_BY_CONNECTOR) + `LocalProjectionStore.alias_index`.
**Depends on:** `GlobalProjectionStore` (C1) — reads connector labels; `LocalProjectionStore` (C2) — reads alias_index for per-household aliases

#### 10.1 What It Is

The **connector alias normalizer** maps user-facing names to canonical `connector_id` values. Users and LLMs refer to connectors by human names: "Google Calendar," "my calendar," "Riley's calendar," "the family shopping list." The kernel needs `connector_id` values: `"calendar"`, `"google_calendar_read"`, `"shopping"`. This component bridges that gap.

It operates in **two scopes**:

- **Global scope:** Maps standard labels (e.g., "Family Calendar" → `"calendar"`, "Google Calendar" → `"google_calendar_read"`) from the connector catalog's LABELS registry + common aliases.
- **Local scope:** Maps per-household resource labels + aliases (e.g., "Riley's calendar" → `"calendar"`, via identifying the connected resource's connector_id) from `LocalProjectionStore.alias_index` + `connected_resources`.

This is a UTILITY component — it doesn't own the alias data. It queries the stores that own it. Its value is the NORMALIZATION algorithm: given a raw string, resolve it to a `connector_id` with a confidence score, handling ambiguity, case-insensitivity, and fuzzy matching.

#### 10.2 Public API

```python
# ── k1/fabric/stores/alias_normalizer.py ──────────────────────

@dataclass(frozen=True)
class AliasResolution:
    """Result of normalizing a user-facing name to a connector_id."""
    raw: str                            # original input
    normalized: str | None              # resolved connector_id, or None if unresolvable
    confidence: str                     # "exact" | "fuzzy" | "resource_based" | "unknown"
    candidates: list[str]               # alternative connector_ids when ambiguous
    source: str                         # "global_catalog" | "local_alias" | "resource_label"


class ConnectorAliasNormalizer:
    """Maps user-facing connector names → canonical connector_id."""

    def __init__(
        self,
        global_store: GlobalProjectionStore,
        local_store: LocalProjectionStore | None = None,  # None for shared/global-only lookups
    ) -> None: ...

    # ── Resolution ─────────────────────────────────────────
    def normalize(self, raw: str, *, actor_id: str | None = None) -> AliasResolution:
        """Resolve a raw name to a connector_id.

        Resolution order:
          1. Exact match against global LABELS (case-insensitive)
          2. Exact match against global connector_id itself
          3. Exact match against local alias_index (if local_store + actor_id provided)
          4. Exact match against connected_resources labels (if local_store + actor_id provided)
          5. Fuzzy LIKE match against global LABELS
          6. Fuzzy LIKE match against local alias_index
          7. If still unresolved → AliasResolution(normalized=None, confidence="unknown")
        """

    def normalize_batch(
        self,
        raws: list[str],
        *,
        actor_id: str | None = None,
    ) -> list[AliasResolution]:
        """Normalize multiple names. Ambiguous names are NOT collapsed."""

    # ── Reverse lookup ─────────────────────────────────────
    def label_for(self, connector_id: str) -> str | None:
        """Get the human-readable label for a connector_id (e.g., 'calendar' → 'Family Calendar')."""

    def labels_for_batch(self, connector_ids: list[str]) -> dict[str, str]:
        """Get labels for multiple connector_ids."""

    # ── Index maintenance ──────────────────────────────────
    def rebuild_global_alias_index(self) -> None:
        """Rebuild the in-memory global alias map from GlobalProjectionStore.
        Called after connector registration changes."""

    def global_alias_count(self) -> int:
        """Number of entries in the global alias index."""

    # ── Ambiguity ──────────────────────────────────────────
    def is_ambiguous(self, raw: str, *, actor_id: str | None = None) -> bool:
        """True if this raw name could refer to multiple connector_ids."""

    def disambiguation_candidates(
        self, raw: str, *, actor_id: str | None = None
    ) -> list[dict]:
        """Return {connector_id, label, resource_label} for each candidate."""
```

#### 10.3 Internal Design

**Resolution algorithm (7-step cascade):**

```text
normalize(raw, actor_id=None):

  Step 1 — Global LABELS exact match (case-insensitive):
    raw_lower = raw.strip().lower()
    if raw_lower in global_labels_lower:
        return AliasResolution(raw, global_labels_lower[raw_lower],
            confidence="exact", candidates=[], source="global_catalog")

  Step 2 — Global connector_id exact match:
    if raw_lower in global_connector_ids:
        return AliasResolution(raw, raw_lower,
            confidence="exact", candidates=[], source="global_catalog")

  Step 3 — Local alias_index exact match (requires actor_id):
    if actor_id and local_store:
        matches = local_store.resolve_alias(raw_lower, actor_id, entity_type="resource")
        if len(matches) == 1:
            resource = local_store.get_connected_resource(matches[0].entity_id)
            if resource:
                return AliasResolution(raw, resource.connector_id,
                    confidence="resource_based", candidates=[],
                    source="local_alias")

  Step 4 — Local connected_resources label exact match (requires actor_id):
    if actor_id and local_store:
        resources = local_store.list_connected_resources(actor_id)
        for res in resources:
            if res.label.lower() == raw_lower:
                return AliasResolution(raw, res.connector_id,
                    confidence="resource_based", candidates=[],
                    source="resource_label")

  Step 5 — Global LABELS fuzzy match (LIKE '%raw%'):
    candidates = [cid for label, cid in global_labels_lower.items()
                  if raw_lower in label]
    if len(candidates) == 1:
        return AliasResolution(raw, candidates[0],
            confidence="fuzzy", candidates=[], source="global_catalog")
    if len(candidates) > 1:
        return AliasResolution(raw, None,
            confidence="unknown", candidates=candidates, source="global_catalog")

  Step 6 — Local alias fuzzy match:
    if actor_id and local_store:
        fuzzy_matches = local_store.fuzzy_resolve_alias(
            raw_lower, actor_id, entity_type="resource"
        )
        # ... similar single/multi logic ...

  Step 7 — Unresolved:
    return AliasResolution(raw, None,
        confidence="unknown", candidates=[], source="global_catalog")
```

**Global alias index (in-memory dict, built from GlobalProjectionStore):**

```text
On init() or rebuild_global_alias_index():
  1. global_labels_lower = {}
  2. For each connector in global_store.list_connectors():
       global_labels_lower[connector.label.lower()] = connector.connector_id
       global_connector_ids.add(connector.connector_id.lower())
       # Also index common aliases:
       - "google calendar" → "google_calendar_read"
       - "apple calendar" → "apple_reminders"
       - "todo list" → "tasks"
       - "grocery list" → "shopping"
       - "family calendar" → "calendar"
       - etc. (from connector catalog)
  3. label_for_cache = {connector.connector_id: connector.label}
```

**Common alias mappings (built-in, overridable):**

```python
# Static mapping for well-known user-facing names
# These are the "headline" aliases that Back/Planner see in prompts
COMMON_ALIASES: dict[str, str] = {
    "google calendar": "google_calendar_read",
    "apple calendar": "apple_reminders",
    "apple reminders": "apple_reminders",
    "todo list": "tasks",
    "to-do list": "tasks",
    "grocery list": "shopping",
    "shopping list": "shopping",
    "family calendar": "calendar",
    "family tasks": "tasks",
    "family chores": "chores",
    "family reminders": "reminders",
    "family notes": "notes",
    "family contacts": "contacts",
    "family budget": "budgets",
    "my calendar": None,     # resolved via local_store (actor-scoped)
    "my tasks": None,        # resolved via local_store
    "kid's calendar": None,  # resolved via local_store
}
```

**Confidence scoring:** `"exact"` > `"resource_based"` > `"fuzzy"` > `"unknown"`. The `SituatedResolver` uses confidence to decide: `"unknown"` → `needs_disambiguation` verdict.

#### 10.4 Wiring — Where It's Used

```text
Used BY:
  RequestFrameBuilder (Back → Frame)
    → User says "add dentist to Riley's calendar"
    → normalize("Riley's calendar", actor_id=...) → "calendar"
    → normalize("dentist") → no connector match → passed as subject hint
    → Populates RequestFrame.resource_kind_hint + connector_hint

  ResolveResourcesService.resolve()
    → After resolving person + resource references in LocalProjectionStore:
    → normalize(resource.label, actor_id=...) to confirm connector_id
    → Cross-references with GlobalProjectionStore admission_verdict

  SituatedResolver.resolve()
    → When RequestFrame has an ambiguous resource reference:
    → disambiguation_candidates(raw, actor_id=...) → list of {connector_id, label}
    → Included in CandidateUniverse for HIL choices

  Back prompt (connector_summary phase)
    → Renders connector labels via label_for(connector_id)
    → "calendar" → "Family Calendar" in the prompt

  ManifestTranslator.translate()
    → Normalizes connector names from IFL manifests
    → "Google Calendar Read Adapter" → "google_calendar_read"
```

#### 10.5 E2E Data Flow

```text
┌─────────────────────────────────────────────────────────────┐
│ Back receives: "Add dentist to Riley's calendar Monday 3pm" │
│                                                             │
│  RequestFrameBuilder:                                       │
│    normalize("Riley's calendar")                            │
│                                                             │
│    Step 1 — Global LABELS: "riley's calendar" not in        │
│      {"family calendar", "google calendar", ...}            │
│    Step 2 — Global connector_id: not a connector_id         │
│    Step 3 — Local alias: resolve_alias("riley's calendar")  │
│      → match: resource_id="res_cal_riley_001"               │
│      → get_connected_resource("res_cal_riley_001")          │
│      → connector_id="calendar"                              │
│    → AliasResolution(                                       │
│        raw="Riley's calendar",                              │
│        normalized="calendar",                                │
│        confidence="resource_based",                         │
│        source="local_alias"                                 │
│      )                                                      │
│                                                             │
│  Frame built with connector_hint="calendar".                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Back prompt renders connector labels                        │
│                                                             │
│  For each connector in ResolutionEnvelope:                  │
│    label = normalizer.label_for("calendar")                 │
│    → "Family Calendar"                                      │
│    label = normalizer.label_for("google_calendar_read")     │
│    → "Google Calendar"                                      │
│    label = normalizer.label_for("chores")                   │
│    → "Family Chores"                                        │
│                                                             │
│  Prompt:                                                    │
│    ## Available Connectors                                  │
│    - Family Calendar (calendar)                             │
│    - Google Calendar (google_calendar_read)                 │
│    - Family Chores (chores)                                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Ambiguity resolution                                        │
│                                                             │
│  User says: "check Riley's schedule"                        │
│  normalize("Riley's schedule")                              │
│                                                             │
│  → No global match, no single local match.                  │
│  → Fuzzy local: resources with "Riley" + "schedule/calendar"│
│    → Candidates:                                            │
│      - "Riley's Google Calendar" (google_calendar_read)     │
│      - "Riley's Chores" (chores)                            │
│      - "Riley's Tasks" (tasks)                               │
│                                                             │
│  is_ambiguous("Riley's schedule") → True                    │
│  disambiguation_candidates("Riley's schedule") →            │
│    [                                                         │
│      {connector_id: "google_calendar_read",                 │
│       label: "Google Calendar",                             │
│       resource_label: "Riley's Google Calendar"},           │
│      {connector_id: "chores",                               │
│       label: "Family Chores",                               │
│       resource_label: "Riley's Chores"},                    │
│      {connector_id: "tasks",                                │
│       label: "Family Tasks",                                │
│       resource_label: "Riley's Tasks"},                     │
│    ]                                                        │
│                                                             │
│  SituatedResolver returns needs_disambiguation with         │
│  these candidates → Back asks HIL: "Which schedule?"        │
└─────────────────────────────────────────────────────────────┘
```

#### 10.6 Test Coverage

```text
GAP-P1-013: ConnectorAliasNormalizer unit tests
  File: tests/k1/fabric/stores/test_alias_normalizer.py

  Test classes:
    TestGlobalAliasResolution
      - test_normalize_exact_global_label_match
      - test_normalize_exact_connector_id_match
      - test_normalize_case_insensitive
      - test_normalize_whitespace_trimmed
      - test_normalize_fuzzy_single_match
      - test_normalize_fuzzy_multiple_matches_returns_candidates
      - test_normalize_no_match_returns_unknown
      - test_normalize_common_alias ("google calendar" → google_calendar_read)

    TestLocalAliasResolution
      - test_normalize_local_alias_exact_match
      - test_normalize_local_resource_label_match
      - test_normalize_local_takes_precedence_over_global_when_both_exact
      - test_normalize_local_requires_actor_id

    TestConfidenceScoring
      - test_exact_confidence_highest
      - test_resource_based_confidence_medium
      - test_fuzzy_confidence_low
      - test_unknown_confidence_lowest

    TestBatchNormalization
      - test_normalize_batch_all_resolved
      - test_normalize_batch_some_ambiguous
      - test_normalize_batch_preserves_order

    TestReverseLookup
      - test_label_for_known_connector
      - test_label_for_unknown_connector_returns_none
      - test_labels_for_batch_all_known
      - test_labels_for_batch_some_unknown

    TestGlobalIndexRebuild
      - test_rebuild_global_alias_index_from_store
      - test_rebuild_respects_new_connector_registration
      - test_global_alias_count_matches_store

    TestAmbiguity
      - test_is_ambiguous_multiple_candidates
      - test_is_ambiguous_single_candidate
      - test_is_ambiguous_no_candidates
      - test_disambiguation_candidates_returns_label_and_resource_label

    TestIntegrationWithLocalStore
      - test_normalize_uses_local_store_when_provided
      - test_normalize_falls_back_to_global_when_local_store_is_none
```

GAP-P2-002: Back prompt contract tests
  File to create: tests/k1/concierge/prompt/test_back_prompt_contract.py
  Covers: loop_start prompt includes GLOBAL constitution rules, meta-tool declarations,
    execution grounding block. after_resolution prompt includes connector constitution cards,
    tool name cards, allowed next actions. after_tool_commitment prompt includes schemas
    ONLY for committed tools. after_invocation prompt includes observations.
  Source: CC-10 injection schedule

GAP-P2-003: Back tool invocation paradigm tests
  File to create: tests/k1/concierge/tools/test_invoke_by_binding_id.py
  Covers: Back invokes by binding_id (not capability_name), InvocationObservation shape,
    FabricDispatchAdapter integration

GAP-P2-004: Back tier classification tests
  File to create: tests/k1/concierge/react/test_tier_classification.py
  Covers: Tier 2 vs Tier 3 promotion triggers, BackPromotionOutcome shape,
    escalation_reason, companion_resource_roles[]

GAP-P2-005: Back HIL integration tests
  File to create: tests/k1/concierge/react/test_back_hil_integration.py
  Covers: HIL fires on missing_required_params, HIL choices from CandidateUniverse,
    HIL response arrives in next BackTaskEnvelope

GAP-P2-006: discover_capabilities catalog-only mode tests
  File to create: tests/k1/concierge/tools/test_discover_capabilities_catalog_mode.py
  Covers: discovery_mode=catalog → catalog_only marker, allowed_next_actions=[],
    Back refuses to invoke from catalog results
  Related: C-014 open question

GAP-P2-007: E2E Tier 2 spine integration
  File to create: tests/integration/test_tier2_spine_e2e.py
  Covers: BackTaskEnvelope → resolve_situation → Fabric → Bridge → NativeToolProvider
    → calendar.create_event → VerificationObservation → submit_result(completed)
  This is THE critical E2E gate.

GAP-P2-008: Negative proof — Back cannot skip resolve_situation
  File to create: tests/k1/concierge/react/test_back_cannot_skip_resolution.py
  Covers: Back calls invoke_capability without resolve_situation → blocked,
    Back invents capability names → rejected, Back calls submit_result before
    verification → blocked

GAP-P2-009: Negative proof — Back cannot exceed allowed_next_actions
  File to create: tests/k1/concierge/react/test_back_allowed_actions_enforcement.py
  Covers: Back attempts action not in allowed_next_actions[] → dispatcher blocks,
    Back attempts forbidden_tool_calls[] → dispatcher blocks

```

#### 2.4 Implementation Plan

```text
Step 2.1: RequestFrame builder
  - Promote poc/back_tool_contract_v2/request_frame_builder.py → k1/concierge/react/request_frame.py
  - Implement Contract A shape (user_goal, actor_ref, operation_hints[], resource_references[], etc.)
  - Wire into back_handler — called before resolve_situation
  - Write: tests for RequestFrame extraction against 100 scenario corpus

Step 2.2: Back prompt contract (CC-10)
  - Refactor back_prompt.py to match CC-10 injection schedule:
    loop_start → after_resolution → after_tool_commitment → after_invocation
  - Inject PromptPack cards at each phase
  - disclose connector constitution + tool names at Phase 1, schemas only after commitment
  - Write GAP-P2-002

Step 2.3: Back ReAct loop — resolve_situation integration
  - In back_handler, after RequestFrame: call resolve_situation (not discover_capabilities)
  - Parse ResolutionEnvelope → extract allowed_next_actions[], PromptPack, CandidateUniverse
  - Enforce: Back acts only through allowed_next_actions[]
  - Write GAP-P2-001, GAP-P2-009

Step 2.4: Tool invocation paradigm
  - Back invokes by binding_id (from BindingBundle), not hand-copied capability_name
  - FabricDispatchAdapter passes binding_id through to CapabilityFabric
  - Back receives normalized InvocationObservation
  - Write GAP-P2-003

Step 2.5: Tier classification + promotion
  - Implement tier classification logic in back_handler
  - Promotion triggers: cross-connector, companion resources, dependency graph, incomplete projection
  - BackPromotionOutcome → bus → FSM → Orchestrator
  - Write GAP-P2-004

Step 2.6: HIL integration
  - Back receives HIL choices from CandidateUniverse (resolved by Fabric)
  - HIL request/response cycle through session_bus
  - Write GAP-P2-005

Step 2.7: discover_capabilities demotion
  - Add discovery_mode flag to Back tool context
  - When discovery_mode=catalog: return results with catalog_only marker, allowed_next_actions=[]
  - When discovery_mode=execution: Back MUST use resolve_situation
  - Write GAP-P2-006

Step 2.8: E2E Tier 2 integration gate
  - Full spine test: BackTaskEnvelope → resolve_situation → Fabric → Bridge → calendar.create_event
  - Write GAP-P2-007 (critical)
  - Write GAP-P2-008 (negative proof)
  - Run ALL existing concierge tests (177+ files) — must all pass
  - Run Phase 1 tests — must all pass (regression)
```

**Files to create:**

```text
k1/concierge/react/request_frame.py              (promoted from POC request_frame_builder.py)
tests/k1/concierge/react/test_resolve_situation_integration.py
tests/k1/concierge/prompt/test_back_prompt_contract.py
tests/k1/concierge/tools/test_invoke_by_binding_id.py
tests/k1/concierge/react/test_tier_classification.py
tests/k1/concierge/react/test_back_hil_integration.py
tests/k1/concierge/tools/test_discover_capabilities_catalog_mode.py
tests/integration/test_tier2_spine_e2e.py
tests/k1/concierge/react/test_back_cannot_skip_resolution.py
tests/k1/concierge/react/test_back_allowed_actions_enforcement.py
```

**Files to modify:**

```text
k1/concierge/actors/back.py                      (RequestFrame → resolve_situation, tier classify)
k1/concierge/prompt/back_prompt.py               (CC-10 injection schedule)
k1/concierge/react/loop.py                       (allowed_next_actions enforcement)
k1/concierge/tools/implementations.py            (discovery_mode flag, binding_id invoke)
k1/concierge/tools/schemas_back.py               (resolve_situation meta-tool declaration)
k1/concierge/adapters/fabric_dispatch.py         (binding_id passthrough)
k1/concierge/fsm/controller.py                   (BackPromotionOutcome → Tier 3 routing)
```

---

### Workbook Phase 2 — Back

> **Ground-reality audit date:** 2026-06-02. Based on full code audit of `k1/concierge/` (177+ test files), `k1/concierge/actors/back.py`, `k1/concierge/prompt/back_prompt.py`, `k1/concierge/react/loop.py`, `k1/concierge/tools/schemas_back.py`, `k1/concierge/tools/implementations.py`, `k1/concierge/adapters/fabric_dispatch.py`, and `k1/concierge/fsm/controller.py`.

---

#### 2.1 Ground Reality — Back Execution Actor

**File:** `k1/concierge/actors/back.py`

Back receives a `BackTaskEnvelope` via `route_back_envelope()`, which calls `back_handler()`. The handler:

1. Reads SessionState once at task start via `SessionStateReaderAdapter`.
2. Resolves the effective safety band and execution profile.
3. Builds the Back system prompt via `build_back_system_prompt()` (from `k1/concierge/prompt/back_prompt.py`).
4. Constructs the initial messages array with task context, tool schemas, and grounding metadata.
5. Runs the shared `react_loop()` (from `k1/concierge/react/loop.py`) with `actor='back'`.
6. After loop termination, calls `_emit_back_result()` which publishes `task.complete`, `task.suspended`, or `task.failed` on the session bus.

**Current tool surface (Back meta-tools):** Defined in `k1/concierge/tools/schemas_back.py`. Back receives tier-filtered meta-tools — `discover_capabilities`, `invoke_capability`, `batch_invoke_capabilities`, `submit_result`, `recall_memory`. These are NOT domain tools (calendar, tasks, etc.) — those are discovered through `discover_capabilities` at runtime.

**Current prompt (`k1/concierge/prompt/back_prompt.py`):** The Back system prompt includes:

- Executor role + constraints (act only through meta-tools, never invent capabilities, always verify before side effects).
- Available meta-tool declarations with JSON schemas.
- Task context block (user goal, task kind, safety band, session ref).
- NO connector constitutions, NO staged disclosure, NO PromptPack.

**Current ToolContext/runtime binding:** `ToolContext` provides Back with `prompt_budget`, `max_iterations`, `max_fabric_calls`, `dispatched_tasks` accumulator, and a `dispatch` adapter that routes through `FabricDispatchAdapter` → `CapabilityFabric.execute()`.

---

#### 2.2 Ground Reality — Back ReAct Loop

**File:** `k1/concierge/react/loop.py`

The shared `react_loop()` handles both Front and Back actors. For Back specifically:

1. Constructs ModelHub request with messages + tools + generation config.
2. LLM responds with tool calls or text.
3. Tool calls are validated against the declared tool surface — unknown tools rejected.
4. Validated calls dispatched through `ToolDispatcher` (parallel or sequential per `parallel_safety` policy).
5. Tool results are formatted as tool result messages and appended to conversation.
6. Loop terminates when Back calls `submit_result(status)` — this sets `react_result.terminal = True`.
7. If Back calls `submit_result(completed)`, success is assumed; no verification step today.
8. Loop guards: `max_iterations` cap, `prompt_budget` exhaustion detection, empty-response detection, spin detection (no work in N consecutive iterations).

**Current termination:** `submit_result` is the ONLY terminal action. Statuses: `completed`, `partial`, `needs_hil`, `cannot_execute`, `blocked`, `failed`. Back must provide `summary` and `evidence` fields — but evidence is unstructured today (free text, not typed verification observations).

**Current capability routing (`k1/concierge/react/capability_routing.py`):** `_bind_capability_for_back_action()` validates or repairs the Back-chosen `capability_name` against the registry. `bind_capability()` ensures required params exist. `recovery_for_unsatisfied_contract()` provides a soft recovery path — prompts Back to fix params rather than hard-blocking.

---

#### 2.3 Ground Reality — Back Tool Implementations

**File:** `k1/concierge/tools/implementations.py`

**`discover_capabilities`:** Back calls this with `domain`, `intent`, `safety_band`, `top_k`. Routes through `FabricRetrieval.discover_capabilities()` → `RetrievalEngine` → returns scored `CapabilityContract` records. Back chooses a capability name from the results and passes it to `invoke_capability`. This is the CURRENT baseline path (catalog search → LLM choose → invoke). Target replaces this with `resolve_situation`.

**`invoke_capability`:** Back provides `capability_name` + `params`. The implementation:

1. Calls `_bind_capability_for_back_action()` to validate the name against the registry.
2. Constructs `CapabilityRequest` with required inputs validated against schema.
3. Routes through `FabricDispatchAdapter.dispatch_direct()` → `CapabilityFabric.execute()`.
4. Returns `ToolResult` with status and data.

**`submit_result`:** Back provides `status` + `summary` + `evidence`. The implementation validates the status, emits `task.complete`/`task.suspended`/`task.failed`, and terminates the loop. No verification gate today — Back can submit `completed` without proving the write persisted.

---

#### 2.4 Ground Reality — Test Coverage (177+ concierge test files)

| Category | Key files | Coverage |
|---|---|---|
| Back actor | `test_back_resume_resolution_frame.py`, `test_back_result_frame.py`, `test_back_handler_profile_wiring.py` | Back handler + result frames |
| Tools | `test_tool_dispatcher_tier_collapse.py` + many more in `tools/` | Tool dispatch, discovery, invocation |
| Factory | `test_concierge_factory.py`, `test_concierge_factory_stress.py` | ConciergeFactory |
| Task | `test_dispatch_grounding_fields.py` | Grounding field propagation in dispatch |
| Bus | `test_bus_temporal_topics.py` | Bus topic integrity |
| Contracts | `test_contract_converter.py`, `test_c1_port_protocols.py` | Contract conversion + port protocols |
| Calendar | `test_calendar_tools.py` | Calendar tools through concierge |
| HIL | `test_controller_hil_port.py` | HIL port on controller |
| Identity | `test_dynamic_identity.py` | Dynamic identity injection |
| Event registry | `test_event_registry_completeness.py` | Event registry audit |
| Other | `test_fabric_port.py`, `test_episodic_compressor.py`, `test_e0515_obs_stubs.py`, `test_bootstrap_smoke.py` | Ports, compression, obs, smoke |

---

#### 2.5 New Tests Required (GATE-P2)

```text
GAP-P2-001: Back ReAct loop — resolve_situation integration
  File to create: tests/k1/concierge/react/test_resolve_situation_integration.py
  Covers: Back builds RequestFrame → calls resolve_situation → receives ResolutionEnvelope
    → acts only through allowed_next_actions[]

GAP-P2-002: Back prompt contract tests
  File to create: tests/k1/concierge/prompt/test_back_prompt_contract.py
  Covers: loop_start prompt includes GLOBAL constitution rules, meta-tool declarations,
    execution grounding block. after_resolution prompt includes connector constitution cards,
    tool name cards, allowed next actions. after_tool_commitment prompt includes schemas
    ONLY for committed tools. after_invocation prompt includes observations.
  Source: CC-10 injection schedule

GAP-P2-003: Back tool invocation paradigm tests
  File to create: tests/k1/concierge/tools/test_invoke_by_binding_id.py
  Covers: Back invokes by binding_id (not capability_name), InvocationObservation shape,
    FabricDispatchAdapter integration

GAP-P2-004: Back tier classification tests
  File to create: tests/k1/concierge/react/test_tier_classification.py
  Covers: Tier 2 vs Tier 3 promotion triggers, BackPromotionOutcome shape,
    escalation_reason, companion_resource_roles[]

GAP-P2-005: Back HIL integration tests
  File to create: tests/k1/concierge/react/test_back_hil_integration.py
  Covers: HIL fires on missing_required_params, HIL choices from CandidateUniverse,
    HIL response arrives in next BackTaskEnvelope

GAP-P2-006: discover_capabilities catalog-only mode tests
  File to create: tests/k1/concierge/tools/test_discover_capabilities_catalog_mode.py
  Covers: discovery_mode=catalog → catalog_only marker, allowed_next_actions=[],
    Back refuses to invoke from catalog results
  Related: C-014 open question

GAP-P2-007: E2E Tier 2 spine integration
  File to create: tests/integration/test_tier2_spine_e2e.py
  Covers: BackTaskEnvelope → resolve_situation → Fabric → Bridge → NativeToolProvider
    → calendar.create_event → VerificationObservation → submit_result(completed)
  This is THE critical E2E gate.

GAP-P2-008: Negative proof — Back cannot skip resolve_situation
  File to create: tests/k1/concierge/react/test_back_cannot_skip_resolution.py
  Covers: Back calls invoke_capability without resolve_situation → blocked,
    Back invents capability names → rejected, Back calls submit_result before
    verification → blocked

GAP-P2-009: Negative proof — Back cannot exceed allowed_next_actions
  File to create: tests/k1/concierge/react/test_back_allowed_actions_enforcement.py
  Covers: Back attempts action not in allowed_next_actions[] → dispatcher blocks,
    Back attempts forbidden_tool_calls[] → dispatcher blocks
```

---

#### 2.6 Implementation Plan

```text
Step 2.1: RequestFrame builder
  - Promote poc/back_tool_contract_v2/request_frame_builder.py → k1/concierge/react/request_frame.py
  - Implement Contract A shape (user_goal, actor_ref, operation_hints[], resource_references[], etc.)
  - Wire into back_handler — called before resolve_situation
  - Write: tests for RequestFrame extraction against 100 scenario corpus

Step 2.2: Back prompt contract (CC-10)
  - Refactor back_prompt.py to match CC-10 injection schedule:
    loop_start → after_resolution → after_tool_commitment → after_invocation
  - Inject PromptPack cards at each phase
  - disclose connector constitution + tool names at Phase 1, schemas only after commitment
  - Write GAP-P2-002

Step 2.3: Back ReAct loop — resolve_situation integration
  - In back_handler, after RequestFrame: call resolve_situation (not discover_capabilities)
  - Parse ResolutionEnvelope → extract allowed_next_actions[], PromptPack, CandidateUniverse
  - Enforce: Back acts only through allowed_next_actions[]
  - Write GAP-P2-001, GAP-P2-009

Step 2.4: Tool invocation paradigm
  - Back invokes by binding_id (from BindingBundle), not hand-copied capability_name
  - FabricDispatchAdapter passes binding_id through to CapabilityFabric
  - Back receives normalized InvocationObservation
  - Write GAP-P2-003

Step 2.5: Tier classification + promotion
  - Implement tier classification logic in back_handler
  - Promotion triggers: cross-connector, companion resources, dependency graph, incomplete projection
  - BackPromotionOutcome → bus → FSM → Orchestrator
  - Write GAP-P2-004

Step 2.6: HIL integration
  - Back receives HIL choices from CandidateUniverse (resolved by Fabric)
  - HIL request/response cycle through session_bus
  - Write GAP-P2-005

Step 2.7: discover_capabilities demotion
  - Add discovery_mode flag to Back tool context
  - When discovery_mode=catalog: return results with catalog_only marker, allowed_next_actions=[]
  - When discovery_mode=execution: Back MUST use resolve_situation
  - Write GAP-P2-006

Step 2.8: E2E Tier 2 integration gate
  - Full spine test: BackTaskEnvelope → resolve_situation → Fabric → Bridge → calendar.create_event
  - Write GAP-P2-007 (critical)
  - Write GAP-P2-008 (negative proof)
  - Run ALL existing concierge tests (177+ files) — must all pass
  - Run Phase 1 tests — must all pass (regression)
```

**Files to create:**

```text
k1/concierge/react/request_frame.py              (promoted from POC request_frame_builder.py)
tests/k1/concierge/react/test_resolve_situation_integration.py
tests/k1/concierge/prompt/test_back_prompt_contract.py
tests/k1/concierge/tools/test_invoke_by_binding_id.py
tests/k1/concierge/react/test_tier_classification.py
tests/k1/concierge/react/test_back_hil_integration.py
tests/k1/concierge/tools/test_discover_capabilities_catalog_mode.py
tests/integration/test_tier2_spine_e2e.py
tests/k1/concierge/react/test_back_cannot_skip_resolution.py
tests/k1/concierge/react/test_back_allowed_actions_enforcement.py
```

**Files to modify:**

```text
k1/concierge/actors/back.py                      (RequestFrame → resolve_situation, tier classify)
k1/concierge/prompt/back_prompt.py               (CC-10 injection schedule)
k1/concierge/react/loop.py                       (allowed_next_actions enforcement)
k1/concierge/tools/implementations.py            (discovery_mode flag, binding_id invoke)
k1/concierge/tools/schemas_back.py               (resolve_situation meta-tool declaration)
k1/concierge/adapters/fabric_dispatch.py         (binding_id passthrough)
k1/concierge/fsm/controller.py                   (BackPromotionOutcome → Tier 3 routing)
```

---

### Workbook Phase 3 — Context Plane

#### 3.1 Current Code Reality

**Grounding infrastructure (Tier 1, S2.7–S2.9; Per-session, P3.6–P3.8):**

| File | Role |
|---|---|
| `k1/temporal/kernel/bootstrap.py` | `TemporalServiceBundle` — clock, timezone, policy stack |
| `k1/temporal/kernel/handle.py` | `TemporalHandle` — per-session temporal state, `refresh_turn()` |
| `k1/temporal/service/temporal_service.py` | `TemporalService` — temporal resolution |
| `k1/spatial/kernel/bootstrap.py` | `SpatialServiceBundle` — place registry, geolocation |
| `k1/spatial/kernel/handle.py` | `SpatialHandle` — per-session spatial state, `refresh_turn()` |
| `k1/grounding/kernel/bootstrap.py` | `GroundingServiceBundle` — composite wrapping temporal+spatial+identity |
| `k1/grounding/kernel/handle.py` | `GroundingHandle` — per-session grounding, `build_projection()`, `refresh_turn()` |
| `k1/grounding/service/grounding_service.py` | `GroundingService` — builds `GroundingEnvelope` → `GroundingProjection` |
| `k1/grounding/service/propagation.py` | `build_propagation_metadata()` — dispatch attachment |
| `k1/grounding/adapters/selfmodel_identity_adapter.py` | `SelfModelIdentityAdapter` — bridges selfmodel actor_id into grounding |
| `k1/grounding/adapters/temporal_handle_adapter.py` | `TemporalHandleAdapter` |
| `k1/grounding/adapters/spatial_handle_adapter.py` | `SpatialHandleAdapter` |

**SelfModel (Tier 1, S2.6; Per-session, P3.5):**

| File | Role |
|---|---|
| `k1/selfmodel/kernel/bootstrap.py` | `SelfModelServiceBundle` |
| `k1/selfmodel/kernel/handle.py` | `SelfModelHandle` — `SituationFrame = S(actor) ∩ F ∩ C`, `render_capsule()` |
| `k1/selfmodel/service/self_model.py` | `SelfModelService` — `K1SelfModelSnapshot` per `actor_id` |
| `k1/selfmodel/service/space_graph.py` | `SpaceGraphService` — members with `display_name`, `role`, `age_band` |
| `k1/selfmodel/service/situation_composer.py` | `SituationFrameComposer` — golden boundary, Empty-Set Invariants |
| `k1/selfmodel/service/capsule_builder.py` | `GroundingCapsuleBuilder` — prompt-safe capsule from SituationFrame |

**SessionState (Per-session, P2):**

| File | Role |
|---|---|
| `k1/sessionstate/sections/meta.py` | `MetaSection.identity` — `user_id`, `device_id`, `privacy_band` |
| `k1/sessionstate/sections/persona.py` | `PersonaSection._preferences["active_member"]` — display name |
| `k1/sessionstate/sections/grounding.py` | `GroundingSection` — envelope/projection metadata IDs |
| `k1/sessionstate/sections/temporal.py` | Temporal context section |
| `k1/sessionstate/sections/spatial.py` | Spatial context section |

**Current prompt injection (Front side):**

| File | Role |
|---|---|
| `k1/concierge/actors/front.py` | `grounding.refresh_turn()` → `GroundingProjection` → injected into Front prompt at stage 9.5 |
| `k1/concierge/prompt/dynamic_prompt_builder.py` | `DynamicPromptBuilder` — injects selfmodel capsule + grounding projection |

#### 3.2 Tests Available Today

| Area | Test files | Count |
|---|---|---|
| Temporal | `test_types.py`, `test_serialization.py`, `test_package_imports.py`, `test_factory_wiring.py`, `test_events.py`, `service/test_*.py` (5 files), `ports/test_protocol_shapes.py`, `kernel/test_handle.py`, `kernel/test_bundle.py`, `adapters/test_*.py` (3 files) | 19 |
| Spatial | `test_types_events_serialization.py`, `test_session_state_adapter.py`, `test_privacy_projector.py`, `test_ports_protocol_shapes.py`, `test_place_resolver.py`, `test_place_candidate_source.py`, `test_package_imports.py`, `test_nominatim_geocoder_adapter.py`, `test_location_normalizer.py`, `test_geofence_matcher.py`, `test_factory_wiring.py`, `test_device_context.py`, `kernel/test_handle.py` | 13 |
| Grounding | `test_prompt_block_renderer_v2.py`, `test_projection_policy_spatial.py`, `test_package_imports.py`, `test_m15_runtime.py`, `test_lease_spatial.py`, `adapters/test_spatial_handle_adapter_real.py` | 6 |
| SelfModel | `test_module_layout.py`, `test_m9_m10_layer_cleanup.py`, `test_m6_m7_m8_conscience_inversion.py`, `adapters/test_*.py` (10 files), `service/test_*.py` (13+ files) | 66 |

#### 3.3 New Tests Required (GATE-P3)

```text
GAP-P3-001: Back execution_grounding_block tests
  File to create: tests/k1/concierge/prompt/test_execution_grounding_block.py
  Covers: temporal context injection (timezone, "now", resolved dates),
    spatial context injection (location, place refs), participant context
    injection (household member list with roles), safety context injection

GAP-P3-002: Back prompt temporal enrichment tests
  File to create: tests/k1/concierge/prompt/test_temporal_prompt_enrichment.py
  Covers: timezone-aware hints, upcoming calendar context, deadline awareness

GAP-P3-003: Back prompt spatial enrichment tests
  File to create: tests/k1/concierge/prompt/test_spatial_prompt_enrichment.py
  Covers: place context, geofence-aware hints

GAP-P3-004: Back prompt participant enrichment tests
  File to create: tests/k1/concierge/prompt/test_participant_prompt_enrichment.py
  Covers: resolved participant list, missing identity flagged as uncertainty_markers[],
    "Could not resolve 'Aunt Sarah'" → needs_disambiguation

GAP-P3-005: Participant resolution service tests (C-013)
  File to create: tests/k1/fabric/test_participant_resolution.py
  Covers: resolve_participant(name, space_id) → actor_id, SpaceGraphService integration,
    ambiguous names → needs_disambiguation with member candidates

GAP-P3-006: Grounding freshness signal tests
  File to create: tests/k1/grounding/test_freshness_signals.py
  Covers: freshness state injection, stale warnings in prompt,
    stale grounding → HIL, does not execute

GAP-P3-007: PromptPack context_summary tests
  File to create: tests/k1/fabric/test_promptpack_context_summary.py
  Covers: PromptPack carries temporal/spatial/participant signals,
    decision_surface enriched with context-derived constraints

GAP-P3-008: Negative proof — stale grounding blocks execution
  File to create: tests/k1/concierge/react/test_stale_grounding_blocks_execution.py
  Covers: spatial context age > threshold → HIL, not execute;
    unresolvable participant → needs_disambiguation, not guess

GAP-P3-009: Negative proof — missing identity does not halt loop
  File to create: tests/k1/concierge/react/test_missing_identity_graceful.py
  Covers: unresolvable name → needs_disambiguation verdict,
    loop continues with HIL, does not crash or silently guess
```

#### 3.4 Implementation Plan

```text
Step 3.1: Build execution_grounding_block for Back's loop_start
  - New file: k1/concierge/prompt/grounding_block.py
  - Consumes GroundingProjection (P3.8) + TemporalHandle (P3.6) + SpatialHandle (P3.7)
    + SelfModelHandle (P3.5)
  - Renders compact text block: temporal context, spatial context, participant list,
    safety context, freshness state
  - Injected into Back prompt at CC-10 loop_start phase
  - Write GAP-P3-001

Step 3.2: Enrich Back prompt with temporal signals
  - Extend execution_grounding_block with timezone-aware hints
  - Add upcoming calendar context (next 7 days summary)
  - Add deadline awareness for task time references
  - Write GAP-P3-002

Step 3.3: Enrich Back prompt with spatial signals
  - Extend execution_grounding_block with place context
  - Add geofence-aware hints (school distance, location radius)
  - Write GAP-P3-003

Step 3.4: Enrich Back prompt with participant signals
  - Extend execution_grounding_block with resolved household member list
  - Flag unresolved names in uncertainty_markers[]
  - Write GAP-P3-004

Step 3.5: Implement participant resolution service (C-013)
  - New file: k1/fabric/resolver/participant_resolver.py
  - Uses GroundingProjection.space_id → SpaceGraphService.get_view(actor_id)
    → iterates members → matches display_name
  - Resolved participants added to CandidateUniverse.impact_set_candidates[]
  - Ambiguous → Fabric returns needs_disambiguation with member candidates
  - Write GAP-P3-005

Step 3.6: Inject grounding freshness signals
  - Add freshness state to execution_grounding_block
  - Add stale warnings when context age exceeds thresholds
  - Write GAP-P3-006, GAP-P3-008

Step 3.7: Enrich PromptPack with context_summary
  - Add context_summary field to PromptPack (Contract G extension)
  - Carry temporal/spatial/participant signals
  - Enrich decision_surface with context-derived constraints
  - Write GAP-P3-007

Step 3.8: Integration gate
  - Run GATE-P3 checklist (11 items in roadmap)
  - Run ALL existing temporal tests (19 files) — must all pass
  - Run ALL existing spatial tests (13 files) — must all pass
  - Run ALL existing grounding tests (6 files) — must all pass
  - Run ALL existing selfmodel tests (66 files) — must all pass
  - Run Phase 1 + Phase 2 tests — must all pass (regression)
  - Write GAP-P3-009 (negative proof)
```

**Files to create:**

```text
k1/concierge/prompt/grounding_block.py                (execution_grounding_block builder)
k1/fabric/resolver/__init__.py
k1/fabric/resolver/participant_resolver.py             (C-013 implementation)
tests/k1/concierge/prompt/test_execution_grounding_block.py
tests/k1/concierge/prompt/test_temporal_prompt_enrichment.py
tests/k1/concierge/prompt/test_spatial_prompt_enrichment.py
tests/k1/concierge/prompt/test_participant_prompt_enrichment.py
tests/k1/fabric/test_participant_resolution.py
tests/k1/grounding/test_freshness_signals.py
tests/k1/fabric/test_promptpack_context_summary.py
tests/k1/concierge/react/test_stale_grounding_blocks_execution.py
tests/k1/concierge/react/test_missing_identity_graceful.py
```

**Files to modify:**

```text
k1/concierge/prompt/back_prompt.py                    (inject execution_grounding_block at loop_start)
k1/concierge/actors/back.py                           (consume grounding signals)
k1/fabric/resolver.py                                 (call participant_resolver)
k1/fabric/policy/selector.py                          (consume resolved participants)
k1/grounding/kernel/handle.py                         (expose freshness metadata)
```

---

### Workbook Phase 4 — IFL

#### 4.1 Current Code Reality

**Bridge IFL tier:**

| File | Role |
|---|---|
| `bridge/ifl/__init__.py` | IFL tier placeholder — adapter registry, MCP host |
| `bridge/ifl/mcp_stdio.py` | MCP stdio transport for child processes |
| `bridge/ifl/adapters/google_calendar/oauth.py` | Google Calendar OAuth server |
| `bridge/ifl/adapters/google_calendar/server.py` | Google Calendar MCP server |
| `bridge/ifl/adapters/google_calendar/consent.py` | Consent flow |
| `bridge/ports/` | 5 protocol definitions (CMD, QRY, SSE, OBS, IFL) |

**Architecture diagrams:**

| File | Content |
|---|---|
| `architecture_diagrams/bridge/bridge_architecture.mmd` | Bridge-owns-IFL hierarchy |
| `architecture_diagrams/bridge/bridge_architecture_v2.mmd` | Trust roots, K0/K1/Bridge topology |
| `architecture_diagrams/bridge/interkernel_fabric_layer.mmd` | IFL runtime subsystems (Manifest, Protocol Engine, Adapter Registry, Dispatch, Events) |

**Contracts (in whiteboard):**

| Contract | Content |
|---|---|
| CC-7 | Bridge ↔ IFL adapter protocol (`IflCommandEnvelope` / `IflResultEnvelope`) |
| CC-8 | IFL Manifest → Fabric Capability Registration (`IflManifest` → `CapabilityRegistrationBatch`) |
| Constitution Tooling | Connector constitution shape + 6 principles |
| Principle 6 | Constitution ships with connector, not prompt |

#### 4.2 Tests Available Today

| Area | Test files | Count |
|---|---|---|
| Bridge IFL | `test_google_calendar_round_trip.py`, `test_google_calendar_oauth_consent.py` | 2 |
| Bridge connector | 9 files (listed in Phase 1) | 9 |
| Bridge core/sync/integration | 37+ files | 37 |

#### 4.3 New Tests Required (GATE-P4)

```text
GAP-P4-001: IFL Manifest schema validation tests
  File to create: tests/bridge/ifl/test_manifest_schema_validation.py
  Covers: IflManifest JSON Schema, required fields, capability_templates[] shape,
    resource_models[] shape, event_topics[], auth_scopes[], safety_metadata,
    verifier_affordances[], freshness_guarantees

GAP-P4-002: Connector constitution schema validation tests
  File to create: tests/bridge/ifl/test_constitution_schema_validation.py
  Covers: ConstitutionArtifact schema, preconditions, companion_resource roles,
    conflict_analysis_rules[], mutation_sequencing[], hil_gates[],
    verification_requirements[], versioning

GAP-P4-003: ManifestTranslator round-trip tests
  File to create: tests/k1/fabric/test_manifest_translator_roundtrip.py
  Covers: IflManifest → ManifestTranslator → CapabilityRegistrationBatch,
    all fields preserved, capability naming convention enforced

GAP-P4-004: Adapter protocol contract tests (CC-7)
  File to create: tests/bridge/ifl/test_adapter_protocol_contract.py
  Covers: IflCommandEnvelope shape, IflResultEnvelope shape, error codes,
    recovery actions, MCP stdio transport contract

GAP-P4-005: Reference connector E2E (Google Calendar)
  File to create: tests/integration/test_google_calendar_e2e_full.py
  Covers: manifest → registration → resolve_situation → invoke → verify → submit_result
    through FULL 4-plane stack. This is the ultimate integration test.

GAP-P4-006: Negative proof — malformed manifest
  File to create: tests/bridge/ifl/test_manifest_rejection.py
  Covers: missing required fields → rejected, invalid capability name format → rejected,
    unsigned manifest → rejected, missing constitution → rejected

GAP-P4-007: Negative proof — adapter security
  File to create: tests/bridge/ifl/test_adapter_security.py
  Covers: unsigned adapter → AdapterVerifier rejects, revoked adapter → rejected,
    credential leak attempt → blocked
```

#### 4.4 Implementation Plan

```text
Step 4.1: IFL Manifest Standard document
  - New file: docs/ifl/IFL_MANIFEST_STANDARD.md
  - JSON Schema for IflManifest with all CC-8 fields
  - Examples: Google Calendar, generic REST API, WebSocket adapter
  - Write GAP-P4-001

Step 4.2: Connector Constitution Standard document
  - New file: docs/ifl/CONNECTOR_CONSTITUTION_STANDARD.md
  - JSON Schema for ConstitutionArtifact
  - Authoring guide: how to define preconditions, companion resources, conflict rules,
    HIL gates, verification requirements
  - Write GAP-P4-002

Step 4.3: Tool Design Contract document
  - New file: docs/ifl/TOOL_DESIGN_CONTRACT.md
  - Capability naming convention specification
  - Input/output JSON Schema requirements
  - Effect declarations, safety requirements, limitations
  - Verifier affordance declarations

Step 4.4: Policy Authoring Standard document
  - New file: docs/ifl/POLICY_AUTHORING_STANDARD.md
  - PolicyBundle schema for domain authors
  - Guide cards authoring patterns
  - Cross-connector governance rule templates

Step 4.5: Adapter Protocol Standard document (CC-7)
  - New file: docs/ifl/ADAPTER_PROTOCOL_STANDARD.md
  - IflCommandEnvelope / IflResultEnvelope specification
  - Error codes and recovery actions
  - MCP stdio transport contract
  - Write GAP-P4-004

Step 4.6: Connector Authoring Guide
  - New file: docs/ifl/CONNECTOR_AUTHORING_GUIDE.md
  - Step-by-step: create a new connector
  - Adapter implementation template (Python MCP server)
  - Credential setup (OAuth, API keys → CredentialVault)
  - Testing checklist before registration
  - Reference: Google Calendar connector as worked example

Step 4.7: ManifestTranslator hardening
  - Audit ManifestTranslator against CC-8 contract
  - Ensure all IflManifest fields are translated to CapabilityRegistrationBatch
  - Ensure capability naming convention enforced at registration
  - Write GAP-P4-003

Step 4.8: Reference connector — Google Calendar
  - Redesign bridge/ifl/adapters/google_calendar/ to new IFL standard
  - Full manifest with constitution, resource models, capability templates
  - Full JSON schemas for all operations
  - Passes Phase 1 Fabric gate, Phase 2 E2E gate, Phase 3 Context Plane gate
  - Write GAP-P4-005 (ultimate integration test)
  - Write GAP-P4-006, GAP-P4-007 (negative proof)

Step 4.9: Integration gate
  - All 5 standard documents published
  - Reference connector passes all 4 gates (Fabric → Back → Context Plane → IFL)
  - Run ALL existing tests — must all pass (regression across all phases)
```

**Files to create:**

```text
docs/ifl/IFL_MANIFEST_STANDARD.md
docs/ifl/CONNECTOR_CONSTITUTION_STANDARD.md
docs/ifl/TOOL_DESIGN_CONTRACT.md
docs/ifl/POLICY_AUTHORING_STANDARD.md
docs/ifl/ADAPTER_PROTOCOL_STANDARD.md
docs/ifl/CONNECTOR_AUTHORING_GUIDE.md
tests/bridge/ifl/test_manifest_schema_validation.py
tests/bridge/ifl/test_constitution_schema_validation.py
tests/k1/fabric/test_manifest_translator_roundtrip.py
tests/bridge/ifl/test_adapter_protocol_contract.py
tests/integration/test_google_calendar_e2e_full.py
tests/bridge/ifl/test_manifest_rejection.py
tests/bridge/ifl/test_adapter_security.py
```

**Files to modify:**

```text
bridge/ifl/__init__.py                              (manifest registry, protocol engine)
bridge/ifl/mcp_stdio.py                             (CC-7 contract compliance)
bridge/ifl/adapters/google_calendar/server.py       (reference implementation redesign)
bridge/ifl/adapters/google_calendar/oauth.py        (credential vault integration)
bridge/connector/gateway.py                         (CC-6 contract compliance audit)
bridge/connector/adapter_verifier.py                (CA signature + revocation check)
k1/fabric/manifest_translator.py                    (CC-8 contract compliance audit)
```

---

### Cross-Phase Regression Suite

After each phase, ALL prior-phase tests must continue passing. The regression suite grows cumulatively:

```text
After Phase 1:
  pytest tests/k1/fabric/ -v
  pytest tests/bridge/ -v
  pytest tests/k1/tools/family/ -v
  pytest tests/k1/hil/ -v
  → ~228 test files

After Phase 2:
  + pytest tests/k1/concierge/ -v
  + pytest tests/integration/test_tier2_spine_e2e.py -v
  → ~405 test files

After Phase 3:
  + pytest tests/k1/temporal/ -v
  + pytest tests/k1/spatial/ -v
  + pytest tests/k1/grounding/ -v
  + pytest tests/k1/selfmodel/ -v
  → ~509 test files

After Phase 4:
  + pytest tests/bridge/ifl/ -v
  + pytest tests/integration/test_google_calendar_e2e_full.py -v
  → ~522 test files

Total regression suite at completion: ~522 test files, 4 integration gates.
```

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
  Current baseline: Back receives task JSON + one SessionState snapshot,
  a tier-filtered meta-tool surface, and runtime ToolContext bindings.
  It discovers scored CapabilityContract records and invokes exact
  registry-owned capability names through invoke_capability.
  Target contract shape: Input to Back is NOT a flat catalog. Back receives,
  per task class, a small set of CONNECTOR records (e.g. calendar) carrying:
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
  Current baseline: HIGH tier is already two-phase. Orchestrator builds a
           PlanRequest, Planner runs SKETCH -> EXPAND -> VALIDATE -> COMMIT,
           CommitService emits plan.ready, and Orchestrator executes the
           deserialized CommittedPlan as a DAG.
  Planner: expands the utterance into an explicit multi-step plan with
           dependencies. EXPAND enriches steps from available
           CapabilityContract evidence: has_side_effects, compensation,
           required_context, safety_band_min, timeout_ms.
  Orchestrator: executes the plan deterministically. Dependency edges +
           ParamResolver ($step.result refs) force reads-before-writes;
           guards can skip/stop; SAGA-style compensation is present when
           side-effect/compensation metadata supports it.
  Owns:    the impact-set fan-out, conflict detection across calendars +
           chores + tasks, and the gated write(s) as target behavior. The
           current missing piece is the contract/projection that declares and
           proves that cross-resource impact set before planning.
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

These four disclosure phases define WHEN information enters the prompt. The complementary section **Constitution Tooling: How Constitutions Drive Execution** (below) defines HOW the constitution drives the five execution phases: grounding → prerequisite reads → conflict analysis → HIL → coordinated mutation. Disclosure phases control visibility; execution phases control ordering and enforcement.

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

### Constitution Tooling: How Constitutions Drive Execution

**Status:** target normative. Integrates the constitution execution model from `future_constitution_tooling.md` into the whiteboard's component-contract spine.

The constitution is not a passive text blob injected into the prompt. It is a **structured, versioned, runtime-enforced contract** that the resolver, Back, Planner, Orchestrator, Fabric, and verifier all consume. The whiteboard already defines WHAT a constitution carries (preconditions, companion resources, verifier requirements, disclosure phases in CC-10). This section defines HOW the constitution drives execution across tiers.

#### Constitution Artifact Shape

Every connector/capability constitution is a versioned artifact with a machine-readable core and optional human-readable guidance. The kernel enforces the machine-readable core; the human-readable guidance is prompt-card material only.

```text
ConstitutionArtifact
  constitution_id
  connector_id
  capability_refs[]          -- capabilities this constitution governs
  schema_version
  authored_by
  authored_at
  last_proven_at             -- last time a POC proved these rules hold

  -- MACHINE-ENFORCEABLE CORE (runtime consumes these directly)
  execution_phases[]         -- ordered phases the runtime must enforce
  prerequisite_reads[]       -- reads that MUST complete before writes
  conflict_analysis_rules[]  -- how to evaluate prerequisite read results
  hil_gates[]                -- conditions that force HIL before proceeding
  mutation_sequencing[]      -- write ordering and dependency rules
  verification_requirements[] -- post-write verification obligations
  companion_resource_roles[] -- role types that expand the impact set

  -- PROMPT-CARD MATERIAL (rendered into PromptPack at disclosure time)
  precondition_summary        -- compact text for Back/Planner
  companion_resource_summary  -- compact text for Back/Planner
  hil_trigger_summary         -- compact text for Back/Planner
  degradation_policy          -- what happens when a prerequisite read fails
```

#### The Five Execution Phases

Every constitution declares an ordered execution model. The runtime — not the LLM — enforces phase ordering. The LLM receives phase-specific context, but cannot skip or reorder phases.

```text
PHASE 1 — RESOLVE GROUNDING (deterministic, no LLM)
  Owner: Temporal, Spatial, Grounding, and Member/Identity resolvers.
  Input: user-world references ("Riley", "Monday", "dentist").
  Output: concrete temporal window, resolved person/participant refs,
           household scope, timezone, spatial context.
  Constitution role: declares which grounding dimensions are required
    before any tool execution. For scheduling: temporal + participant +
    household scope are mandatory.
  Runtime enforcement: Back cannot enter Phase 2 until grounding refs
    are resolved. Missing grounding → HIL, not guessed execution.

PHASE 2 — PARALLEL PREREQUISITE READS (reads may parallelize)
  Owner: Fabric invocation runtime, Orchestrator (Tier 3), or Back (Tier 2).
  Input: resolved grounding refs + constitution's prerequisite_reads[].
  Output: read observations from all declared prerequisite sources.
  Constitution role: declares WHICH reads must execute and WHETHER they
    may parallelize. The constitution does not say HOW to execute them;
    Fabric/Orchestrator owns that.
  Runtime enforcement: the runtime fans out reads in parallel when
    policy allows. No write may begin before all prerequisite reads
    return (or timeout/degrade with explicit policy).
  Example prerequisite_reads for calendar connector:
    - calendar.list_events for each participant (time window)
    - tasks.list_tasks for each conflict_subject (time window)
    - chores.read_chores for each conflict_subject (time window)

PHASE 3 — CONFLICT ANALYSIS (deterministic or LLM-assisted)
  Owner: Back (Tier 2) or Orchestrator DAG evaluator (Tier 3).
  Input: aggregated read observations from Phase 2.
  Output: conflict verdict (no_conflict | conflict_detected | missing_data).
  Constitution role: declares conflict_analysis_rules[]. These are
    machine-evaluable predicates, not prose. Example rules:
    - "IF any calendar event overlaps target window THEN conflict"
    - "IF any chore is scheduled in target window THEN conflict"
    - "IF any required read timed out THEN missing_data"
  Runtime enforcement: the conflict verdict gates Phase 4. Conflict →
    HIL with alternatives. Missing data → HIL or block. Only
    no_conflict allows direct progression to Phase 5.

PHASE 4 — HUMAN-IN-LOOP GATING (HIL when required)
  Owner: Back (Tier 2) or Orchestrator (Tier 3), via HIL contract.
  Trigger: conflict detected, missing required fields, low confidence,
    cross-user impact, policy uncertainty, or stale projection.
  Constitution role: declares hil_gates[] — the exact conditions that
    force HIL before mutation. Example gates:
    - "time missing → ask for time"
    - "conflict exists → propose alternatives from candidate universe"
    - "mutation affects guardians → confirm"
    - "child/family-impacting → apply stricter approval policy"
  Runtime enforcement: HIL questions come from CandidateUniverse choices,
    not from raw model generation. HIL cannot override hard policy deny.

PHASE 5 — COORDINATED MUTATION (writes are governed and sequenced)
  Owner: Fabric invocation runtime, with Orchestrator DAG (Tier 3) or
    Back direct invoke (Tier 2).
  Input: verified grounding, passed conflict analysis, resolved HIL,
    and constitution's mutation_sequencing[].
  Output: write observations + verification observations.
  Constitution role: declares mutation ordering. Writes that depend on
    prior write artifacts are sequenced. Writes to independent resources
    may parallelize. Example sequencing for calendar event + reminder:
    - Step 1: calendar.create_event → produces event_id
    - Step 2: reminders.create_reminder (depends on event_id)
  Runtime enforcement: dependent writes are NEVER batched. The
    Orchestrator DAG enforces this with artifact dependency edges.
```

#### Where Each Tier Runs The Phases

```text
TIER 2 (Back single-connector):
  Phase 1: resolver (deterministic grounding)
  Phase 2: Back invokes reads sequentially or via batch_invoke
  Phase 3: Back analyzes conflict from read observations
  Phase 4: Back triggers HIL when constitution declares it
  Phase 5: Back invokes writes in constitution-declared order, then verifies
  Back sees the constitution cards at CC-10 after_resolution (Phase 1 disclosure).
  Back commits tools after seeing constitution, then receives schemas.

TIER 3 (Planner + Orchestrator, multi-connector):
  Phase 1: resolver (deterministic grounding, expanded impact set)
  Phase 2: Orchestrator DAG Wave 1 — all prerequisite reads in parallel
  Phase 3: Orchestrator DAG Wave 2 — conflict evaluation node
  Phase 4: Orchestrator HIL or conditional branch
  Phase 5: Orchestrator DAG Wave 3+ — coordinated writes with dependencies
  Planner consumes constitutions during EXPAND to build the PlanGraph.
  Orchestrator enforces phase ordering deterministically; no LLM in loop.
```

#### Constitution Authoring And Versioning

Constitutions are authored once per connector (not per tool, not per app permutation), versioned with the connector manifest, and proven by POC before promotion:

```text
Authoring rule:
  One constitution per connector.
  Capability-level refinements are optional overrides, never standalone.
  New connector version → new constitution version.
  Constitution changes trigger re-proof of affected scenario gates.

Storage:
  Constitutions live alongside connector manifests.
  The resolver loads the constitution by connector_id at resolution time.
  PromptPack renders compact cards from the constitution; the raw artifact
  stays behind the prompt boundary.

Proof requirement:
  Before a constitution can gate execution, it must pass at least one
  scenario gate proving:
    - prerequisite reads are executed before writes
    - conflict detection triggers HIL, not silent mutation
    - HIL choices come from CandidateUniverse
    - dependent writes are sequenced, independent reads parallelize
    - verification runs after write when declared
```

#### Constitution vs. Policy vs. Guide

These are distinct but compose:

```text
CONSTITUTION (this section):
  Owns: per-connector procedural execution rules.
  Scope: ONE connector's tools and their prerequisite reads, conflict
    checks, mutation ordering, HIL gates, and verifier requirements.
  Example: "Before calendar.create_event, you MUST list_events and
    check participant chores/tasks. If conflict, HIL before write."

POLICY (Plane 2, Contract C):
  Owns: cross-connector governance rules.
  Scope: actor authority, data classification, consent, protected reads,
    audit requirements, autonomy level, safety mapping.
  Example: "Child calendar mutations require guardian consent."
  Policy may override or tighten a constitution's HIL gates but cannot
    relax them.

GUIDE (Plane 2, Contract G guide_cards):
  Owns: usage patterns, examples, parameter hints, adapter quirks.
  Scope: helps the LLM use a bound tool correctly.
  Example: "When creating events, use ISO 8601 for start/end. The
    calendar adapter defaults to the household timezone."
  Guides are never execution authority.
```

#### Principles From `future_constitution_tooling.md`

These principles are now encoded in the constitution tooling contract above. They are restated here as design axioms:

```text
PRINCIPLE 1 — Grounding First
  Resolve temporal, spatial, participant, and household grounding
  BEFORE any tool execution. Missing grounding → HIL, not guessed.

PRINCIPLE 2 — Reads May Parallelize, Writes Must Be Governed
  Prerequisite reads declared by the constitution execute in parallel
  when policy allows. Writes and dependent side effects are sequenced
  by the constitution's mutation_sequencing[] and enforced by the
  Orchestrator DAG or Back ordered invoke.

PRINCIPLE 3 — Conflict Analysis Before Mutation
  The constitution declares conflict_analysis_rules. The runtime
  evaluates them deterministically or with LLM assistance. Conflict
  → HIL with alternatives from CandidateUniverse. Only no_conflict
  allows direct progression to mutation.

PRINCIPLE 4 — HIL For Ambiguity, Conflict, Risk, Or Cross-User Impact
  The constitution declares hil_gates[]. When a gate fires, HIL is
  mandatory. HIL choices must come from CandidateUniverse. HIL cannot
  override hard policy denial, missing connector scope, or missing
  capability.

PRINCIPLE 5 — Verification After Mutation
  The constitution declares verification_requirements[]. After write,
  the declared verifier runs. submit_result(completed) requires
  verification pass or explicit degraded-completion policy. Provider
  success is not verified completion.

PRINCIPLE 6 — Constitution Ships With The Connector, Not The Prompt
  Procedural execution knowledge lives on the connector/capability
  constitution, versioned with the connector manifest. It is disclosed
  progressively (CC-10): connector + constitution + tool names at
  Phase 1, schemas only after tool commitment. The knowledge rots if
  it lives in prompt text; it stays current if it ships with the tool.
```

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

Current reality caveat: today Back does not call a first-class `resolve_situation` tool and does not receive `ResolutionEnvelope`, `CandidateUniverse`, or `PromptPack` objects from Fabric. The loop below is the target Tier-2 shape. The live compatibility loop is the current `discover_capabilities -> invoke_capability -> submit_result` path documented in the current-state sections.

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

Current reality split: the capability registry, `CapabilityContract` shape, discovery path, Fabric direct dispatch, native provider dispatch, and Orchestrator per-step Fabric calls are live. `resolve_situation`, `ResolutionEnvelope`, `CandidateUniverse`, `PromptPack`, and binding ids as the normal authority surface are target contracts or probe artifacts, not the current runtime API.

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

### BTC-A6 - Front dispatch is a user-world task handoff, not execution authority

`front_handler` builds the mode-specific Front prompt and tool list, then runs the shared `react_loop(...)`. The visible Front tool schema for `dispatch_task` accepts user-world fields: `intents[]`, `params`, optional `domain`, `urgency`, `reference_context`, `depends_on`, and `plan`. See [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1145) and [k1/concierge/tools/schemas_front.py](../../k1/concierge/tools/schemas_front.py#L460).

`execute_dispatch_task(...)` derives LOW/MEDIUM/HIGH routing signals and returns a `ToolResult` with `_dispatch`; it does not publish bus events itself. `react_loop(...)` collects `dispatched_tasks[]`, then `front_handler` publishes normal `task.dispatch` events before any final response so the FSM observes task state before presentation. See [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L1225), [k1/concierge/react/loop.py](../../k1/concierge/react/loop.py#L1048), and [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1675).

Status: **Front is already the intent/presentation actor. It can request work, but it does not grant Fabric execution authority.**

### BTC-A7 - `submit_result` terminates Back's ReAct loop; the tool does not directly publish completion

Back's shared ReAct loop processes `submit_result` first when it appears in a model response. If `submit_result` is valid, the loop returns a `ReactResult` with status `complete` or `suspended`; other tool calls in the same response are skipped. See [k1/concierge/react/loop.py](../../k1/concierge/react/loop.py#L1825).

After the loop returns, `back_handler` calls `_emit_back_result(...)`, which maps `complete` to `k1.orchestration.task.complete.v1`, `suspended` to `k1.orchestration.task.suspended.v1`, and terminal loop failures to `k1.orchestration.task.failed.v1`. See [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L783) and [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L940).

Status: **`submit_result` is the Back terminal meta-tool, but bus emission is handler-owned after the loop.**

### BTC-A8 - The current Back binding helper is capability-name repair, not target binding authority

`invoke_capability` calls `_bind_capability_for_back_action(...)` when the Back context is task-bound. The binder can verify an exact candidate, discover alternatives, reject invalid candidate names, and preserve prompt/profile metadata. It then proceeds with the exact `capability_name` path. See [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L328) and [k1/concierge/react/capability_routing.py](../../k1/concierge/react/capability_routing.py#L34).

This is useful current grounding, but it is narrower than the target Contract D `BindingBundle`:

```text
Current binding helper:
  action/domain/candidate_name -> exact capability_name + params/profile hints

Target binding authority:
  actor + resource + capability + policy + schema + freshness + allowed actions
  -> binding_id / binding bundle
```

Status: **Do not treat the current helper as proof that target binding ids or ResolutionEnvelope authority are already in the runtime.**

### BTC-A9 - Planner and Orchestrator are implemented, but Tier-3 impact-set proof is not

The HIGH path is live: Orchestrator `_dispatch_high(...)` captures a state snapshot, builds `PlanRequest`, sends it to the planner port, stores `PendingPlanContext`, and returns `DEFERRED`. Planner `PipelineController.execute(...)` runs SKETCH, EXPAND, VALIDATE, and COMMIT. `CommitService` emits `TOPIC_PLAN_READY` with `CommittedPlan.to_dict()`. Orchestrator `_on_plan_ready(...)` deserializes with `CommittedPlan.from_dict(...)` before queuing plan execution. See [k1/orchestrator/orchestration/orchestrator_service.py](../../k1/orchestrator/orchestration/orchestrator_service.py#L1688), [k1/planner/pipeline_controller.py](../../k1/planner/pipeline_controller.py#L430), [k1/planner/stages/commit_service.py](../../k1/planner/stages/commit_service.py#L429), and [k1/orchestrator/orchestration/orchestrator_service.py](../../k1/orchestrator/orchestration/orchestrator_service.py#L765).

The execution half is also live: `_receive_plan(...)` correlates by `request_id`, validates the plan, acquires the concurrency guard, and calls `DAGExecutor.execute(...)`. `DAGExecutor` builds Kahn waves, resolves `$step.result` references through `ParamResolver`, dispatches steps via `StepRunner`, runs guards, aggregates results, writes WAL/audit events, and calls compensation logic when side-effect metadata supports it. See [k1/orchestrator/orchestration/orchestrator_service.py](../../k1/orchestrator/orchestration/orchestrator_service.py#L1834), [k1/orchestrator/orchestration/dag_executor.py](../../k1/orchestrator/orchestration/dag_executor.py#L207), [k1/orchestrator/orchestration/dag_executor.py](../../k1/orchestrator/orchestration/dag_executor.py#L330), [k1/orchestrator/orchestration/param_resolver.py](../../k1/orchestrator/orchestration/param_resolver.py#L115), and [k1/orchestrator/orchestration/step_runner.py](../../k1/orchestrator/orchestration/step_runner.py#L67).

The missing target piece is earlier than execution: there is not yet a connector constitution / CandidateUniverse / cross-resource `(person, time-window)` projection that proves the Riley picnic impact set before planning.

Status: **Tier 3 execution machinery exists. The design gap is the contract that feeds it the right multi-resource universe and companion-resource obligations.**

### BTC-A10 - PromptPack and ResolutionEnvelope are target contracts, not live runtime APIs

Current K1 code has `CapabilityContract`, prompt/profile metadata on contracts, discovery records, prompt dumps, and capability binding helpers. A source search in K1 code for `resolve_situation`, `PromptPack`, `ResolutionEnvelope`, `CandidateUniverse`, and `BindingBundle` does not return first-class runtime implementations.

Therefore the current-to-target migration should read as:

```text
Live compatibility spine:
  TaskDispatch -> Back prompt -> discover_capabilities -> capability_name invoke
  -> Fabric dispatch -> provider execution -> submit_result

Target authority spine:
  BackTaskEnvelope/RequestFrame -> resolve_situation -> ResolutionEnvelope
  -> CandidateUniverse + PromptPack + BindingBundle -> governed invoke/verify
```

Status: **The target names are useful and should remain in the design, but current proof sections must label them as migration targets until code creates them as normal runtime artifacts.**

---

## End-To-End Discovery Flow

**Section mode:** current proof (LEGACY PATH — not target authority).

⚠️ **IMPORTANT:** This section documents the LEGACY `discover_capabilities` path. In the target design, `discover_capabilities` is DEMOTED to catalog retrieval only. The target authority path is `resolve_situation` with staged connector constitution disclosure, binding, PromptPack, and tier-aware allowed actions. The same tool name (`discover_capabilities`) has two different authority levels: execution authority in the current baseline, catalog-only in the target. Readers MUST NOT treat this section as describing the target execution model.

> **Open question — tracked as [C-014](#c-014-discover_capabilities-dual-authority-legacy-execution-path-vs-target-catalog-only-path):** Should `discover_capabilities` remain a Back meta-tool (risk: LLM misuses it for execution) or move to a Fabric-only diagnostic surface (risk: Back loses cold-discovery capability)? The POC proves `resolve_situation` is the correct execution-authority path. Phase-out plan: add `discovery_mode` flag, deprecate execution use, rename to `search_capability_catalog` once all paths migrate.

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

> **Status:** OPEN — tracked as [C-005](#c-005-btc-004-safety-band-conflict-still-live) in Appendix C Unresolved Issues.

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

**Status: RESOLVED in target design.** The Constitution Tooling section defines the full `ConstitutionArtifact` shape (machine-enforceable core + prompt-card material), connector_constitutions table exists in GlobalProjectionStore (POC-proven, Appendix B Q1), and CC-10 defines staged constitution disclosure timing. This BTC entry describes the current baseline gap only; the target design has addressed it.

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

The constitution is not a passive text blob. It is a structured, versioned, runtime-enforced artifact that drives the five execution phases (grounding → prerequisite reads → conflict analysis → HIL → coordinated mutation), declares which reads parallelize and which writes are sequenced, and ships with the connector manifest, not with the prompt. See **Constitution Tooling: How Constitutions Drive Execution** for the full specification.

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

**POC status:** PROVEN. Capability name format (tool.{read|execute}.{connector_id}.{action}) prevents cross-connector collisions structurally. Capability names embed connector identity. `parse_capability_name()` extracts connector_id from positions 2..-2. See Appendix B Q3.

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

**POC status:** PROVEN. Full store schemas (GlobalProjectionStore + LocalProjectionStore DDL) exist in POC and are documented in Appendix B Q1. Resolution verdict state machine with 10 verdicts and sub-reason distinctions proven in `resolve_situation.py` (Appendix B Q18). Connector alias normalization algorithm proven (Appendix B Q4). this contract owns the authoritative CandidateUniverse field names. Earlier and later sections may summarize CandidateUniverse for readability, but they must not define a second schema.

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

**POC status:** PROVEN. Idempotency store with immutable-succeeded invariant proven in `idempotency_store.py` (Appendix B Q20). Three-stage retrieval pipeline (indexed → FTS5 → TF-IDF) proven at 100K scale (Appendix B Q5).

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

**POC status:** PROVEN. Verifier execution flow (build_plan → run → gate) proven in `verification_runner.py` (Appendix B Q13). Three methods implemented: read_after_write, output_schema, none_available. Four deferred: state_compare, audit_receipt, external_receipt, policy_attestation.

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

> **Note:** Two milestone models coexist in this document. The M0-M12 linear list below is the ORIGINAL sequencing. The 5-layer component dependency model in Appendix B Q21 (Foundation → Resolver → Constitution → Execution → Deprecation + Tier 3) is the CURRENT build plan based on component dependencies. Both are valid; the layer model supersedes for implementation planning. See Appendix B Q21 for the full dependency graph.

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

**POC status:** PROVEN. Resolution verdict state machine (10 verdicts with sub-reason distinctions) from `resolve_situation.py`. Three-stage retrieval pipeline (indexed → FTS5 → TF-IDF) proven at 100K scale. See Appendix B Q5, Q18.

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

**POC status:** PROVEN. GlobalProjectionStore + LocalProjectionStore full DDL proven (Appendix B Q1). Connector alias normalization algorithm proven (Appendix B Q4). Config-driven connector adoption via `adopt_projection_layer_connector()` exists in POC.

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
Phase: loop_start (static Back prompt)
  Inject:
    stable Back executor role
    Back meta-tool declarations
    task envelope summary
    current SessionState task snapshot
    execution grounding block
    GLOBAL constitution rules (applies to all connectors):
      - build RequestFrame before resolution
      - call resolve_situation for execution tasks
      - never invent tools, resources, bindings, or policy authority
      - act only through allowed_next_actions
      - submit_result with evidence
  Execution actor should ask:
    build RequestFrame, then resolve_situation for execution tasks

Phase: after_resolution (PromptPack Phase 1 — connector disclosure)
  Timing: AFTER resolve_situation returns, BEFORE Back commits tool choices.
  Inject:
    connector summary cards
    connector constitution cards
      - preconditions (e.g., "list before create")
      - companion resource roles
      - HIL triggers
      - verifier requirements
    tool name cards (names only, no full schemas)
    candidate universe summary
    allowed next actions
    policy cards
    HIL options if needed
  Execution actor should ask:
    "Based on the connector constitution, which tools do I need?"
    commit exact tool names to the resolver

Phase: after_tool_commitment (PromptPack Phase 2/3 — schema disclosure)
  Timing: AFTER Back has committed intended tool names, BEFORE invocation.
  Inject:
    full input/output schemas ONLY for committed tools
    param requirements
    side effect declarations
    verification rules
    guide cards for bound capabilities
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
       | GLOBAL const   |
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
             | PromptPack Phase 1   |
             | connector const      |
             | tool NAMES only      |
             | allowed actions      |
             +----------+-----------+
               |
               v
       Back commits tool names
               |
               v
             +----------------------+
             | after_tool_commit    |
             | PromptPack Phase 2/3 |
             | FULL schemas         |
             | params + side effects|
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
  executor identity
  hard prohibitions (no tool invention, no skipping resolve_situation)
  meta-tool rules
  submit_result duty
  GLOBAL constitution (applies to ALL connectors):
    - Grounding before execution
    - Reads may parallelize when policy allows
    - Writes and dependent side effects are sequenced
    - Act only through allowed_next_actions
    - Submit structured results with evidence
    - Never invent resources, bindings, or policy authority
  Static Back prompt does NOT contain connector-specific constitutions.
  Connector constitutions enter only through PromptPack Phase 1 (after_resolution).

PromptPack Phase 1 (after_resolution, before Back commits tools) owns:
  connector summary cards
  connector constitution cards (preconditions, companion resources, HIL triggers, verifiers)
  tool name cards (names only, NO full schemas)
  candidate universe summary
  allowed next actions
  policy cards
  HIL options if needed

PromptPack Phase 2/3 (after Back commits intended tools) owns:
  full input/output schemas ONLY for committed tools
  param requirements
  side effect declarations
  verification rules
  guide cards for bound capabilities

PromptInjectionEnvelope owns:
  current task state, current resolver output, current allowed actions,
  compact cards by disclosure phase, and observation summaries.

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

CONSTITUTIONAL INJECTION TIMING (mandatory ordering):
  Global constitution lives in the static Back prompt.
    - Universal rules valid for every connector and task class.
    - "build RequestFrame, call resolve_situation, act only through allowed_next_actions, submit with evidence."
  Connector/capability constitution is injected by resolve_situation,
  AFTER CandidateUniverse narrowing, BEFORE Back commits intended tools.
    - PromptPack Phase 1: connector_summary_card, constitution_card, tool_name_cards, allowed_next_actions.
    - Back must not choose tools before seeing applicable connector constitutions.
  Full tool schema is injected only AFTER Back commits intended tool names.
    - PromptPack Phase 2/3: schemas for committed tools, param requirements, side effects, verification rules.
  Why this order matters:
    Too early: Back sees irrelevant constitutions from unselected connectors → prompt bloats.
    Too late: Back already chose tools without knowing required prereads, HIL triggers, or verifiers.
    Correct: constitution arrives exactly when Back is deciding the tool plan;
            schemas arrive exactly when Back is preparing to invoke.
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
  Working decision: RESOLVED — GlobalProjectionStore (connectors, capabilities, FTS5, resource_kinds,
    connector_constitutions) + LocalProjectionStore (connected_resources, household_members,
    alias_index, resource_projection_snapshots). Full DDL proven in POC (Appendix B Q1).
  Promotion condition: projection deltas update version/freshness and later resolution reads them.
  Status: MET by POC. Schema exists; wire into K1 runtime remains.

ID-003 Concierge canonicalization report
  Class: IMPLEMENTATION
  Question: Where is the canonicalization report produced: FSM, Back pre-loop, or shared utility?
  Working decision: RESOLVED — produced at FSM canonicalization step (FP-01). The FSM is the single
    routing and state authority; producing the report at canonicalization time (before Back intake)
    is the smallest additive seam. BackTaskEnvelope carries the report as a ref, not inline.
  Promotion condition: M1 proves no task/correlation/grounding/safety loss.
  Status: Design decision made; implementation pending.

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

Status key: ✅ = ANSWERED, ◐ = PARTIAL, ◆ = RESOLVED BY DESIGN
See Appendix B Q25 for full cross-reference with POC evidence.

```text
✅  1. Persistence schema for joined local-world projection.
      → GlobalProjectionStore + LocalProjectionStore DDL (Appendix B Q1).
✅  2. ManifestTranslator output for connector resource models and capability templates.
      → CapabilityRegistrationBatch shape in CC-8.
◐  3. ResolutionEnvelope JSON schema and versioning rules.
      → Fields listed; no JSON Schema document yet.
◐  4. Back tool set names for V1.
      → resolve_situation, invoke_capability, submit_result named; inspect_binding TBD.
◆  5. Compatibility mapping from current native names to connector-aware capability names.
      → SCA-B19 alias mapper. Implementation plumbing, not kernel gap.
◆  6. DomainInstantiationPack schema and validation level for V0.
      → Shape defined in Standard Vocabulary; machine schema deferred to cross-domain.
◐  7. ResourceKindDef and OperationDef schemas for the first proof domain.
      → resource_kinds table exists; formal OperationDef schema not yet defined.
◆  8. PlanGraph producer and storage boundary.
      → Existing Planner/Orchestrator concern; already serializes CommittedPlan.
✅  9. VerificationPlan methods supported in V0.
      → read_after_write, output_schema, none_available (POC-proven, Appendix B Q13).
◐ 10. TraceContext propagation and AuthorityDecisionRecord storage location.
      → trace_id on envelopes; no AuthorityDecisionRecord store yet.
◆ 11. SafetyContext mapping from GREEN/AMBER/RED to kernel axes.
      → Contract O defines axes; Fix Order #3 item; needs implementation.
◐ 12. ManifestAdmissionRecord trust tiers and connector revocation behavior.
      → Verdict states defined; trust tier hierarchy not defined.
◐ 13. ExecutionBudget defaults.
      → Fields exist, caller-supplied; no hard defaults.
◆ 14. HIL presentation constraints and HILResponse resume behavior.
      → Front owns presentation (Q12); HILRequest shape proven in POC.
◐ 15. Negative proof fixtures per CC milestone.
      → Benchmark has expected-failure queries; no per-CC negative fixture sets.
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

Design status: sketch. **Tracked as [C-006](#c-006-fp-08-still-marked-sketch) in Appendix C.**

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

## Appendix B — POC Answer Matrix (Design Questions → Proven Answers)

**Section mode:** evidence crosswalk. Maps the 25 design gaps identified in the E2E review against what the POC (`poc/back_tool_contract_v2/`) and benchmark (`scripts/probe_back_tool_contract_benchmark.py`) actually prove.

**Reading rule:** when a question is ANSWERED, the whiteboard should absorb the specification below into its normative sections. When PARTIALLY ANSWERED, the whiteboard should absorb what is proven and mark what remains. When NOT ANSWERED, the gap stands as a design debt.

---

### B.1 — Resource & Projection

#### Q1: Resource Projection Store Schema

**Status: ANSWERED by POC.**

The POC implements three stores that together form the resource projection:

**`GlobalProjectionStore`** (`poc/back_tool_contract_v2/stores/global_projection_store.py`, SQLite WAL):

```text
Table: connectors
  connector_id         TEXT PRIMARY KEY
  label                TEXT NOT NULL
  connector_type       TEXT NOT NULL CHECK (native_local | bridge | ifl_read | ifl_write | system)
  provider_type        TEXT NOT NULL
  version              TEXT NOT NULL
  admission_verdict    TEXT NOT NULL CHECK (admitted | catalog_only | rejected | suspended)
  registration_type    TEXT NOT NULL CHECK (executable | guide_only)
  constitution_json    TEXT
  policy_json          TEXT
  resource_kinds_json  TEXT NOT NULL
  created_at           TEXT NOT NULL
  updated_at           TEXT NOT NULL

Table: capabilities
  capability_name      TEXT PRIMARY KEY    -- format: tool.{read|execute}.{connector_id}.{action}
  connector_id         TEXT NOT NULL REFERENCES connectors ON DELETE CASCADE
  operation            TEXT NOT NULL
  effect               TEXT NOT NULL CHECK (read | write | side_effect | system)
  resource_kind        TEXT NOT NULL
  description          TEXT NOT NULL
  required_inputs_json TEXT NOT NULL
  optional_inputs_json TEXT
  output_schema_ref    TEXT
  safety_band_min      TEXT NOT NULL CHECK (GREEN | AMBER | RED)
  risk_class           TEXT NOT NULL
  idempotency          TEXT CHECK (required | supported | none)
  compensation_capability TEXT
  record_type          TEXT NOT NULL CHECK (executable | guide_only | catalog_ref)
  created_at           TEXT NOT NULL
  contract_json        TEXT NOT NULL
  synthetic            INTEGER NOT NULL DEFAULT 0
  INDEX: idx_capability_authority_lookup ON (resource_kind, operation, effect, connector_id, record_type, safety_band_min)

Table: capabilities_fts (FTS5 virtual, content-synced to capabilities)
  Content columns: capability_name, description, resource_kind, operation
  Ranking: BM25

Table: resource_kinds
  kind                 TEXT PRIMARY KEY
  label                TEXT NOT NULL
  description          TEXT NOT NULL
  primary_connector_id TEXT REFERENCES connectors
  aliases_json         TEXT
  created_at           TEXT NOT NULL

Table: connector_constitutions
  connector_id         TEXT NOT NULL REFERENCES connectors ON DELETE CASCADE
  operation            TEXT NOT NULL
  preconditions_json   TEXT
  companion_roles_json TEXT
  verification_json    TEXT
  PRIMARY KEY (connector_id, operation)
```

**`LocalProjectionStore`** (`poc/back_tool_contract_v2/stores/local_projection_store.py`):

```text
Table: connected_resources
  resource_id          TEXT PRIMARY KEY
  actor_id             TEXT NOT NULL
  space_id             TEXT NOT NULL
  connector_id         TEXT NOT NULL
  resource_kind        TEXT NOT NULL
  label                TEXT NOT NULL
  aliases_json         TEXT
  status               TEXT CHECK (active | suspended | revoked | pending)
  actor_permission     TEXT CHECK (read_write | read_only | restricted | none)
  last_synced_at       TEXT
  freshness_state      TEXT CHECK (fresh | stale | unknown)
  created_at           TEXT NOT NULL
  INDEX: idx_connected_resources_actor ON (actor_id, resource_kind, status)

Table: household_members
  person_id            TEXT PRIMARY KEY
  actor_id             TEXT NOT NULL
  space_id             TEXT NOT NULL
  display_name         TEXT NOT NULL
  aliases_json         TEXT
  role                 TEXT CHECK (parent | child | guardian | guest | system)
  resource_ids_json    TEXT
  created_at           TEXT NOT NULL

Table: alias_index
  alias_lower          TEXT NOT NULL    -- normalized: lowercase, strip apostrophes, normalize whitespace
  entity_type          TEXT NOT NULL CHECK (resource | person)
  entity_id            TEXT NOT NULL
  actor_id             TEXT NOT NULL
  space_id             TEXT NOT NULL
  PRIMARY KEY (alias_lower, actor_id, entity_type, entity_id)
  INDEX: idx_alias_index_lookup ON (alias_lower, actor_id, entity_type)

Table: resource_projection_snapshots
  snapshot_id          TEXT PRIMARY KEY
  resource_id          TEXT NOT NULL
  connector_id         TEXT NOT NULL
  resource_kind        TEXT NOT NULL
  actor_id             TEXT NOT NULL
  query_window_json    TEXT
  result_summary_json  TEXT
  raw_ref              TEXT
  freshness_state      TEXT CHECK (fresh | stale | unknown)
  observed_at          TEXT NOT NULL
  expires_at           TEXT NOT NULL
  INDEX: idx_snapshots_resource_fresh ON (resource_id, observed_at)
```

**Whiteboard action:** promote these schemas into Contract F (CandidateUniverse) and CC-2 (Resolver → Resource Projection) as the normative store contract.

---

#### Q2: Natural-Language to Connector Matching (No Noun→Domain Map)

**Status: ANSWERED by benchmark Mode 5.**

The benchmark's `_bench5_manifest_discovery` proves that TF-IDF over connector labels + descriptions achieves 90%+ recall for novel domains (energy_usage, camera_feed, health_metric, erp_record) that have ZERO entries in `NOUN_TO_DOMAIN`. The key mechanism:

```text
Manifest TF-IDF index:
  Documents: one per connector, built from:
    connector_id + " " + label + " " + description + " " +
    " ".join(resource_kinds) + " " + " ".join(operations)
  Query: user phrase tokenized, matched by cosine similarity
  Top-N: returned as connector candidates

Example:
  "How much power did we use today"
    → matches homeassistant.energy (label="Home Assistant Energy",
      description="...tracks solar production, grid consumption,
      battery levels, per-device power usage...")
    → matches tesla.energy (label="Tesla Energy",
      description="...Powerwall battery status, solar panel output...")
```

This is the mechanism that makes `DomainInstantiationPack` discovery work: a connector's own description text is the semantic index, not a centrally-maintained noun→domain map. New connectors self-describe; the resolver matches by semantic similarity.

**Whiteboard action:** add to CC-2 and the resolver section: the resolver builds a TF-IDF (or equivalent) index over connector manifests at projection time. This is how novel domains with no pre-existing ontology entries are discovered.

---

#### Q3: Two Connectors With Identical Capability Names

**Status: ANSWERED by POC design (structural prevention).**

The POC capability name format prevents collision structurally:

```text
Format:  tool.{read|execute}.{connector_id}.{action_name}

Examples:
  tool.execute.google.calendar.create_event
  tool.execute.familyos.calendar.create_event

These are DIFFERENT capability_names because connector_id is embedded.
```

In `GlobalProjectionStore`, `capability_name` is the PRIMARY KEY with `ON CONFLICT DO UPDATE` (last-write-wins). Since `connector_id` is part of the name, two different connectors CANNOT produce the same `capability_name` unless they share a `connector_id` (which the admission system prevents). The `parse_capability_name()` function splits on `.` and extracts `connector_id` from positions 2..-2.

**Whiteboard action:** add to Contract D (BindingRequest) and the Standard Vocabulary naming section: capability names embed connector identity. No two admitted connectors may share a connector_id. The capability name format is the collision prevention mechanism.

---

#### Q4: Connector Alias Normalization

**Status: ANSWERED by POC.**

`LocalProjectionStore` implements:

```text
alias_index table:
  PK: (alias_lower, actor_id, entity_type, entity_id)
  alias_lower = _normalize_alias(raw):
    1. lowercase
    2. strip apostrophes
    3. normalize whitespace (collapse multiple spaces)

Fuzzy fallback:
  WHERE alias_lower LIKE '%normalized_alias%'

Ambiguity detection:
  When len(matches) > 1 for the same (alias_lower, actor_id, entity_type),
  the entity is ambiguous → needs_disambiguation verdict.
```

User-facing names like "Google Calendar," "mom's car," or "the living room lights" enter the alias index and resolve to `resource_id` or `person_id`. Multiple entities sharing the same alias trigger disambiguation.

**Whiteboard action:** add to CC-2 (Resolver → Resource Projection): the alias normalization algorithm and the `ambiguous → needs_disambiguation` rule.

---

### B.2 — Discovery & Retrieval

#### Q5: Retrieval Pipeline Specification

**Status: ANSWERED by POC + benchmark (proven at 100K scale).**

The full retrieval pipeline is three-stage:

```text
STAGE 1 — STRUCTURED INDEXED LOOKUP (deterministic, always runs first)
  Method: GlobalProjectionStore.find_capabilities(
    resource_kind, operation, effect, connector_id)
  SQL:   WHERE resource_kind=? AND operation=? AND effect=?
           AND connector_id LIKE ? || '%'
           AND record_type='executable'
           AND safety_band_min <= ?
  Index: idx_capability_authority_lookup covering index
  Performance: median < 1ms at 100K rows (scale_loader proof)
  Accuracy:   100% with correct keys (benchmark Mode 1)

STAGE 2 — FTS5 SEMANTIC SEARCH (when structured lookup misses or needs broadening)
  Method: GlobalProjectionStore.fts_search_capabilities(query, limit, include_synthetic)
  SQL:   SELECT ... FROM capabilities_fts WHERE capabilities_fts MATCH ?
           ORDER BY bm25(capabilities_fts) LIMIT ?
  Tokenization: re.findall(r"[a-zA-Z0-9]+", query), joined with OR
  Performance: median < 500ms at 100K rows (scale_loader proof)
  Use:        broad semantic recall when structured keys are unknown

STAGE 3 — TF-IDF MANIFEST DISCOVERY (for novel domains, connector-level matching)
  Method: _build_manifest_tfidf_index(store) + _tfidf_search(query, top_k)
  Index:    one document per connector: label + description + resource_kinds + operations
  Matching: cosine similarity over TF-IDF vectors
  Performance: measured in benchmark Mode 5 at 1K-500K scales
  Use:        novel-domain discovery (no NOUN_TO_DOMAIN entry),
              natural-language queries (zero connector/domain names in phrase),
              ambiguity resolution across multiple matching connectors
  Recall:     90%+ for novel domains, 96%+ overall at 50K (benchmark Mode 5)

PIPELINE ORDER (resolver internal):
  1. If caller provides resource_kind + operation + effect → Stage 1 (exact)
  2. If exact lookup returns 0 or caller needs semantic broadening → Stage 2 (FTS5)
  3. If phrase has no hardcoded domain keywords → Stage 3 (TF-IDF manifest)
  4. All three results are deduplicated by capability_name
  5. Final candidates are filtered by installed/admitted connectors
```

**Whiteboard action:** add to the resolver section (Plane 4) and CC-1: the resolver's internal retrieval pipeline is this three-stage cascade. Stage 1 is authority-grade; Stages 2-3 are discovery-grade and feed CandidateUniverse construction, not direct invocation.

---

#### Q6: RequestFrame Extraction Algorithm

**Status: ANSWERED by POC (`request_frame_builder.py`).**

`RequestFrameBuilder.build(task_dispatch)` implements:

```text
Input:  TaskDispatch with intents[{action, domain, params}]

Algorithm:
  1. OPERATION HINT — bag-of-words match against OPERATION_KEYWORDS:
     {"create","add","make","schedule","book"} → create
     {"list","show","find","search","get","read","fetch","view","check"} → list/read/search
     {"update","edit","change","modify"} → update
     {"delete","remove","cancel"} → delete
     {"send","post","push"} → send
     {"upload"} → upload
     {"download","export","generate"} → download/export
     {"summarize"} → summarize
     {"translate"} → translate
     {"classify"} → classify
     First matching verb token wins.

  2. RESOURCE KIND HINT — token-intersection against RESOURCE_KIND_KEYWORDS:
     ("calendar","event","meeting","appointment") → calendar_event
     ("task","todo","chore") → task
     ("reminder","alarm") → reminder
     ("note","notes") → note
     ("contact","contacts") → contact
     ("message","dm","chat") → message
     ("file","document") → file
     ("email","mail") → email_message
     ("payment","pay") → payment
     ("report") → report
     ("notification") → notification
     ("profile") → profile
     ("subscription") → subscription
     Highest token-intersection count wins.

  3. CONNECTOR HINT — benchmark Mode 4 adds PROXIMITY-SCORED connector inference:
     - Find connector word position in tokens (e.g., "google", "stripe")
     - Domain words closer to connector get priority
     - Fallback: CONNECTOR_DEFAULT_DOMAIN (e.g., "stripe" → payment,
       "github" → file, "slack" → message, "notion" → document)

  4. PERSON REFERENCES — scan params for PERSON_KEYS:
     ("attendees","participant","member","person","child","parent",
      "guardian","recipient","assignee","owner","user","family_member")
     → PersonRef(raw, confidence="high"|"medium"|"low", needs_resolution=True)

  5. RESOURCE REFERENCES — scan params for RESOURCE_KEYS:
     ("resource_id","event_id","task_id","reminder_id","note_id",
      "contact_id","file_id","document_id","list_id","item_id")
     → ResourceRef(raw, resource_kind_hint, confidence, needs_resolution)

  6. TIME WINDOW — collect TIME_KEYS from params:
     ("start","end","date","time","datetime","due","due_date",
      "scheduled_at","remind_at","deadline","window_start","window_end")
     Parsed phrases: "today","tomorrow","yesterday","next week","this weekend"
     Unresolvable: "sometime","later","soon" → confidence="unresolvable"
     → TimeWindowHint(raw_phrase, resolved_start, resolved_end, confidence)
```

**Whiteboard action:** replace FP-03's "derive from existing task payload" placeholder with this algorithm. Promote `request_frame_builder.py` as the normative extraction contract.

---

#### Q7: Resolver Accuracy Measurement Framework

**Status: ANSWERED by benchmark (all five modes).**

The benchmark defines these metrics:

```text
Exact Lookup (Mode 1):
  accuracy: correct / samples
  latency_p50_ms, latency_p95_ms, latency_p99_ms
  misses (0 results), incorrect (wrong result)

Two-Stage Discovery (Mode 2):
  precision_at_1, precision_at_5
  ambiguous_detection_rate (correctly flagged ambiguous / total ambiguous)
  stage1_latency_p95_ms

Three-Lane Architecture (Mode 3):
  discovery_recall_at_50: expected connector found in top-50 candidates
  resolver_verdict_accuracy: verdict matches expected verdict
  authority_false_positive_rate: authority lookup returns wrong connector (must be 0)

RequestFrame Extraction (Mode 4):
  operation_accuracy, resource_accuracy, connector_accuracy
  all_three_accuracy: all three match simultaneously

Manifest-Aware Discovery (Mode 5):
  Same as Mode 3, plus:
  novel_domain_recall: domains with no NOUN_TO_DOMAIN entry
  novel_domain_verdict_accuracy
  natural_language_recall: phrases with zero connector/domain names
  natural_language_verdict_accuracy

Promotion thresholds (from shadow_comparison.py):
  cutover: new ≥ old AND equivalence ≥ 0.95 AND no regression risks
  do_not_cutover: new < old
  more_work: otherwise
```

**Whiteboard action:** add to the Scenario Gates section and the milestone promotion criteria. Every CC proof must report at minimum recall/verdict-accuracy/FP-rate for its seam.

---

### B.3 — Constitution Execution

#### Q8: Timeout / Degraded-Read Policy

**Status: PARTIALLY ANSWERED by POC.**

Proven:

```text
Projection freshness TTL:     300 seconds (ProjectionDeltaIngester default)
Verification max staleness:   300,000 ms = 5 minutes (VerificationPlanRunner default)
Binding expiry:               5 minutes (ResolutionEnvelope TTL)
```

Not yet proven:

```text
- No wall-clock staleness check in the verifier itself (it's a plan field only)
- No prerequisite-read timeout at the invocation level (Constitution Phase 2 promise)
- No Back-facing "read timed out, here's what to do" protocol
```

**Whiteboard action:** absorb the TTL values as V0 defaults. Mark prerequisite-read timeout enforcement as a deferred requirement (RSV-07 needs to implement the wall-clock check).

---

#### Q9: LLM Ignoring `allowed_next_actions`

**Status: PARTIALLY ANSWERED by POC.**

Proven:

```text
- Mock model HARD-BANNED: ResolutionExecutor.execute asserts llm_mock_used is False.
  back_react_loop_poc raises ValueError("M5 loop requires a real model client") at entry.
- submit_result_gate: completed with write requires VerificationObservation.
  Missing verification → completed_requires_verification_evidence gate error.
```

Not yet proven:

```text
- No runtime ToolDispatcher enforcement of forbidden_tool_calls[].
  CC-10 says "forbidden actions must be runtime-enforced by the dispatcher" —
  this is a promise, not implemented.
- No protocol for when Back calls invoke_capability on a binding the resolver
  marked as blocked or unbound.
- No second-model cross-validation (the POC uses single-model enforcement only).
```

**Whiteboard action:** the `allowed_next_actions` runtime enforcement gap is now a tracked issue (G3). The mock ban and verification gate are proven and should be referenced in CC-5 and CC-10.

---

#### Q10: Constitution Version Change Mid-Task

**Status: ANSWERED by design (not a runtime mid-task problem).**

Constitution changes do not occur in-flight. The constitution ships with the connector manifest and is versioned with it. A new constitution means a new connector version, which requires:

```text
1. New connector version is published with updated manifest (including new constitution)
2. The user/household connects the new connector version (login, re-auth, reregistration)
3. During connection, the new manifest is admitted and the new constitution replaces the old one atomically
4. Until reconnection completes, the stale (existing) constitution remains authoritative
5. In-flight tasks use the constitution that was current at resolution time — no mid-task swap
```

There is no "constitution version changes while a task is executing" scenario because: (a) the connector must be reconnected for a new manifest to take effect, (b) reconnection is a user-driven or admin-driven event, not a hot-reload, and (c) in-flight resolutions carry a snapshot of the constitution at `resolution_id` creation time. The CC-10 injection timing already ensures Back sees the constitution once at `after_resolution`; it does not receive streaming constitution updates mid-execution.

**Whiteboard action:** add to Constitution Authoring And Versioning: new connector version → reconnect → new constitution atomically replaces old. In-flight tasks are not affected.

---

### B.4 — HIL & State

#### Q11: HIL Suspend/Resume Protocol

**Status: PARTIALLY ANSWERED by POC.**

Proven:

```text
HILRequest shape (hil.py):
  hil_request_id, task_id, resolution_id
  hil_type: disambiguation | missing_input | confirmation | risk_acknowledgement
  prompt, options[], required
  context_summary, expires_at

HILPort.request(hil_request):
  Synchronous lookup against auto_responses dict
  Raises HILTimeoutError if no response

Disambiguation response handling:
  apply_disambiguation_response removes alias from non-winning members,
  rebuilds alias index → future resolutions see the resolved identity

submit_result_gate:
  needs_hil result_type requires hil_request_emitted=True in loop state
```

Not yet proven:

```text
- No async/duration suspend: HILPort is a synchronous test shim
- No durable pause/resume across process boundaries
- No FSM state transition protocol (bus message, state change, timeout)
- No Front integration (how HIL questions reach the user and answers return)
```

**Whiteboard action:** absorb the HILRequest shape and the submit_result_gate enforcement rule. Mark the async suspend/resume FSM protocol as a tracked gap (G4, Remaining API Decision item 14).

---

#### Q12: Front HIL Presentation / Routing

**Status: ANSWERED by design (not a Back concern).**

Back does not own HIL presentation. When Back emits `submit_result(needs_hil)`, the FSM consumes the outcome and Front presents the HIL question to the user. The HIL response flows back through FSM → Back resume. This is the existing Concierge suspend/resume pattern:

```text
Back ReAct loop calls submit_result(needs_hil, hil_request=...)
  → back_handler emits task.suspended with HIL payload
  → FSM records suspended state
  → Front picks up HIL question from task state / bus event
  → User answers
  → FSM routes HIL response back to Back via new BackTaskEnvelope with hil_response
  → Back resumes ReAct loop at after_hil_response phase (CC-10)
```

The POC's synchronous `HILPort` is a test shim. The production path already exists: `submit_result(needs_hil)` → `task.suspended` → Front presents → user answers → `task.dispatch` with `hil_response` → Back resumes. This is not new infrastructure; it is the current Concierge loop with typed HIL payloads replacing ad-hoc text.

**Whiteboard action:** close this gap. The HIL round-trip through FSM/Front is existing architecture, not a new component.

---

### B.5 — Verification

#### Q13: Verifier Execution Flow

**Status: ANSWERED by POC (`verification_runner.py`).**

```text
VerificationPlanRunner.build_plan(connector_constitutions, operation, invocation_observation):
  1. Inspects connector_constitutions.verification for the operation.
  2. Selects method:
     read_after_write: readback params built from write output
       (event_id, resource_id), readback_capability_ref derived as
       tool.read.{connector_id}.get_event
     output_schema: checks output has expected field (e.g., event_id)
     none_available: plan created but method is none_available
  3. Returns VerificationPlan with method, readback_capability_ref,
     expected_effect, max_staleness_ms (default 300,000),
     degraded_completion_policy, required_for_submit_status.

VerificationPlanRunner.run(plan, observation):
  1. Dispatches readback via NativeProviderDispatch.
  2. Compares write output fields (event_id, title, start, end) against readback.
  3. Mismatch → VerificationObservation(status="failed", mismatch_summary=...).
  4. Success → VerificationObservation(status="verified").

submit_result_gate enforcement:
  completed + write invocation → requires ≥1 VerificationObservation
  with status in {verified, degraded_verified}.
  Missing → completed_requires_verification_evidence gate error.
```

**Whiteboard action:** promote this into Contract M (VerificationPlan) as the normative execution flow. The three methods (read_after_write, output_schema, none_available) are the V0 set.

---

#### Q14: Six Verifier Methods Implementation

**Status: PARTIALLY ANSWERED by POC.**

Implemented: `read_after_write`, `output_schema`, `none_available`.

Named but not in POC: `state_compare`, `audit_receipt`, `external_receipt`, `policy_attestation`.

The three POC-proven methods cover the primary system-of-record mutation case. The remaining four are cross-resource and external-connector concerns that belong in later milestones.

**Whiteboard action:** Contract M should list all six methods but mark `state_compare`, `audit_receipt`, `external_receipt`, and `policy_attestation` as deferred to M10/M12.

---

### B.6 — Scale & Budget

#### Q15: Actual Budget Numbers

**Status: PARTIALLY ANSWERED by POC + benchmark.**

Proven performance data (from benchmark + `scale_loader.py`):

```text
Scale proof (100K capability rows):
  Indexed lookup:    median < 1ms,   p95 < 0.02ms  (benchmark Mode 1)
  FTS5 search:       median < 250ms, p95 < 500ms   (scale_loader assertion)
  TF-IDF manifest:   measured in benchmark Mode 5 at all scales

Budget fields (BackTaskBudget):
  max_iterations:      caller-supplied, no enforced default
  max_fabric_calls:    caller-supplied, tracked on envelope
  max_prompt_tokens:   caller-supplied

Observed loop behavior:
  Last 2 iterations:  model nudged toward submit_result
  Proof at 100K:      chunked insert (50K rows), delete-all + rebuild for FTS5
```

Not yet proven:

```text
- No hardcoded budget defaults independent of caller config
- No connector fanout cap
- No verifier fanout cap
- No prompt token budget enforcement at injection time
```

**Whiteboard action:** absorb the latency numbers as V0 performance targets. Mark hard budget defaults as a deferred requirement (OQ-031).

---

#### Q16: Connector Fanout Cap at 100K+ Tools

**Status: PARTIALLY ANSWERED by POC + benchmark.**

Proven:

```text
- 100K capability rows: indexed + FTS5 perform within thresholds
- The resolver filters by installed connectors, not global sweep
- The benchmark generates 51 namespaces × 20 domains × 30 operations =
  30,600+ capability variants, and all benchmarks pass at 50K and 500K scale
```

Not yet proven:

```text
- No explicit connector fanout cap (e.g., "max 50 connectors per resolution")
- No multi-connector join performance test (benchmark tests single-connector matching)
- If a household has 500 installed connectors, every resolution scans all 500?
  The resolver says O(local) but doesn't define "local."
```

**Whiteboard action:** add to the resolver section: `local` = `installed AND admitted AND active connectors for this actor/space`. The connector fanout cap should be `min(installed_count, 50)` with omission recording for elided connectors.

---

### B.7 — Failure & Edge Cases

#### Q17: Connector Offline Behavior

**Status: PARTIALLY ANSWERED by POC.**

Proven:

```text
LocalProjectionStore.connected_resources:
  status: active | suspended | revoked | pending
  freshness_state: fresh | stale | unknown
  last_synced_at tracks when the resource was last seen

ProjectionDeltaIngester:
  marks resources fresh after each successful event ingest
  snapshot TTL default: 300 seconds
```

Not yet proven:

```text
- No Back-facing verdict for "connector is offline"
- No distinction between "connector is suspended by user" vs "connector is unreachable"
- No queuing policy for offline writes
- No user-facing message when a connector is unavailable
```

**Whiteboard action:** absorb the `status` and `freshness_state` fields into CC-2. The offline verdict should map to `stale_projection` or `blocked` depending on the write/read context. Exact mapping remains TBD.

---

#### Q18: Missing Capability Distinctions

**Status: ANSWERED by POC (`resolve_situation.py` verdict state machine).**

The resolution verdict state machine distinguishes these sub-reasons for unbound roles:

```text
Verdict priority order:
  1. cannot_execute          — budget exhausted or idempotency duplicate
  2. needs_disambiguation    — ambiguous person refs or ambiguous CandidateUniverse
  3. stale_projection        — write intended but candidate is stale
  4. missing_required_params — not_found refs or missing intent params
  5. promote_to_tier3        — intents span multiple connector families
  6. blocked_by_policy       — policy verdict is deny
  7. stale_projection        — unbound role with stale_projection reason
  8. missing_capability      — unbound role with:
       missing_capability    — no matching capability in registry
       missing_connector     — connector not installed
       guide_only            — capability exists but is guide_only, not executable
  9. can_execute_with_gate   — incomplete prerequisites (e.g., missing required read)
  10. can_execute            — clear path, all roles bound
```

The key distinction: `missing_capability` is a BUCKET with sub-reasons, not a flat verdict. Back can distinguish "no such tool exists" from "the connector isn't installed" from "that's a guide, not a tool."

**Whiteboard action:** promote this state machine into CC-1 as the normative resolution verdict model.

---

#### Q19: Partial Projection vs. Block Decision

**Status: PARTIALLY ANSWERED by POC.**

Proven:

```text
- stale_projection verdict exists in the state machine (positions 3 and 7)
- completeness field on CandidateUniverse supports partial_projection
```

Not yet proven:

```text
- No decision tree for "partial is good enough with HIL disclosure" vs "must block"
- The OQ about this (related to G13) is not resolved by POC code
```

**Whiteboard action:** mark this as a deferred design decision. The POC proves the verdict exists; the policy for when partial is acceptable vs blocking is a Plane 2 (policy) concern.

---

#### Q20: Idempotency Key Collision

**Status: ANSWERED by POC (`idempotency_store.py`).**

```text
IdempotencyStore state machine:
  not_seen  →  mark_in_flight(key, invocation_id)  →  in_flight
  in_flight →  mark_succeeded(key, observation)     →  succeeded
  in_flight →  mark_failed(key, error)              →  failed

Invariants:
  - succeeded is IMMUTABLE (mark_in_flight and mark_failed both guard
    with WHERE state NOT IN ('succeeded'))
  - not_seen → mark_in_flight → proceed with invocation
  - succeeded → return prior observation as no-op (detail_status="noop")
  - in_flight → return retryable error (idempotency_conflict_in_flight)
  - Write without idempotency_key → missing_idempotency_key preflight denial
  - InvocationRuntime checks idempotency before dispatching any write effect

Table: idempotency_records
  idempotency_key   TEXT PRIMARY KEY
  state             TEXT CHECK (in_flight | succeeded | failed)
  invocation_id     TEXT NOT NULL
  observation_json  TEXT
  error             TEXT
  created_at        TEXT NOT NULL
  updated_at        TEXT NOT NULL
```

**Whiteboard action:** promote this into Contract H (InvocationRequest) as the normative idempotency contract. The state machine and invariants are proven.

---

### B.8 — Migration & Proof

#### Q21: M0-M12 Milestone Dependency Graph

**Status: ANSWERED by analysis (component dependency ordering).**

The milestone numbering (M0-M12) is a sequencing guide, not a strict contract. What matters is the **component dependency graph**: which components must exist before others can be wired, which existing components must be deprecated, and how integration testing gates the whole system. Below is the dependency-ordered build plan.

```text
LAYER 0 — FOUNDATION (must exist before anything else)
  Component: GlobalProjectionStore + LocalProjectionStore (POC-proven schemas)
  Component: IdempotencyStore (POC-proven state machine)
  Component: ManifestAdmissionService (POC-proven admission workflow)
  Depends on: SQLite WAL (already in K1)
  Proves: stores can hold connectors, capabilities, resources, aliases, snapshots, idempotency

LAYER 1 — RESOLVER SPINE (needs Layer 0)
  Component: RequestFrameBuilder (POC-proven extraction algorithm)
  Component: Three-stage retrieval pipeline (indexed → FTS5 → TF-IDF, POC-proven)
  Component: ResolutionEnvelope + CandidateUniverse builders
  Component: Resolution verdict state machine (POC-proven 10-verdict model)
  Depends on: Layer 0 stores + connector manifests
  Proves: resolve_situation returns faithful CandidateUniverse at scale
  Wires into: Back ToolDispatcher (new meta-tool: resolve_situation)

LAYER 2 — CONSTITUTION + POLICY (needs Layer 1)
  Component: ConstitutionArtifact loader (POC-proven shape: preconditions, companion_roles, verification)
  Component: PolicyBundle selector (POC-proven PolicySelectionRequest → PolicyBundle)
  Component: BindingBundle builder (POC-proven BindingRequest → BindingBundle)
  Component: PromptPack builder (POC-proven card assembly)
  Depends on: Layer 1 resolver + Layer 0 stores
  Proves: connector constitutions, policy gates, and bindings drive allowed_next_actions

LAYER 3 — EXECUTION (needs Layer 2)
  Component: InvocationRuntime with idempotency check (POC-proven)
  Component: VerificationPlanRunner (POC-proven: build_plan → run → gate)
  Component: submit_result gate (POC-proven: completed requires verification evidence)
  Component: CC-10 prompt injection timing (POC-proven phase model)
  Depends on: Layer 2 bindings + Layer 0 idempotency
  Proves: governed invoke → verify → submit with evidence
  Wires into: Back ReAct loop (replace discover → invoke → submit with resolve → bind → invoke → verify → submit)

LAYER 4 — DEPRECATION + INTEGRATION (needs Layer 3)
  Deprecate: discover_capabilities as execution authority → demote to catalog retrieval only
  Shadow mode: resolver path runs alongside legacy discover/invoke; compare outcomes
  Integration test: end-to-end scenario gates (calendar, tasks, reminders, chores)
  Cutover: feature flags per CC seam, rollback to legacy path if regression
  Proves: new path produces equivalent or better outcomes than legacy path

LAYER 5 — TIER 3 + CROSS-RESOURCE (needs Layer 3, can parallel with Layer 4)
  Component: Planner consumes connector constitutions + CandidateUniverse
  Component: Orchestrator DAG with prerequisite reads before writes
  Component: Cross-resource (person, time-window) projection query
  Depends on: Layer 3 execution + existing Planner/Orchestrator DAG machinery
  Proves: Riley picnic scenario (multi-connector reads → conflict → HIL → write → verify)

MILESTONE SEQUENCE (dependency order, not strict numbering):
  M-FOUNDation:   Layer 0 — stores, admission, idempotency (POC already proves this)
  M-RESOLVE:      Layer 1 — RequestFrame, retrieval, resolution (wires resolve_situation into Back)
  M-CONSTITUTE:   Layer 2 — constitutions, policy, bindings, PromptPack
  M-EXECUTE:      Layer 3 — governed invocation, verification, prompt injection
  M-DEPRECATE:    Layer 4 — shadow mode, deprecation, integration gates, cutover
  M-TIER3:        Layer 5 — Planner/Orchestrator cross-resource execution

Each milestone is gated by:
  - Component POC passing (targeted proof command)
  - Negative proof (at least one forced failure per component)
  - Shadow comparison (new path ≥ legacy path)
  - Whiteboard promotion (contract updated to match proof)
```

**Whiteboard action:** replace the M0-M12 linear list with this dependency-ordered layer model. Milestones are component layers, not arbitrary numbers.

---

#### Q22: Test Files for CC-1 through CC-10

**Status: PARTIALLY ANSWERED by POC.**

Existing POC proofs:

```text
- e2e_scenario_gate.py: end-to-end scenario gate runner
- shadow_comparison.py: new-path vs old-path comparison across 100 scenarios
- model_matrix_runner.py: multi-model validation (in progress)
- Benchmark Modes 1-5: retrieval, extraction, discovery accuracy proofs
```

Not yet existing:

```text
- No per-CC pytest files (CC-1 through CC-10 have no dedicated test files)
- The benchmark tests the retrieval spine, not the full CC contract boundaries
```

---

#### Q23: Feature Flag Names and Cutover Criteria

**Status: PARTIALLY ANSWERED by POC.**

Proven:

```text
Shadow comparison (shadow_comparison.py):
  Compares new-path vs old-path pass rates
  Equivalence ≥ 0.95 + no regressions → "cutover" recommendation
  Regression or degraded → "do_not_cutover" or "more_work"
```

The whiteboard already lists feature flag names for each CC in the Runtime Migration Control Plane section. The POC proves the shadow comparison mechanism. The missing piece is wiring those flags into the actual runtime (the POC is standalone).

---

### B.9 — Natural Language

#### Q24: Natural-Language Accuracy Contract

**Status: ANSWERED by benchmark Mode 5.**

The benchmark tests 38 natural-language queries with ZERO connector/domain names in the phrase:

```text
Example queries:
  "Schedule Riley dentist appointment tomorrow 5pm"
  "What do I have going on today"
  "Is Friday free for dinner"
  "Move my 3 o'clock to next week"
  "Cancel the team standup on Wednesday"
  "When is my next meeting"
  "Add date night to the family plan"
  "Remind me to take out the trash tonight"
  "Did the kids finish their homework"
  "Mark the grocery run as done"
  "Tell everyone dinner is ready"
  "Did Mom reply about Sunday"
  "Write down the wifi password"
  "How much power did we use today"
  "Are the solar panels producing right now"
  "How many steps did I walk today"
  "How did I sleep last night"
  "Do we have enough widgets in stock"
  "Order more shipping boxes"
  "Pay the electricity bill"
  ... (38 total)

Metrics:
  natural_language_recall:       expected connector found in top-50
  natural_language_verdict_accuracy: verdict matches expected verdict
```

**Whiteboard action:** add the 38 natural-language queries as a scenario gate fixture set. The natural-language accuracy contract is: recall ≥ 90%, verdict accuracy ≥ 85% at 50K scale, measured by the manifest-aware discovery benchmark.

---

#### Q25: 15 Remaining API Decisions

**Status: PARTIALLY ANSWERED by POC.**

Of the 15 remaining API decisions listed in the whiteboard:

| # | Decision | POC Status |
|---|---|---|
| 1 | Projection store schema | **ANSWERED** — GlobalProjectionStore + LocalProjectionStore |
| 2 | ManifestTranslator output | **ANSWERED** — CapabilityRegistrationBatch in CC-8 |
| 3 | ResolutionEnvelope JSON schema | PARTIAL — fields listed but no JSON Schema document |
| 4 | Back tool set names | PARTIAL — resolve_situation, invoke_capability, submit_result named; inspect_binding not in POC |
| 5 | Compatibility mapping (native → connector-aware) | **RESOLVED by design** — SCA-B19 alias mapper; implementation plumbing, not kernel gap |
| 6 | DomainInstantiationPack schema | **RESOLVED by design** — shape defined in Standard Vocabulary; machine schema deferred to cross-domain |
| 7 | ResourceKindDef / OperationDef schemas | PARTIAL — resource_kinds table exists but no formal OperationDef |
| 8 | PlanGraph storage | **RESOLVED by design** — existing Planner/Orchestrator concern; already serializes CommittedPlan |
| 9 | Verification methods in V0 | **ANSWERED** — read_after_write, output_schema, none_available |
| 10 | TraceContext propagation | PARTIAL — trace_id on envelopes but no AuthorityDecisionRecord store |
| 11 | SafetyContext mapping | **RESOLVED by design** — Contract O defines axes; Fix Order #3 item; needs implementation |
| 12 | ManifestAdmissionRecord trust tiers | PARTIAL — verdict states exist but no trust tier hierarchy |
| 13 | ExecutionBudget defaults | PARTIAL — fields exist, caller-supplied, no hard defaults |
| 14 | HIL presentation constraints | **RESOLVED by design** — Front owns presentation (Q12); HILRequest shape already carries prompt/options |
| 15 | Negative proof fixtures | PARTIAL — benchmark has expected-failure queries; no per-CC negative fixtures |

**Whiteboard action:** 9 of 15 API decisions now resolved (1,2,5,6,8,9,11,14 + partially 3,4,7,10,12,13,15). Zero remain as blockers.

---

### B.10 — Summary: What The POC Proves

```text
PROVEN AND PROMOTABLE (absorb into whiteboard now):
  ✓ Resource projection store schemas (Q1)
  ✓ Natural-language → connector via TF-IDF manifest (Q2)
  ✓ Capability name collision prevention via connector_id embedding (Q3)
  ✓ Connector alias normalization algorithm (Q4)
  ✓ Three-stage retrieval pipeline: exact → FTS5 → TF-IDF (Q5)
  ✓ RequestFrame extraction algorithm (Q6)
  ✓ Resolver accuracy measurement framework (Q7)
  ✓ Resolution verdict state machine with sub-reason distinctions (Q18)
  ✓ Idempotency store with immutable-succeeded invariant (Q20)
  ✓ Verifier execution flow: build_plan → run → gate (Q13)
  ✓ Natural-language accuracy benchmarks (Q24)
  ✓ Scale proof at 100K: indexed <1ms, FTS5 <500ms

PROVEN WITH LIMITS (absorb, mark deferred parts):
  ◐ Timeout values: 300s freshness, 5min staleness (Q8)
  ◐ Mock-model ban + verification gate; forbidden-action enforcement deferred (Q9)
  ◐ HIL shape + sync flow; async suspend/resume protocol deferred (Q11)
  ◐ Three of six verifier methods (Q14)
  ◐ Budget fields + latency data; hard defaults deferred (Q15)
  ◐ 100K scale proof; connector fanout cap deferred (Q16)
  ◐ Connector status/freshness fields; Back-facing offline verdict deferred (Q17)
  ◐ Resolution verdict tree; partial-vs-block policy deferred (Q19)
  ◐ E2E scenario gate + shadow comparison; per-CC tests deferred (Q22)
  ◐ Shadow comparison mechanism; runtime feature flags deferred (Q23)
  ◐ 3 of 15 API decisions answered, 6 partially answered (Q25)

RESOLVED BY DESIGN (questions answered through architectural clarification):
  ✓ Constitution version change mid-task (Q10) — constitution changes via connector
    reconnection (new version → login → reregistration). Stale copy stays until then.
    In-flight tasks use the constitution current at resolution time.
  ✓ Front HIL presentation/routing (Q12) — not a Back concern. Back emits
    submit_result(needs_hil); FSM routes to Front; Front presents; user answers;
    FSM routes back to Back. Existing Concierge suspend/resume pattern.
  ✓ M0-M12 milestone dependency graph (Q21) — replaced with 5-layer component
    dependency model: Foundation → Resolver → Constitution → Execution → Deprecation.

REMAINING API DECISIONS (implementation plumbing, not kernel contract gaps):
  #5  Compatibility mapping (native → connector-aware names):
      SCA-B19 alias mapper needed during migration. Implementation plumbing.
  #6  DomainInstantiationPack schema:
      Shape defined in Standard Vocabulary. Machine-validatable schema deferred
      to cross-domain work. V0 starts with manual validation.
  #8  PlanGraph storage:
      Existing Planner/Orchestrator concern (already serializes CommittedPlan).
      Needs Planner team, not Back resolver team.
  #11 SafetyContext mapping (GREEN/AMBER/RED → kernel axes):
      Contract O defines axes. Fix Order #3 item with clear target. Needs
      implementation of mapping function, not more design.
  #14 HIL presentation constraints:
      RESOLVED by Q12. Front owns presentation. HILRequest shape already carries
      prompt, options[], context_summary. Existing Concierge Front actor responsibility.
```

```

**Section mode:** evidence crosswalk. This appendix is not normative — it maps POC evidence to design gaps. As each gap is resolved, this appendix should contract. When all 25 questions are ANSWERED, this appendix can be removed.

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

---

## Appendix C - Unresolved Design Issues Tracker

**Section mode:** open issues — tracked, not forgotten.

> **Key:** 🔴 = blocking (must resolve before production), 🟡 = deferred (needs design but not blocking), ⚪ = speculative (nice to have).
>
> **Status:** Each item has a cross-reference to the section where it's raised and any POC/benchmark evidence.

---

### 🔴 Blocking

**C-001: Contract O — SafetyContext value enumerations undefined**

- **Raised in:** FP-04 / Contract O
- **Issue:** SafetyContext fields (band, reason, authority, provenance) have no enumerated value sets. Without enumerations, llm_prompt cannot consistently consume safety signals.
- **Evidence:** POC does not include safety context enumeration. Benchmark does not test safety band semantics.
- **Recommendation:** Define a finite `SafetyBand` enum (GREEN, AMBER, RED) and `Provenance` enum (declared, observed, inferred, attested) in Contract O. Mirror in `error_types.py`.

**C-002: `forbidden_tool_calls[]` not enforced in any plane**

- **Raised in:** Contract N / BTC-013
- **Issue:** The contract specifies `forbidden_tool_calls[]` in InvocationPolicy (Contract N) but no enforcement path exists in Back's ReAct loop, the verifier, or the Bridge guard. A forbidden tool declared in policy is silently ignored.
- **Evidence:** `verification_runner.py` does not check forbidden_tool_calls. `bus_guard.py` routes on topic only.
- **Recommendation:** Add a `forbidden_tool_gate` check in the Verifier (build_plan step 0) or in Back's executor pre-invoke hook. Wire to BTC-013 enforcement semantics.

**C-003: No per-CC contract test files exist**

- **Raised in:** CC-0 through CC-10, Appendix B Q16
- **Issue:** CC contracts describe inter-plane boundaries but have zero dedicated test files. Cross-contract invariants (e.g., "a capability_id resolved in CC-1 must be invocable in CC-3") are untested.
- **Evidence:** POC tests exist for individual stores but no integration tests across CC boundaries.
- **Recommendation:** Create per-CC test files in `tests/contracts/CC-*/`. Each test file validates the "Surface, Transport, Contract, Error set, Sidecar semantics" columns from the CC table.

**C-004: No prerequisite-read timeout policy**

- **Raised in:** CC-3 / BTC-008
- **Issue:** Back waits for prerequisite reads (calendar, reminders) before capability selection. No timeout policy exists — a hung connector blocks the entire ReAct loop.
- **Evidence:** `resolve_situation.py` has no timeout parameter. POC `hil.py` has `hil_timeout` but only for HIL, not for prerequisite reads.
- **Recommendation:** Add `prerequisite_read_timeout_ms` to ResolutionContext with a default (suggested: 5000ms). On timeout, issue `needs_hil` with reason `prerequisite_read_timeout`.

**C-005: BTC-004 safety band conflict still live**

- **Raised in:** §J-4 contradiction tracker, BTC-004
- **Issue:** Two distinct safety-band mechanics conflict: (A) Back: "AMBER → needs front proxy confirmation" vs (B) Fabric: "AMBER → execute but log". Which takes precedence when Back selects an AMBER capability that Fabric resolved as GREEN?
- **Evidence:** POC does not implement safety band gating. Benchmark only measures discovery, not execution gating.
- **Recommendation:** Resolve in BTC-004 resolution spec. Suggested: Back-band overrides Fabric-band when Back-band is stricter. GREEN < AMBER < RED precedence with max() rule.

**C-006: FP-08 still marked `sketch`**

- **Raised in:** FP-08 (Multi-Plane Governance Policy, currently tagged `[sketch]`)
- **Issue:** FP-08 governs multi-plane consistency (Back's executor, Fabric's resolver, Bridge's guard). Without it, each plane enforces its own policies independently with no cross-plane reconciliation.
- **Evidence:** No POC or benchmark evidence.
- **Recommendation:** Promote FP-08 from `[sketch]` to `[draft]` with concrete enumerated safeguards. Define at minimum: (a) cross-plane policy conflict resolution, (b) authority precedence (which plane wins), (c) audit trail consistency across planes.

**C-007: All KD/ID/XD promotion conditions unmet**

- **Raised in:** BTC-006 (PromotionState: KD → ID → XD)
- **Issue:** The promotion pipeline from Known Design (KD) → Implementation Draft (ID) → Executable Draft (XD) has formal gates (BTC-006) but all normative sections are still KD. ID requires per-section test coverage; XD requires benchmark validation. Neither condition is met.
- **Evidence:** POC proves individual components but not integrated per-section.
- **Recommendation:** Select 3 highest-priority contracts for ID promotion (suggested: Contract D, Contract F, CC-1). Create dedicated test files. Run the promotion gate checklist from BTC-006.

---

### 🟡 Deferred

**C-008: CC contracts 3-8 missing Failure Semantics sections**

- **Raised in:** CC-3 through CC-8
- **Issue:** CC-0 through CC-2 have Failure Semantics sections. CC-3 through CC-8 do not. This creates asymmetric contract rigor — earlier contracts define error behavior; later contracts assume it.
- **Recommendation:** Add Failure Semantics to each CC contract following the CC-0 template: Transport failure, Encode failure, Decode failure, Semantic mismatch.

**C-009: M0-M12 milestones vs 5-layer model — no explicit handoff**

- **Raised in:** §Milestone order, Appendix B Q21
- **Issue:** Two milestone models coexist (M0-M12 linear and 5-layer component dependency). No explicit statement of which governs current implementation.
- **Status:** A note was added (J-8 resolution) stating the layer model supersedes for implementation planning. But no migration plan exists for renumbering M0-M12 to layer milestones.
- **Recommendation:** Create a milestone migration table mapping old M0-M12 to new layer-based milestones. Close after migration.

**C-010: PlanGraph dual-mode (optional vs. mandatory) unresolved**

- **Raised in:** §J-3, Contract L vs BTC-014
- **Issue:** Contract L describes PlanGraph as optional (for planning flow) while BTC-014 describes it as mandatory (for audit trail). Both cannot be correct simultaneously.
- **Evidence:** POC does not implement PlanGraph. Benchmark does not measure plan serialization.
- **Recommendation:** Resolve the mode: if BTC-014 requires mandatory PlanGraph for audit, update Contract L. If Contract L's optional mode stands, BTC-014 must accept optional PlanGraph with fallback audit via observation chain.

---

### ⚪ Speculative

**C-011: End-to-end discovery flow dual authority (LEGACY vs. target)**

- **Raised in:** End-To-End Discovery Flow section (LEGACY PATH warning banner)
- **Issue:** The Legacy Path (`llm_prompt` → `discover_capabilities` → `invoke_capability`) coexists with the Target Path (Back → Resolver → Manifest → CapabilityInvocation). The transition plan is undocumented.
- **Recommendation:** Define a phase-out schedule for the Legacy Path. Add a `discovery_mode` flag to the bridge context so Back can signal which path it's using.

**C-012: Executive Thesis top-K rejection vs. current-state prose**

- **Raised in:** §J-6
- **Issue:** Executive Thesis says "top-1, then offer alternatives" but current-state sections describe parallel resolution with no mention of top-1 selection.
- **Recommendation:** Either update Executive Thesis to match current design (parallel resolution) or update the resolver to implement top-1 with alternative offering.

---

### 🔴 Blocking (code-verified — added 2026-06-02)

**C-013: Participant name→identity resolution does not exist anywhere in the pipeline**

- **Raised in:** 4-plane decomposition analysis, code audit of `front.py`, `kernel/service.py`, `selfmodel/`, `sessionstate/`
- **Issue:** When a user says "Riley," no code resolves "Riley" → `actor_id`. The LLM interprets the name from prompt context. The grounding pipeline resolves temporal ("tomorrow"→date) and spatial references but NOT identity/name references. `SpaceGraphService` lists members with `display_name` but has no `resolve_name()` lookup method. `SessionState.persona._preferences["active_member"]` stores a display string, not a resolved identity.
- **Evidence:** Full code audit of the Front→Back dispatch path: `front_handler()` → `grounding.refresh_turn()` → `build_projection()` → `dispatch_task`. At no point is "Riley" matched to a `member_id`. The `GroundingProjection` carries `identity_ref` (session's own actor) and `group_refs` (space_id), not resolved participant refs from user text.
- **Recommendation:** Add `resolve_participant(name: str, space_id: str) → actor_id | None` to Fabric's resolver (NOT the Context Plane). The Context Plane delivers the raw `GroundingProjection` (space_id + temporal/spatial snapshot). Fabric's resolver consults `SpaceGraphService` members, matches `display_name`, and includes resolved participants in `CandidateUniverse.impact_set_candidates[]`. If ambiguous, Fabric returns `needs_disambiguation` with member candidates.
- **Rationale for Fabric ownership:** Participant resolution must consult constitution visibility rules (which members are visible to this actor?) and policy (can this actor schedule for this participant?). The Context Plane has no policy authority and should not make visibility decisions.

**C-014: `discover_capabilities` dual-authority — legacy execution path vs. target catalog-only path**

- **Raised in:** 4-plane decomposition analysis, End-To-End Discovery Flow section, POC benchmark
- **Issue:** `discover_capabilities` currently serves as BOTH (A) execution authority in the current baseline (Back discovers top-K → invokes by name) AND (B) catalog retrieval in the target design (cold discovery, first-contact, "is there any tool that could do X?"). The same tool name has two different authority levels depending on which code path calls it. There is no `discovery_mode` flag to distinguish them.
- **Evidence:** POC benchmark proves `resolve_situation` is the correct execution-authority path (100% exact lookup, 96-99.8% manifest recall, 0% authority FP rate). `discover_capabilities` returns a flat semantic-search catalog with no policy gates, no resource binding, no verification — it cannot be execution authority. But it is still needed for cold discovery, docs, and missing-capability suggestions.
- **Recommendation:** (a) Add `discovery_mode: execution | catalog | diagnostic` to Back's tool context. (b) When `discovery_mode=catalog`, `discover_capabilities` returns results with a `catalog_only: true` marker and `allowed_next_actions=[]` — the LLM cannot invoke from catalog results. (c) When `discovery_mode=execution`, Back MUST use `resolve_situation`, not `discover_capabilities`. (d) Define a phase-out schedule: once all Tier 2 paths use `resolve_situation`, deprecate `discover_capabilities` for execution and rename to `search_capability_catalog`.
- **Open question:** Should `discover_capabilities` remain a Back meta-tool or move to a Fabric-only diagnostic surface? If Back can call it, the LLM can misuse it for execution. If only Fabric can call it, Back loses cold-discovery capability.

---

## Code-Verified Architecture Findings — 2026-06-02

**Section mode:** code-audit findings that resolve 4-plane decomposition questions.

These findings are based on full code audits of `k1/concierge/actors/front.py`, `k1/kernel/service.py`, `k1/selfmodel/`, `k1/sessionstate/`, `k1/orchestrator/`, `k1/fabric/`, `bridge/`, and `architecture_diagrams/bridge/`.

---

### F-001: Bridge owns IFL — confirmed in code and architecture diagrams

**Source:** `bridge/README.md`, `bridge_architecture.mmd`, `bridge_architecture_v2.mmd`, `interkernel_fabric_layer.mmd`, `bridge/__init__.py`, `bridge/connector/`, `bridge/ifl/`

**Finding:** Bridge is the root peer of K0/K1. IFL is a subsystem (`bridge/ifl/`) inside Bridge. The hierarchy is:

```text
Bridge/                          ← root peer of K0/K1 (device-side Python package)
  ├── connector/                 ← security pipeline, credential vault, MCP process mgmt
  │   ├── gateway.py             ← ConnectorGateway (3-stage pipeline)
  │   ├── credential_vault.py    ← per-adapter secrets (AES256-GCM, never leave Bridge)
  │   ├── mcp_process_manager.py ← MCP child process supervision
  │   ├── token_verifier.py      ← K1 capability token validation
  │   └── adapter_verifier.py    ← FamilyOS CA adapter signature verification
  ├── ifl/                       ← IFL runtime tier (BRIDGE-OWNED)
  │   ├── adapters/              ← per-adapter MCP server packages
  │   │   └── google_calendar/   ← OAuth server, consent flow, MCP server
  │   ├── mcp_stdio.py           ← MCP stdio transport
  │   └── manifest/, protocol/, registry/, dispatch/, events/ (deferred)
  ├── ports/                     ← 5 protocol definitions (CMD, QRY, SSE, OBS, IFL)
  ├── core/                      ← signing, envelope_builder, events, health
  └── sync/                      ← LocalOutbox, drain_worker
```

**Security boundary:** Bridge IS the security boundary. K0/K1 cannot import Bridge internals directly (CI-enforced wall `bridge_not_imported_from_kernels`). Envelope signing (Ed25519), band enforcement, adapter verification, rate limiting, circuit breaking, and credential isolation all happen inside Bridge. MCP children receive secrets at init over stdio only — never via process env or argv.

**Implication for 4-plane model:** Bridge is NOT a 5th plane. It is the security boundary layer between Fabric (Plane 2) and IFL (Plane 1). Fabric dispatches through Bridge's `IConnectorGatewayPort`; Bridge routes through its IFL tier to concrete adapters. The 4-plane model remains correct: IFL (Plane 1) defines tool shapes; Bridge enforces security; Fabric (Plane 2) resolves and invokes.

---

### F-002: Orchestrator executes ALL tools through Fabric — single invocation path

**Source:** `k1/kernel/service.py` (S5, S6), `k1/orchestrator/adapters/fabric_gateway_adapter.py`, `k1/orchestrator/orchestration/step_runner.py`, `k1/orchestrator/orchestration/dag_executor.py`, `k1/orchestrator/orchestration/orchestrator_service.py`, `k1/fabric/fabric.py`

**Finding:** The Orchestrator has zero tools of its own (invariant ORCH-03). Every step executes through Fabric. The exact call chain is:

```text
OrchestratorService._receive_plan()
  → DAGExecutor.execute()
    → execute_wave()
      → _execute_step()
        → StepRunner.run()
          → IFabricGatewayPort.execute()    ← FabricGatewayAdapter
            → Fabric.execute()              ← Fabric container (fabric.py:1623)
              → CapabilityFabric.execute()  ← 9-step _execute_impl() (fabric.py:229)
                → Provider (Bridge/IFL)
```

**Planner is read-only:** The Planner uses `IFabricRetrievalPort` — a discovery port with only `discover_capabilities()` and `find_relevant_prompts()`. It has NO `execute()` method. Planner literally cannot execute a capability (PLAN-06 enforced at interface level).

**Concierge also calls Fabric:** Back's `invoke_capability` → `FabricDispatchAdapter` → `CapabilityFabric.execute()`. Both Tier 2 (Back) and Tier 3 (Orchestrator) go through the same Fabric execution spine.

**Implication for 4-plane model:** Fabric (Plane 2) is the single execution authority for ALL tiers. No tool call bypasses Fabric. Back (Plane 3) invokes through Fabric; Orchestrator (Tier 3, outside 4-plane model) also invokes through Fabric. The 4-plane model correctly places invocation in Fabric.

---

### F-003: Participant name→identity resolution is a design gap — Context Plane vs. Fabric boundary

**Source:** `k1/concierge/actors/front.py`, `k1/kernel/service.py`, `k1/selfmodel/service/space_graph.py`, `k1/grounding/adapters/selfmodel_identity_adapter.py`, `k1/sessionstate/sections/persona.py`, `k1/sessionstate/sections/meta.py`

**Finding:** The grounding pipeline resolves temporal and spatial references deterministically. It does NOT resolve participant names from user text. The current flow:

```text
User: "Can Riley pick up the kids tomorrow?"

1. grounding.refresh_turn() → GroundingEnvelope
   - temporal: "tomorrow" → 2026-06-03 ✅ RESOLVED
   - spatial: device_location, place_refs ✅ RESOLVED
   - identity_ref: "actor:session123" ← session's OWN actor, NOT "Riley"
   - group_refs: ("space:family123",) ← space context

2. self_model.render_capsule() → GroundingCapsule
   - SituationFrame = S(actor) ∩ F ∩ C
   - Contains: actor's selfmodel, space members list, constitution rules
   - Does NOT contain: "Riley → member_id" mapping

3. SpaceGraphService.get_view(actor_id)
   - Returns: members with display_name, role, age_band
   - Has NO resolve_name(display_name) → member_id method

4. SessionState.persona._preferences["active_member"]
   - Stores: "Riley" as a display string
   - Is NOT a resolved identity reference

5. The LLM interprets "Riley" from the prompt context
   - NO deterministic resolution occurs
```

**Design decision:** Participant resolution belongs to Fabric (Plane 2), not the Context Plane (Plane 4). Rationale:

- Participant resolution requires consulting constitution visibility rules — which members can this actor see?
- It requires policy checks — can this actor schedule for this participant?
- The Context Plane has no policy authority and should not make visibility decisions.
- The Context Plane's job is snapshot DELIVERY (temporal, spatial, session identity, space refs). Fabric's job is snapshot CONSUMPTION (resolving participants, resources, capabilities from the snapshot).

**Implementation path:** Fabric's resolver, given `GroundingProjection.space_id`, calls `SpaceGraphService.get_view(actor_id)` → iterates members → matches `display_name` against user text references → includes resolved participants in `CandidateUniverse.impact_set_candidates[]`. If ambiguous (two "Riley"s in a space), Fabric returns `needs_disambiguation` with member candidates.

---

### F-004: Constitution ownership split confirmed — IFL (format/authoring), Fabric (interpretation/enforcement)

**Source:** Constitution Tooling section, Principle 6, `bridge/ifl/adapters/`, `k1/fabric/fabric.py`

**Finding:** The user confirmed the split: IFL owns constitution artifact format and authoring (it ships with the connector). Fabric owns constitution interpretation at runtime (enforcing prerequisite reads, conflict checks, HIL gates, verification requirements). This matches Principle 6: "Constitution Ships With The Connector, Not The Prompt." The constitution is stored in `GlobalProjectionStore.connector_constitutions` (POC-proven, Appendix B Q1) and disclosed progressively via CC-10 phases. Fabric's resolver loads it by `connector_id` at resolution time.
