# Whiteboard: K1 Temporal and Spatial Kernel Modules

Date: 2026-05-18
Status: initial draft / architecture whiteboard
Branch context: feature/back-execution-profiles

## Thesis

K1 needs first-class `k1.temporal` and `k1.spatial` kernel modules.

Today, time and place exist mostly as prompt hints, persona preferences, partial SessionState metadata, and LLM-inferred strings. That is not strong enough for FamilyOS. A family assistant has to know who is asking, what day it is, what "tomorrow" means, which household member is active, what device or surface is being used, which places matter, and what privacy rules apply before it plans, calls tools, spawns agents, or writes memory.

The correct direction is:

```text
Kernel temporal/spatial services
  -> typed SessionState sections
  -> canonical grounding envelope
  -> Concierge Front / Back / Planner / Fabric / agents / tools
  -> policy-filtered prompt and tool context
```

Not:

```text
LLM prompt text
  -> maybe says current time
  -> maybe resolves tomorrow
  -> maybe calls date_calc
  -> maybe passes a raw location string
```

The system should treat time and place as kernel-owned runtime facts, with confidence, freshness, provenance, privacy policy, and typed projections for every consumer.

## Executive Summary

The audit found that temporal and spatial grounding are inconsistent across the live K1 stack.

| Surface | Temporal status | Spatial status | Main problem |
| --- | --- | --- | --- |
| Concierge Front | Partial | Weak / identity-like | Front gets a NOW block and temporal_context, but location is hardcoded and spatial mostly means family roster. |
| Concierge Back | Missing | Missing | Back prompt has no current time, date windows, timezone, semantic place, or member-place grounding. |
| Planner / Orchestrator | Conditional | Missing | Planner can receive temporal constraints, but nothing guarantees them. Spatial is not typed. |
| Fabric capabilities | Contract-dependent | Contract-dependent / mostly absent | ContextBuilder only injects sections declared by contracts. Current contracts do not default temporal/spatial. |
| Spawned agents | Missing by default | Missing by default | Agent contracts omit temporal/spatial in default context. |
| Kernel / Session lifecycle | POC utility only | No module | Temporal anchor lives as POC code and control metadata. No spatial module exists. |
| SessionState UI | Can display sections if present | No real section yet | The UI can inspect actual stored data now, but temporal/spatial must become real sections to be useful. |

The near-term design goal is a canonical, policy-filtered `GroundingEnvelope` assembled by kernel services and provided to every AI surface.

## Definitions

### Temporal Context

Temporal context is the authoritative answer to:

- What is the current instant?
- What is the local date and time for the active member/device?
- What timezone applies?
- What does "today", "tomorrow", "this weekend", "next Monday", or "after school" mean right now?
- What time windows are safe for tools to use?
- How fresh is this information?
- Which source produced it?

Temporal context is not just a rendered string in a prompt. It is a typed runtime object that can be consumed by deterministic tools, LLM prompts, planners, memory writers, and spawned agents.

### Spatial Context

Spatial context is the authoritative answer to:

- Where is the active person or device, if known and allowed?
- What semantic place is relevant: home, work, school, car, store, unknown?
- Which household places are registered?
- Which members are co-present, if known and allowed?
- Which device or surface is being used?
- Which geofence or place confidence applies?
- What location data is private, approximate, stale, or unavailable?

Spatial context is not only a household roster. The existing prompt concept of `[space]` mostly means social/relationship space. The new `k1.spatial` module should own physical, semantic, and permissioned place context.

### Grounding Envelope

A Grounding Envelope is the kernel-produced object that binds identity, time, place, freshness, confidence, and privacy policy into a single projection for AI consumers.

The envelope should be scoped. Front, Back, Planner, Fabric tools, and spawned agents should not all receive the same raw payload.

```text
GroundingEnvelope
  identity_ref
  temporal
  spatial
  household_refs
  device_surface
  policy_scope
  freshness
  provenance
  redactions
```

## Current Code Grounding

This whiteboard is based on read-only audits of the current repository.

### Front Prompt Grounding Today

Relevant files:

- `k1/concierge/actors/front.py`
- `k1/concierge/prompt/builder.py`
- `k1/concierge/prompt/sections.py`
- `k1/concierge/prompt/scenario_templates.py`
- `k1/concierge/fsm/controller.py`
- `k1/sessionstate/sections/control.py`
- `k1/sessionstate/sections/temporal_context.py`
- `k1/selfmodel/contracts/capsule.py`

Current behavior:

1. The FSM computes a temporal anchor per user turn.
2. The anchor is written into `ControlSection` via `control.set_temporal_anchor(anchor.to_dict())`.
3. `DynamicPromptBuilder` maps virtual `temporal_context` to real SessionState section `control`.
4. The Front prompt gets a high-priority `== NOW ==` block.
5. The Front prompt also gets a rendered `## temporal_context` block.
6. If no temporal anchor is present, prompt rendering lazily recomputes one.
7. Active member and family context come through two paths:
   - legacy `persona._preferences["family"]`
   - typed SelfModel `GroundingCapsule`

Important details:

- `SS_READ_CONFIGS` includes `temporal_context` for active prompt modes.
- `SECTION_SOURCE_MAP` maps `temporal_context` to `control`.
- `_render_temporal_context_full()` renders current time, day, time of day, weekend status, timezone, and location.
- `_build_now_block()` promotes the most compact time signal near the top of the prompt.
- `_build_active_member_block()` promotes SelfModel `self_block` and `space_graph_block` when available.

Known gaps:

| Gap | Detail | Impact |
| --- | --- | --- |
| Hardcoded location | The temporal renderer currently emits `Location: Denton, Texas`. | Wrong for any other family or device. |
| Temporal hidden in control | `temporal_context` is virtual and stored under `control`. | Fabric and agents do not naturally discover it as a first-class context section. |
| Lazy recomputation | Prompt rendering can recompute time if missing. | Hides wiring failures and creates inconsistent anchors across consumers. |
| Spatial overloaded | `space_graph_block` is household/social context, not physical place. | The model may know who people are but not where anything is. |
| Legacy/capsule divergence | Persona family dict and SelfModel capsule can disagree. | Prompt context can drift. |
| Turn-time freshness only | Temporal anchor is written per turn. | Long-running Back or Planner work may use stale time. |

### Back Task Grounding Today

Relevant files:

- `k1/concierge/actors/back.py`
- `k1/concierge/prompt/back_prompt.py`
- `k1/concierge/task/dispatch.py`
- `k1/concierge/tools/schemas_back.py`
- `k1/concierge/tools/schemas_front.py`

Current Back input:

| Field | Source | Notes |
| --- | --- | --- |
| `task_id` | `TaskDispatch` | System-generated task identifier. |
| `intents` | Front dispatch | Action and params. May contain unresolved relative dates. |
| `tier` | Front/FSM | LOW, MEDIUM, HIGH. Drives budget and routing. |
| `budget_hint` | Front/FSM | ReAct max tool budget. |
| `reference_context` | Front | May contain resolved referents, but no guarantee of temporal normalization. |
| `safety_band` | Control section | Extracted by Back snapshot code. |
| `context_snapshot` | Optional dispatch field | Not consistently used for temporal/spatial. |
| `execution_profiles` | M4 profiles | Execution hints, not time/place grounding. |

Current Back SessionState snapshot reads:

| Section | Back usage |
| --- | --- |
| `beliefs_active` | rendered belief summary |
| `scoreboard` | referents |
| `task_state` | task summary |
| `task_artifacts` | artifact summary |
| `control` | safety band only |
| `history_active` | recent history |
| `persona` | payment/dietary/accessibility prefs |

Back does not currently extract:

- current time
- current local date
- timezone
- today/tomorrow windows
- resolved relative expressions
- semantic place
- home/work/school place registry
- active device surface
- member presence
- precise or approximate location

Back prompt gap:

`build_back_prompt()` receives summaries and safety fields, but no `current_time`, `today`, `timezone`, `location`, `spatial_context`, or `active_member_context` parameter.

Why this matters:

When the user asks, "what does Jordan have tomorrow?", and Front dispatches a task without converting "tomorrow" to an ISO date, Back has to reason from an ungrounded phrase. It may call `date_calc`, discover a capability, spend tool budget, and still fail if WASM runtime is missing or if the LLM supplied the wrong base date.

Observed runtime lesson:

- `tool.execute.date_calc` exists.
- It can be discovered and invoked.
- It failed in observed logs without `wasm_runtime`.
- But even if fixed, it should not be required for basic `today` and `tomorrow` resolution.

Back should receive resolved temporal context before it starts the ReAct loop.

### Planner and Orchestrator Grounding Today

Relevant files:

- `k1/planner/stages/sketch_service.py`
- `k1/planner/stages/expand_service.py`
- `k1/planner/services/tool_call_router.py`
- `k1/planner/adapters/session_state_adapter.py`
- `k1/planner/adapters/null_state_read_adapter.py`
- `k1/orchestrator/types.py`
- `k1/orchestrator/orchestration/orchestrator_service.py`

Current behavior:

1. Planner stages can see temporal data if it appears in `constraints["temporal"]`.
2. Planner can call `query_session_context` to read SessionState sections.
3. Orchestrator builds `PlanRequest` from intent, trace ID, context snapshot, constraints, and metadata.
4. `TaskEnvelope` and `PlanRequest` do not type temporal/spatial as first-class fields.
5. `NullStateReadAdapter` can return empty snapshots indefinitely.

Gaps:

| Gap | Impact |
| --- | --- |
| Temporal is conditional | Planner only gets it if upstream remembered to include it. |
| Spatial is absent | Planner cannot reason about travel, place constraints, co-presence, pickup/dropoff, or location-specific tasks in a typed way. |
| Context query is voluntary | LLM has to decide to call `query_session_context`. Critical grounding should not depend on voluntary tool use. |
| No typed envelope | PlanRequest cannot declare "this plan was made under temporal anchor X and spatial anchor Y". |

Planner should receive typed temporal/spatial constraints on every plan request, even if the LLM never asks for context.

### Fabric and Agent Grounding Today

Relevant files:

- `k1/fabric/core/context_builder.py`
- `k1/fabric/providers/agent_provider.py`
- `k1/concierge/tools/implementations.py`
- `k1/contracts/tools/date_calc.yaml`
- `k1/contracts/tools/build_agent.yaml`
- `k1/sessionstate/sections/beliefs_active.py`

Current Fabric behavior:

1. `ContextBuilder.build()` reads sections declared by the tool or agent contract.
2. It fetches required and optional context sections from `ISessionStateReader`.
3. It injects request params.
4. It resolves prompt template if configured.
5. It applies budget.
6. It merges `context_override`.
7. It returns `ExecutionContext`.

Key issue:

Fabric does not automatically inject time/place. It only injects what contracts ask for.

Specific examples:

- `date_calc.yaml` declares no `required_context` or `optional_context` for temporal anchor.
- `build_agent.yaml` default context omits temporal/spatial.
- Spawned agents receive context through `ContextBuilder`, so they inherit the same omission.
- `MentionedLocation` exists in `beliefs_active`, but that is a mention from language, not an authoritative place signal.

Gaps:

| Gap | Impact |
| --- | --- |
| `date_calc` has no `today` anchor | It depends on LLM-supplied dates. |
| Spawned agents lack default temporal context | Agents can plan with stale or imagined time. |
| Spawned agents lack default spatial context | Agents cannot reason about place unless contracts manually include it. |
| Mentioned location is not ground truth | "school" in a conversation is not the same as current device/user location. |
| No invocation timestamp in context | Tool and agent execution cannot prove which instant grounded the decision. |

### Kernel and Session Lifecycle Today

Relevant files:

- `k1/kernel/service.py`
- `k1/concierge/factory.py`
- `k1/concierge/session.py`
- `k1/sessionstate/sections/temporal_context.py`
- `k1/sessionstate/sections/control.py`
- `k1/sessionstate/sections/persona.py`
- `k1/sessionstate/sections/__init__.py`

Current state:

- `k1/sessionstate/sections/temporal_context.py` contains `TemporalAnchor` and `compute_temporal_anchor(tz_name)`.
- The file is POC-grade by its own architectural notes.
- The live temporal anchor is stored under `ControlSection`.
- No `k1.temporal` package exists.
- No `k1.spatial` package exists.
- No real spatial SessionState section exists.
- The best kernel integration pattern to reuse is the SelfModel/HIL pattern:
  - Tier 1 kernel-lifetime bundle.
  - Tier 2 per-session handle.
  - Install handle before Concierge starts.
  - Uninstall during session teardown.

## Failure Modes We Need To Eliminate

### Failure Mode 1: Relative Date Escapes Front

```text
User: What does Jordan have tomorrow?
Front: dispatches task with params.date = "tomorrow"
Back: has no current date
Back: discovers date_calc
Back: invokes date_calc with LLM-generated base date
date_calc: may fail or compute from wrong anchor
Calendar: receives bad or unresolved date
User: gets wrong answer or no answer
```

Correct behavior:

```text
User: What does Jordan have tomorrow?
k1.temporal: resolves tomorrow -> 2026-05-19 local date window
Front: dispatches task with resolved temporal refs
Back: receives same temporal anchor and resolved window
Calendar tool: receives ISO start/end
User: gets deterministic answer
```

### Failure Mode 2: Back Prompt Has No Now

Back is the actor doing most real work. It should not be temporally blind.

The Back prompt should know:

- current local time
- current local date
- timezone
- today window
- tomorrow window
- week start/end
- resolved relative expressions from this task
- freshness of the anchor

Without that, the actor burns tool calls and may hallucinate dates.

### Failure Mode 3: Planner Makes A Plan Without Place

Example:

```text
User: Can you figure out when we can pick up groceries after soccer?
```

The plan needs:

- current family calendar
- soccer location
- grocery store location
- travel-time assumptions
- who is driving
- who is with whom
- constraints on child pickup/dropoff
- local time window

Current Planner has no mandatory spatial envelope. It may produce a plan that is logically coherent but physically impossible.

### Failure Mode 4: Agent Is Spawned Without Ambient Grounding

Example:

```text
Spawn agent: plan Saturday birthday errands.
```

The spawned agent needs:

- now/today
- target date
- family location
- store/place candidates
- member constraints
- child privacy constraints
- available travel windows

Today, agent contracts omit temporal/spatial by default. The agent can become an ungrounded LLM worker.

### Failure Mode 5: Raw Location Leaks Into Prompt

If spatial data is added carelessly, prompts may receive raw GPS coordinates or sensitive child location.

Correct behavior:

- Front prompt usually gets semantic place: "at home", "near school", "unknown".
- Back tools may get precise location only when required and policy allows.
- Planner may get approximate travel context but not unnecessary raw coordinates.
- Spawned agents get a scoped lease, not unrestricted location state.

## Design Goals

1. Make time and place kernel-owned runtime facts.
2. Provide every AI surface with consistent temporal/spatial grounding.
3. Resolve simple temporal expressions before LLM tool execution.
4. Preserve privacy by default, especially for child/member location.
5. Separate semantic place from raw coordinates.
6. Make freshness and provenance visible.
7. Keep SessionState as the live projection, not the computation engine.
8. Keep deterministic tools deterministic by passing typed inputs.
9. Keep prompts concise, but never omit critical grounding.
10. Ensure Back, Planner, Fabric, and agents get at least the same authoritative anchor as Front.

## Non-Goals

1. Do not make LLMs the source of truth for time or location.
2. Do not store raw GPS in Persona.
3. Do not make every prompt receive every spatial detail.
4. Do not replace SelfModel. Spatial should integrate with SelfModel, not duplicate identity.
5. Do not remove `date_calc`. Keep it for non-trivial date arithmetic, but stop using it for basic now/today/tomorrow grounding.
6. Do not make location mandatory. Unknown location is a valid state.
7. Do not block the whole assistant when spatial signals are unavailable.
8. Do not give spawned agents unlimited family context.

## Core Invariants

1. Every turn has exactly one authoritative temporal anchor.
2. Every task dispatch carries the temporal anchor ID or envelope version used to create it.
3. Every Back execution sees the same or newer temporal anchor as the Front dispatch.
4. Every Planner request receives typed temporal constraints.
5. Spatial context is permissioned before prompt/tool exposure.
6. Raw coordinates are never sent to an LLM unless a policy explicitly allows it for that consumer and task.
7. Semantic place can be exposed more broadly than raw coordinates.
8. All temporal/spatial projections include freshness and provenance.
9. Stale anchors are marked stale, not silently reused.
10. Unknown is better than invented.
11. `DeviceContextSnapshot` is one shared typed object, not separate temporal and spatial variants.
12. Prompt renderers consume `GroundingProjection`, not raw temporal/spatial section payloads.
13. Regular expressions are not the core resolver contract for time or place.

## Production V0 Bar

V0 does not mean a demo slice. For these modules, V0 means the first production contract that is safe to deploy broadly. If the kernel cannot expose time and place correctly, the feature should stay off rather than ship as prompt-only grounding.

The bar is:

1. The installed device is the primary observer.
2. The kernel is the authority that normalizes, timestamps, validates, and stores the observation.
3. Policy controls what each AI surface can see.
4. Typed contracts exist from day one, even when a specific deployment lacks a sensor.
5. Unknown, hidden, unavailable, stale, and degraded are explicit states.
6. Front, Back, Planner, Fabric, spawned agents, and memory writeback all consume the same envelope family.
7. Raw device data never becomes prompt text by accident.
8. The design must hold for one household and for a billion households.

Production V0 must include the installed-device context path:

```text
Installed device / app / browser
  |
  |-- device_id
  |-- installation_id
  |-- surface_kind
  |-- observed_at_utc
  |-- timezone
  |-- locale
  |-- location_permission
  |-- optional location fix
  |-- optional semantic place hint
  v
DeviceContextSnapshot
  |
  +-- k1.temporal normalizes time, timezone, clock skew, windows
  |
  +-- k1.spatial normalizes surface, place, permission, precision
  |
  v
GroundingEnvelope
  |
  +-- Front projection
  +-- Back projection
  +-- Planner constraints
  +-- Fabric context sections
  +-- Agent grounding lease
```

Production V0 may run with missing sensors, but it must not have missing interfaces. A desktop install with no GPS should still report `location_permission=unavailable`, `precision=hidden`, and `semantic_place=unknown`. A mobile install with GPS permission can provide a raw fix, but raw coordinates are redacted unless a policy-approved deterministic tool contract asks for them.

`DeviceContextSnapshot` is a single shared dataclass for the installed-device observation. The producer/reader Protocol belongs at the kernel boundary, but the pure data type should be shared by grounding so temporal and spatial cannot drift into incompatible device-context shapes.

This is the distinction:

| Bad V0 | Production V0 |
| --- | --- |
| prompt string says current time | typed temporal section + prompt projection |
| location hardcoded or omitted | typed spatial section with unknown/hidden states |
| Back guesses tomorrow | Back receives ISO windows from temporal anchor |
| agents get whatever context happens to be there | agents get scoped grounding leases |
| raw GPS can leak into prompts | raw GPS is contract-gated and redacted by default |
| Fabric receives optional ad hoc metadata | Fabric receives declared context sections and baseline invocation grounding |

## Proposed Architecture

```text
k1.kernel
  starts TemporalBundle, SpatialBundle, and GroundingBundle
  creates per-session TemporalHandle, SpatialHandle, and GroundingHandle
  installs handles into SessionState before Concierge starts

k1.temporal
  owns current instant, timezone, local date windows, expression resolution
  writes TemporalSection projection
  exposes ITemporalPort

k1.spatial
  owns device/place/member presence projection
  writes SpatialSection projection
  exposes ISpatialPort

k1.grounding
  builds policy-filtered GroundingEnvelope
  owns DeviceContextSnapshot dataclass and consumer projections
  provides per-consumer projections

Concierge Front
  renders compact temporal/spatial prompt blocks
  resolves dispatch references using TemporalHandle/SpatialHandle

Concierge Back
  receives execution grounding and resolved windows
  avoids unnecessary date_calc calls

Planner/Orchestrator
  receive typed temporal/spatial constraints

Fabric
  ContextBuilder injects temporal/spatial sections when contract declares them
  can stamp baseline invocation anchor for all calls

Spawned agents
  receive scoped ambient intelligence lease
```

## Existing Module Pattern To Follow

This design should follow the module and port/adapter style already used by Planner, Fabric, Concierge, HIL, and SelfModel.

The important repo conventions are:

1. Factories are composition roots.
2. Services receive dependencies by constructor injection.
3. Business logic does not import production adapters.
4. Ports are `typing.Protocol` surfaces, usually `@runtime_checkable` when factories validate them.
5. Adapters wrap external subsystems and translate shapes.
6. Top-level agents/facades own lifecycle, not dependency creation.
7. Kernel owns shared Tier 1 startup and per-session Tier 2 binding.
8. Optional overlays must degrade cleanly and not abort session creation unless the module is required.
9. Session-scoped services that publish UI-visible events must bind to the session bus, not the kernel bus.
10. Per-session handles must be installed before `ConciergeRuntime.start()` so the mailbox consumer cannot race the first turn.

### Pattern: Planner

Planner shows the pure factory and layer discipline pattern.

```text
k1.planner
  config.py
  types.py
  events.py
  ports/
    llm_port.py
    state_read_port.py
    fabric_retrieval_port.py
    bridge_port.py
    delta_emit_port.py
    event_port.py
    mailbox_port.py
  adapters/
    llm_gateway_adapter.py
    session_state_adapter.py
    fabric_retrieval_adapter.py
    bridge_adapter.py
    delta_bus_adapter.py
    event_bus_adapter.py
    mailbox_adapter.py
  services/
    tool_call_router.py
  stages/
    sketch_service.py
    expand_service.py
    validate_service.py
    commit_service.py
  pipeline_controller.py
  planner_agent.py
  factory.py
```

Planner wiring shape:

```text
PlannerFactory.create_production(... explicit ports ...)
  |
  |-- validate config
  |-- validate all ports satisfy Protocols
  |-- reject duplicate port identities
  |
  +--> ToolCallRouter
  |      |-- IFabricRetrievalPort
  |      |-- IStateReadPort
  |      +-- IPlannerWritePort
  |
  +--> SketchService     -- gets LLM + ToolCallRouter + HIL
  +--> ExpandService     -- gets LLM + ToolCallRouter
  +--> ValidateService   -- gets LLM + Fabric + HIL
  +--> CommitService     -- gets Bridge + Delta + Event, no LLM
  |
  +--> PipelineController -- gets stages + delta/event/HIL/config
  |
  +--> PlannerAgent       -- gets mailbox + pipeline + event/config
         |
         +-- caller starts with asyncio.create_task(agent.start())
```

Design lessons for `k1.temporal` and `k1.spatial`:

- Use a single factory as the only cross-layer importer.
- Keep resolvers as leaf services.
- Keep section write/read adapters outside core services.
- Make top-level services/handles receive already-wired components.
- Keep LLM calls out of deterministic temporal/spatial core logic.
- If a resolver ever needs LLM help, put it behind an optional port and make deterministic behavior the baseline.

### Pattern: Fabric

Fabric shows the larger composition-root and contract-context pattern.

```text
FabricFactory.create_with_ports(
    state_reader,
    event_port,
    bridge,
    model_gateway,
    prompt_system,
    delta_bus,
    ...
)
  |
  +--> ContractValidator
  +--> CapabilityRegistry
  +--> RetrievalEngine
  +--> ContextBuilder(state_reader, prompt_system)
  +--> ProviderFactory(**port_deps)
  +--> Resolver
  +--> OutputValidationPipeline
  +--> HealthChecker
  +--> CapabilityFabric facade
```

Fabric context path:

```text
CapabilityContract.required_context / optional_context
  |
  v
ContextBuilder.build(...)
  |
  |-- read requested sections via ISessionStateReader
  |-- inject request params
  |-- resolve prompt template through IPromptSystemPort
  |-- apply token budget
  v
ExecutionContext(session_sections, params, prompt, trace_id)
```

Design lessons:

- Temporal/spatial must become real section names that contracts can request.
- `ContextBuilder` should not know private module internals.
- Tool and agent contracts should declare context precision.
- Universal invocation metadata can go through `context_override`, but authoritative facts should live in sections.

### Pattern: SelfModel

SelfModel shows the exact kernel bundle/handle pattern temporal/spatial should copy.

```text
Tier 1: Kernel startup
  KernelService._startup_tier1()
    |
    +-- build_self_model_bundle(...)
          |
          +-- projection store
          +-- constitution service
          +-- self model service
          +-- space graph service
          +-- policy evaluator
          +-- capsule builder
          +-- citation builder
          +-- health()
          +-- shutdown()

Tier 2: Per-session creation
  KernelService._create_session_tier2()
    |
    +-- build_self_model_handle(bundle, session_id, actor_id, device_id, ...)
          |
          +-- ConciergePolicyGate
          +-- GroundingCapsuleRenderer
          +-- install_into_session(front/back dispatchers and ToolContexts)
          +-- uninstall_from_session()

Pre-start install
  session_self_model.install_into_session(...)
  session_concierge.set_self_model(session_self_model)
  await session_concierge.start()
```

Design lessons:

- Use shared bundles for kernel-lifetime services and stores.
- Use per-session handles for session ID, actor ID, device ID, policy, and prompt projections.
- Provide `install_into_session()` and `uninstall_from_session()`.
- Attach handles to `ConciergeRuntime` before `start()`.
- Keep business logic in service modules; kernel files only wire.

### Pattern: HIL

HIL shows one service satisfying a kernel-level port structurally.

```text
IHILPort Protocol
  |
  +-- ask_clarification(...)
  +-- request_approval(...)
  +-- needs_human(...)
  +-- request_override(...)
  +-- gate_capability(...)
  +-- reset_round_budget(...)
  +-- shutdown()

HumanInTheLoopService
  |
  +-- IEventPort.publish/subscribe
  +-- ledger adapter
  +-- safety policy
  +-- pending futures by request id
  +-- shutdown cancels pending futures and unsubscribes
```

Design lessons:

- Define kernel-visible temporal/spatial ports with pure dataclass request/response types.
- Keep bus publishing behind an event port.
- If temporal/spatial needs user confirmation, call `IHILPort`; do not invent a new approval path.

## ASCII System Diagrams

### Diagram 1: Current Scattered Grounding

```text
                        +----------------------+
                        |  Persona preferences |
                        |  timezone/family     |
                        +----------+-----------+
                                   |
                                   v
+------------+      +--------------+--------------+      +-------------------+
| User turn  | ---> | FSM writes control metadata | ---> | Front prompt      |
+------------+      | temporal_anchor             |      | == NOW ==         |
                    +--------------+--------------+      | temporal_context  |
                                   |                     +---------+---------+
                                   |                               |
                                   |                               v
                                   |                     +-------------------+
                                   |                     | Front dispatch    |
                                   |                     | maybe resolves    |
                                   |                     | "tomorrow"       |
                                   |                     +---------+---------+
                                   |                               |
                                   v                               v
                       +----------------------+          +-------------------+
                       | Back reads control   |          | Planner/Fabric    |
                       | safety band only     |          | conditional ctx   |
                       +----------+-----------+          +-------------------+
                                  |
                                  v
                       +----------------------+
                       | Back prompt has no   |
                       | now/place window     |
                       +----------------------+
```

Main defect: Front gets partial prompt grounding, while Back, Planner, Fabric, and agents do not receive one canonical typed source.

### Diagram 2: Proposed Kernel-Owned Grounding

```text
                   +-----------------------+
                   |      KernelService    |
                   +-----------+-----------+
                               |
             +-----------------+------------------+
             |                                    |
             v                                    v
   +-------------------+                +-------------------+
   |  TemporalBundle   |                |   SpatialBundle   |
   |  shared services  |                |   shared services |
   +---------+---------+                +---------+---------+
             |                                    |
             v                                    v
   +-------------------+                +-------------------+
   | TemporalHandle    |                | SpatialHandle     |
   | per session       |                | per session       |
   +---------+---------+                +---------+---------+
             |                                    |
             +-----------------+------------------+
                               |
                               v
                   +-----------------------+
                   |  GroundingEnvelope    |
                   |  typed + policy       |
                   +-----------+-----------+
                               |
       +-----------+-----------+------------+------------+------------+
       |           |                        |            |            |
       v           v                        v            v            v
   +-------+   +--------+              +---------+   +--------+   +--------+
   | Front |   | Back   |              | Planner |   | Fabric |   | Agent  |
   | prompt|   | tools  |              | stages  |   | ctx    |   | lease  |
   +-------+   +--------+              +---------+   +--------+   +--------+
```

Main property: every consumer receives a projection from the same source envelope, with precision and privacy adjusted per consumer.

### Diagram 3: Tier 1 Startup Slots

The current kernel startup labels Bridge as S4 even though it runs before shared Fabric. The temporal/spatial insertion should respect that existing code reality.

```text
S1   Bus + Router + AsyncBusBridge
 |
 v
S2   ModelHub
 |
 v
S2.5 HumanInTheLoopService
 |
 v
S2.6 SelfModelServiceBundle
 |
 v
S2.7 TemporalServiceBundle          new
 |
 v
S4   Bridge                         existing label, runs before shared Fabric
 |
 v
S2.8 SpatialServiceBundle           new, may use Bridge/place registry later
 |
 v
pre-S3 SessionRoutingStateReader
 |
 v
S3   Shared Fabric
 |
 v
S5+  Orchestrator / Planner / remaining shared services
```

Why this ordering:

- HIL is available if temporal/spatial need confirmation.
- SelfModel is available for actor/family policy.
- Temporal can start without Bridge.
- Spatial can optionally use Bridge/K0-backed place registry after Bridge exists.
- Shared Fabric starts after canonical section names and context policy are known.

If SpatialBundle starts before Bridge in production V0, it must still expose the full spatial contract. Bridge-backed registry hydration can be unavailable, but the section must explicitly represent that state instead of shrinking the feature to prompt-only place text.

### Diagram 4: Tier 2 Per-Session Install Slots

```text
P1     Session bus + router + Front/Back mailboxes
 |
 v
P1.5   Session-bus-bound HIL service
 |
 v
P2     SessionStateManager
 |
 v
P3     Per-session Fabric
 |
 v
P3.5   SelfModelHandle
 |
 v
P3.6   TemporalHandle                 new
        - binds session_id
        - writes TemporalSection
        - can mirror control.temporal_anchor
 |
 v
P3.7   SpatialHandle                  new
        - binds session_id / actor / device
        - writes SpatialSection
        - prepares privacy projection
 |
 v
P4     ConciergeFactory.create_with_ports(...)
 |
 v
pre-start installs
        self_model.install_into_session(...)
        temporal.install_into_session(...)
        spatial.install_into_session(...)
        concierge.set_self_model(...)
        concierge.set_temporal(...)
        concierge.set_spatial(...)
 |
 v
P6     await concierge.start()
```

Critical invariant: handle setters must run before `ConciergeRuntime.start()` for the same reason `set_self_model()` does today.

### Diagram 5: Port / Adapter Boundary For Temporal

```text
                         +-------------------+
                         | TemporalFactory   |
                         +---------+---------+
                                   |
             +---------------------+-----------------------+
             |                     |                       |
             v                     v                       v
   +-------------------+  +-------------------+   +-------------------+
   | IClockPort        |  | ITimezonePort     |   | IEventPort        |
   | SystemClockAdapter|  | Device/Persona    |   | Bus adapter       |
   +---------+---------+  +---------+---------+   +---------+---------+
             |                      |                       |
             +----------------------+-----------------------+
                                    |
                                    v
                         +-------------------+
                         | TemporalService   |
                         | pure resolver     |
                         +---------+---------+
                                   |
                +------------------+------------------+
                |                                     |
                v                                     v
      +--------------------+              +----------------------+
      | TemporalHandle     |              | TemporalSection      |
      | per session        |------------->| SessionState HOT     |
      +--------------------+              +----------------------+
```

### Diagram 6: Port / Adapter Boundary For Spatial

```text
                         +-------------------+
                         | SpatialFactory    |
                         +---------+---------+
                                   |
       +---------------------------+-----------------------------+
       |                           |                             |
       v                           v                             v
+---------------+        +-------------------+        +-------------------+
| IDevicePlace  |        | IPlaceRegistry    |        | ISpatialPolicy    |
| Adapter       |        | Bridge/Local      |        | SelfModel policy  |
+-------+-------+        +---------+---------+        +---------+---------+
        |                          |                            |
        +--------------------------+----------------------------+
                                   |
                                   v
                         +-------------------+
                         | SpatialService    |
                         | projection engine |
                         +---------+---------+
                                   |
                +------------------+------------------+
                |                                     |
                v                                     v
      +--------------------+              +----------------------+
      | SpatialHandle      |              | SpatialSection       |
      | per session        |------------->| SessionState HOT     |
      +--------------------+              +----------------------+
```

### Diagram 7: Runtime Turn Flow

```text
User input
  |
  v
Concierge FSM turn start
  |
  |-- TemporalHandle.refresh_turn(user_text)
  |       |-- compute anchor
  |       |-- compute standard windows
  |       +-- resolve relative expressions
  |
  |-- SpatialHandle.refresh_turn(user_text)
  |       |-- classify device surface
  |       |-- resolve semantic place
  |       +-- apply privacy projection
  |
  +-- GroundingEnvelopeBuilder.create(turn_id, trace_id)
          |
          +-- write temporal/spatial SessionState projections
          +-- store envelope id in control/turn metadata
          |
          v
Front prompt build
  |
  +-- compact NOW block
  +-- compact PLACE block
  +-- SelfModel capsule
  |
  v
Task dispatch
  |
  +-- include grounding ids
  +-- include resolved date/place refs
  |
  v
Back / Planner / Fabric / Agent
  |
  +-- receive scoped projection
  +-- use ISO windows and place ids, not guesses
```

### Diagram 8: Agent Grounding Lease

```text
Back or Fabric spawns agent
  |
  v
AgentFactory.spawn(contract, params, session_id, trace_id)
  |
  +-- ContextBuilder reads contract sections
  +-- GroundingLeaseBuilder reads temporal/spatial envelope
  +-- Policy filter redacts by contract precision
  |
  v
+--------------------------------------------------+
| AgentGroundingLease                              |
|   lease_id                                       |
|   expires_at_utc                                 |
|   temporal_anchor + windows                      |
|   semantic place / relevant place ids            |
|   active member ref                              |
|   allowed sections                               |
|   denied sections                                |
|   redactions                                     |
+--------------------------------------------------+
  |
  v
Spawned Agent executes with bounded ambient intelligence
```

## Pattern-Matched Service Design

### Shared Design Rules

`k1.temporal` and `k1.spatial` should share the same architectural skeleton:

```text
k1/<module>/
  __init__.py
  config.py            -- frozen config / defaults
  types.py             -- pure dataclasses, enums, errors
  events.py            -- topic names + payload dataclasses
  factory.py           -- pure static composition root
  ports/               -- Protocols only
  adapters/            -- wrappers around external systems
  service/             -- business logic services
  kernel/              -- bundle + handle for KernelService integration
  tests/               -- focused tests
```

Factory methods should match Planner/Fabric conventions:

```python
class TemporalFactory:
    def __init__(self) -> None:
        raise TypeError("TemporalFactory is a pure static factory")

    @staticmethod
    def create_standalone(config: TemporalConfig | None = None) -> TemporalServiceBundle: ...

    @staticmethod
    def create_for_testing(config: TemporalConfig | None = None, **overrides: Any) -> tuple[TemporalServiceBundle, dict[str, Any]]: ...

    @staticmethod
    def create_with_ports(*, clock_port: IClockPort, event_port: IEventPort, state_port: ITemporalStatePort, ...) -> TemporalServiceBundle: ...

    @staticmethod
    def create_production(*, clock_port: IClockPort, event_port: IEventPort, state_port: ITemporalStatePort, ...) -> TemporalServiceBundle: ...
```

Spatial should mirror the same shape:

```python
class SpatialFactory:
    @staticmethod
    def create_standalone(config: SpatialConfig | None = None) -> SpatialServiceBundle: ...

    @staticmethod
    def create_for_testing(config: SpatialConfig | None = None, **overrides: Any) -> tuple[SpatialServiceBundle, dict[str, Any]]: ...

    @staticmethod
    def create_with_ports(*, device_place_port: IDevicePlacePort, place_registry_port: IPlaceRegistryPort, event_port: IEventPort, policy_port: ISpatialPolicyPort, ...) -> SpatialServiceBundle: ...

    @staticmethod
    def create_production(*, device_place_port: IDevicePlacePort, place_registry_port: IPlaceRegistryPort, event_port: IEventPort, policy_port: ISpatialPolicyPort, ...) -> SpatialServiceBundle: ...
```

### Temporal Factory Wiring Order

Recommended production V0 `_wire()` order:

```text
Step 0:  validate config
Step 1:  validate ports and duplicate identities
Step 2:  clock = injected IClockPort
Step 3:  timezone_resolver = TimezoneResolver(device_tz_port, spatial_tz_port, persona_tz_port, fallback_utc=True)
Step 4:  window_builder = TemporalWindowBuilder(clock, timezone_resolver, config)
Step 5:  expression_resolver = TemporalExpressionResolver(window_builder, routines_port=None)
Step 6:  projection_renderer = TemporalProjectionRenderer(config)
Step 7:  event_emitter = TemporalEventEmitter(event_port)
Step 8:  service = TemporalService(clock, timezone_resolver, window_builder, expression_resolver, event_emitter)
Step 9:  bundle = TemporalServiceBundle(service, renderer, config, health, shutdown)
Step 10: return bundle
```

Production V0 must include deterministic expression resolution for common household phrases such as `today`, `tomorrow`, `tonight`, `this weekend`, `next Monday`, and routine-backed windows when routines exist. If later NLP/LLM temporal parsing is added, it should be a separate optional `ITemporalParserPort` behind the resolver; absence of that parser must not remove kernel-level temporal resolution.

The source order is locked as device timezone, then spatial place timezone, then persona timezone, then UTC safe mode. Expression resolution is locked to typed candidates, token objects, phrase catalogs, routine registries, and explicit rules. Pattern matching can exist only inside curated leaf helpers; it must never become the resolver contract or the source of truth.

### Spatial Factory Wiring Order

Recommended production V0 `_wire()` order:

```text
Step 0:  validate config
Step 1:  validate ports and duplicate identities
Step 2:  device_surface_resolver = DeviceSurfaceResolver(device_port, config)
Step 3:  place_resolver = PlaceResolver(place_registry_port, geocoder_port=None)
Step 4:  presence_resolver = PresenceResolver(presence_port=None)
Step 5:  privacy_projector = SpatialPrivacyProjector(policy_port, selfmodel_port=None)
Step 6:  projection_renderer = SpatialProjectionRenderer(config)
Step 7:  event_emitter = SpatialEventEmitter(event_port)
Step 8:  service = SpatialService(device_surface_resolver, place_resolver, presence_resolver, privacy_projector, event_emitter)
Step 9:  bundle = SpatialServiceBundle(service, renderer, config, health, shutdown)
Step 10: return bundle
```

Production V0 must define semantic, approximate, place-id, and raw-coordinate projection types plus the privacy gate for each. A deployment may run without raw GPS or geocoding, but that is a degraded input-source state, not a reduced feature surface.

### Kernel Bootstrap Wrappers

To match SelfModel's kernel-facing API, each module should also expose wrapper functions:

```text
k1.temporal.kernel.bootstrap
  TemporalServiceBundle
  build_temporal_bundle(...)

k1.temporal.kernel.handle
  TemporalHandle
  build_temporal_handle(...)

k1.spatial.kernel.bootstrap
  SpatialServiceBundle
  build_spatial_bundle(...)

k1.spatial.kernel.handle
  SpatialHandle
  build_spatial_handle(...)
```

These wrappers can call the factories internally, but KernelService should import only the kernel bootstrap/handle surfaces, the same way it imports SelfModel today.

### Kernel-Visible Ports

Add kernel-level ports only for surfaces that cross subsystem boundaries. Keep pure dataclasses in `types.py` so importing ports does not import services.

```text
k1/kernel/ports/temporal_port.py
  ITemporalPort
    get_anchor(session_id) -> TemporalAnchor
    get_windows(session_id) -> Mapping[str, TemporalWindow]
    resolve_expression(request) -> ResolvedTemporalExpression
    build_projection(request) -> TemporalProjection
    refresh_turn(request) -> TemporalTurnSnapshot
    shutdown() -> None

k1/kernel/ports/spatial_port.py
  ISpatialPort
    get_context(session_id) -> SpatialContext
    resolve_place(request) -> PlaceRef | None
    build_projection(request) -> SpatialProjection
    refresh_turn(request) -> SpatialTurnSnapshot
    shutdown() -> None

k1/kernel/ports/grounding_port.py
  IGroundingPort
    create_envelope(request) -> GroundingEnvelope
    build_projection(request) -> GroundingProjection
    build_agent_lease(request) -> AgentGroundingLease
    refresh_if_stale(request) -> GroundingEnvelope
    shutdown() -> None

k1/kernel/ports/device_context_port.py
  IDeviceContextPort
    get_snapshot(session_id, device_id, installation_id) -> DeviceContextSnapshot
    update_snapshot(request) -> DeviceContextSnapshot
```

### Runtime Attachment Pattern

Concierge currently has `set_self_model(handle)` with a pre-start guard. Temporal/spatial should follow that shape.

```python
class ConciergeRuntime:
    def set_temporal(self, handle: Any) -> None:
        if self._started:
            raise RuntimeError("set_temporal() must be called before start()")
        self._temporal = handle

    def set_spatial(self, handle: Any) -> None:
        if self._started:
            raise RuntimeError("set_spatial() must be called before start()")
        self._spatial = handle
```

The mailbox consumer then passes the handles into Front/Back routes:

```text
front_handler(..., self_model=self._self_model, temporal=self._temporal, spatial=self._spatial)
route_back_envelope(..., temporal=self._temporal, spatial=self._spatial, hil_port=self._hil_port)
```

The safer intermediate step is to let handles write SessionState sections and let Front/Back read those sections. Direct handle injection is still useful for explicit refresh and scoped projection rendering.

### SessionState Adapter Pattern

Do not let TemporalService or SpatialService mutate arbitrary SessionState internals. Use small adapters.

```text
TemporalHandle
  |
  +-- TemporalStateAdapter
        |-- read current temporal section
        |-- write temporal section
        |-- mirror control.set_temporal_anchor(anchor_dict) during migration

SpatialHandle
  |
  +-- SpatialStateAdapter
        |-- read spatial section
        |-- write spatial section
        |-- never write raw coordinates into prompt-facing fields
```

This follows Planner's `SessionStateReadAdapter` and Fabric's `ISessionStateReader` pattern: core services see a narrow port, not the whole manager.

### Event Topics

Temporal events:

```text
k1.temporal.anchor.created.v1
k1.temporal.anchor.refreshed.v1
k1.temporal.expression.resolved.v1
k1.temporal.expression.ambiguous.v1
k1.temporal.anchor.stale.v1
```

Spatial events:

```text
k1.spatial.context.created.v1
k1.spatial.context.refreshed.v1
k1.spatial.place.resolved.v1
k1.spatial.context.redacted.v1
k1.spatial.location.unavailable.v1
```

Grounding events:

```text
k1.grounding.envelope.created.v1
k1.grounding.projection.created.v1
k1.grounding.projection.denied.v1
```

All event publishers should go through `IEventPort` adapters. Session-scoped events should use the session bus. Kernel/global health events can use the kernel bus.

### Health Shape

Match SelfModel's `health()` style.

```json
{
  "status": "ok",
  "module": "temporal",
  "started_at_ms": 1779123456789,
  "clock": {"source": "system", "available": true},
  "timezone": {"source_order": ["device", "spatial", "persona", "utc"]},
  "last_anchor_id": "temp_...",
  "last_refresh_ms": 1779123456999,
  "safe_mode": false
}
```

```json
{
  "status": "degraded",
  "module": "spatial",
  "started_at_ms": 1779123456789,
  "place_registry": {"available": false, "mode": "semantic_only"},
  "device_location": {"available": false},
  "last_context_id": "spatial_...",
  "safe_mode": false
}
```

Degraded spatial must not block normal assistant use. It should produce explicit `unknown`, `hidden`, `unavailable`, or semantic-precision projections.

## Production Service Folder And File Map

This is the concrete production implementation target. The package map is intentionally explicit: no hidden dynamic discovery, no prompt-string source of truth, no regular-expression-driven core parsing, and no accidental path where raw device data becomes prompt text. Every file exists to keep ownership narrow enough that the system can scale across many device classes, privacy regimes, household configurations, and deployment regions.

### Core Parsing And Resolution Rule

The temporal and spatial cores should not use regular expressions as their resolver contract. Resolution should be built from typed inputs, explicit rule classes, normalized tokens, curated phrase catalogs, routine/place registries, and deterministic state machines.

Allowed shape:

```text
DeviceContextSnapshot
TaskDispatch params
Front semantic candidates
Known place registry entries
Known routine registry entries
Normalized token sequence
  -> typed rule object
  -> typed resolution object
  -> auditable confidence/provenance
```

Disallowed shape:

```text
freeform prompt string
  -> ad hoc regular expression match
  -> guessed date/place string
  -> tool call
```

If later language parsing needs ML or LLM support, it must live behind an optional port and return candidate objects with provenance. Kernel correctness must not depend on scraping prompt text.

### Production Package Overview

```text
k1/
  temporal/            -- authoritative time, timezone, windows, temporal expressions
  spatial/             -- authoritative device/place/presence projection and privacy filtering
  grounding/           -- consumer-scoped envelope, projections, leases, propagation metadata
  kernel/ports/        -- subsystem-crossing Protocols only
  sessionstate/sections/ -- canonical HOT/WARM projections visible to the rest of K1
```

`k1.temporal` and `k1.spatial` are source modules. `k1.grounding` is the envelope and projection module that joins their outputs with identity, policy, consumer scope, and propagation metadata.

`DeviceContextSnapshot` lives as a pure dataclass in `k1.grounding.types`. `k1/kernel/ports/device_context_port.py` owns the producer/reader Protocol so UI, browser, app, and kernel session creation paths can provide the installed-device observation without importing temporal or spatial services.

### `k1/temporal/` File Map

```text
k1/temporal/
  __init__.py
    -- exports stable public types and factory entry points only; no adapter imports.
  config.py
    -- frozen TemporalConfig, TTLs, timezone fallback order, window defaults, locale defaults.
  types.py
    -- TemporalAnchor, TemporalWindow, ResolvedTemporalExpression, TemporalProjection, TemporalTurnSnapshot, provenance enums, freshness states.
  errors.py
    -- TemporalError hierarchy for invalid timezone, stale anchor, ambiguous expression, unavailable clock, and unsupported locale.
  events.py
    -- temporal event topic constants and payload dataclasses for anchor creation, refresh, expression resolution, ambiguity, and staleness.
  factory.py
    -- pure static TemporalFactory; validates config/ports, rejects duplicate port identities, wires services and bundle.
  constants.py
    -- canonical labels for standard windows, time-of-day buckets, weekdays, freshness states, and timezone source names.
  serialization.py
    -- explicit dataclass-to-dict and dict-to-dataclass helpers for SessionState and event payloads.

k1/temporal/ports/
  __init__.py
    -- re-exports Protocol names for factory validation and tests.
  clock_port.py
    -- IClockPort for UTC wall clock and monotonic time; isolates OS clock reads.
  device_context_port.py
    -- ITemporalDeviceContextPort for device timezone, locale, observed timestamp, installation ID, and clock-skew metadata.
  timezone_port.py
    -- ITimezonePort for persona/spatial/provider timezone candidates and validation.
  routine_port.py
    -- IRoutinePort for household routine windows such as school, bedtime, commute, dinner, and quiet hours.
  state_port.py
    -- ITemporalStatePort for reading/writing TemporalSection without exposing SessionStateManager internals.
  event_port.py
    -- ITemporalEventPort for publish/subscribe through kernel or session bus adapters.
  id_port.py
    -- ITemporalIdPort for anchor/window/resolution IDs; keeps ID shape deterministic and testable.
  metrics_port.py
    -- ITemporalMetricsPort for counters/timers around refresh, staleness, ambiguity, and source fallback.
  policy_port.py
    -- ITemporalPolicyPort for routine/calendar sensitivity decisions before projection.

k1/temporal/adapters/
  __init__.py
    -- exports adapter classes for production wiring; core services do not import this package.
  system_clock_adapter.py
    -- reads system UTC and monotonic time via Python runtime.
  device_context_adapter.py
    -- adapts installed-device/session metadata into ITemporalDeviceContextPort.
  persona_timezone_adapter.py
    -- reads fallback timezone/locale from Persona or SelfModel-compatible identity data.
  spatial_timezone_adapter.py
    -- reads timezone candidates from Spatial place refs when an active place is known.
  session_state_adapter.py
    -- writes TemporalSection and mirrors control.temporal_anchor during migration.
  event_bus_adapter.py
    -- publishes temporal events to the proper kernel or session bus.
  null_routine_adapter.py
    -- returns explicit routine-unavailable results for deployments with no routine provider.
  selfmodel_routine_adapter.py
    -- reads allowed household routines through SelfModel policy gates when available.
  uuid_id_adapter.py
    -- generates production IDs for anchors, windows, and resolutions.
  null_metrics_adapter.py
    -- no-op metrics implementation for tests and standalone mode.

k1/temporal/service/
  __init__.py
    -- keeps service imports explicit for factory wiring.
  anchor_builder.py
    -- builds TemporalAnchor from clock/device/timezone inputs with confidence and provenance.
  timezone_resolver.py
    -- chooses timezone using device -> spatial place -> persona -> UTC order and records fallback reason.
  locale_resolver.py
    -- resolves locale and week-start conventions without coupling to prompts.
  clock_skew_checker.py
    -- detects stale or inconsistent device observed timestamps compared with server/runtime time.
  window_builder.py
    -- computes yesterday, today, tomorrow, week, weekend, month, and custom windows from anchor.
  daylight_boundary.py
    -- owns DST and timezone boundary handling for windows and recurrence expansion.
  freshness_evaluator.py
    -- marks anchors and resolutions live, stale, degraded, or unavailable by TTL and source.
  expression_candidates.py
    -- accepts structured candidate spans/phrases from Front/task params; does not scrape prompts as authority.
  phrase_catalog.py
    -- curated exact phrase and synonym catalog for household temporal expressions by locale.
  temporal_tokens.py
    -- normalized token objects for weekdays, offsets, ordinals, day-parts, deadlines, and routine labels.
  relative_day_rules.py
    -- typed rules for today, tomorrow, yesterday, tonight, this morning, and similar day-relative phrases.
  weekday_rules.py
    -- typed rules for next Monday, this Friday, by Friday, weekend, and locale-aware week references.
  offset_rules.py
    -- typed rules for in two days, in three weeks, last month, next month, and similar offset phrases.
  routine_window_resolver.py
    -- resolves after school, before dinner, bedtime, and commute windows through IRoutinePort.
  ambiguity_resolver.py
    -- marks unresolved or multi-meaning expressions and prepares clarification reasons.
  expression_resolver.py
    -- orchestrates candidate selection, rule execution, routine lookup, confidence scoring, and final resolved expression output.
  projection_builder.py
    -- builds TemporalProjection variants for Front, Back, Planner, Fabric, Agent, Tool, and Memory consumers.
  projection_renderer.py
    -- renders compact prompt blocks from TemporalProjection only; no direct SessionState reads.
  event_emitter.py
    -- converts service outcomes to temporal events through ITemporalEventPort.
  temporal_service.py
    -- top-level deterministic service API for refresh, get anchor, get windows, resolve expressions, and build projections.
  health.py
    -- health snapshot for clock, timezone source order, last anchor, last refresh, degraded states, and safe mode.

k1/temporal/kernel/
  __init__.py
    -- exports kernel bootstrap and handle types.
  bootstrap.py
    -- TemporalServiceBundle, build_temporal_bundle(), health(), shutdown(); imported by KernelService Tier 1.
  handle.py
    -- TemporalHandle, build_temporal_handle(), install_into_session(), uninstall_from_session(); imported during session creation.
  session_binding.py
    -- immutable binding data for session_id, actor_id, device_id, installation_id, bus scope, and state adapter.
```

### `k1/spatial/` File Map

```text
k1/spatial/
  __init__.py
    -- exports stable public types and factory entry points only; no production adapter imports.
  config.py
    -- frozen SpatialConfig, precision defaults, freshness TTLs, geofence thresholds, projection defaults.
  types.py
    -- DeviceSurface, LocationFix, PlaceRef, Geofence, SpatialContext, SpatialProjection, PresenceRef, redaction types; consumes shared DeviceContextSnapshot from k1.grounding.types.
  errors.py
    -- SpatialError hierarchy for permission denial, stale location, invalid coordinates, missing registry, and policy denial.
  events.py
    -- spatial event topic constants and payload dataclasses for context creation, refresh, redaction, place resolution, and unavailable location.
  factory.py
    -- pure static SpatialFactory; validates config/ports, rejects duplicate port identities, wires services and bundle.
  constants.py
    -- canonical precision levels, permission states, place kinds, surface kinds, and redaction reason codes.
  serialization.py
    -- explicit dataclass-to-dict and dict-to-dataclass helpers for SessionState, events, and contracts.

k1/spatial/ports/
  __init__.py
    -- re-exports Protocol names for factory validation and tests.
  device_context_port.py
    -- ISpatialDeviceContextPort for device ID, installation ID, surface kind, permission state, observed timestamp, and semantic hint.
  device_location_port.py
    -- IDeviceLocationPort for optional raw or approximate location fixes from installed devices.
  place_registry_port.py
    -- IPlaceRegistryPort for household places, member default places, geofences, aliases, and timezone by place.
  geocoder_port.py
    -- IGeocoderPort for optional address/geocode lookups; unavailable state must be explicit.
  presence_port.py
    -- IPresencePort for co-presence/member presence candidates under policy.
  policy_port.py
    -- ISpatialPolicyPort for precision decisions by actor, subject, task, consumer, and capability contract.
  state_port.py
    -- ISpatialStatePort for reading/writing SpatialSection and PlaceRegistrySection without exposing SessionStateManager internals.
  event_port.py
    -- ISpatialEventPort for publish/subscribe through kernel or session bus adapters.
  id_port.py
    -- ISpatialIdPort for context, place, geofence, fix, and projection IDs.
  metrics_port.py
    -- ISpatialMetricsPort for source availability, redaction, stale input, geofence, and policy counters.

k1/spatial/adapters/
  __init__.py
    -- exports adapter classes for production wiring; core services do not import this package.
  device_context_adapter.py
    -- adapts installed-device/session metadata into ISpatialDeviceContextPort.
  null_device_location_adapter.py
    -- returns explicit location-unavailable state when no raw sensor exists.
  browser_device_location_adapter.py
    -- adapts browser/app supplied permission and location payloads when present.
  local_place_registry_adapter.py
    -- reads configured household places from local/session settings for standalone and test deployments.
  bridge_place_registry_adapter.py
    -- bridges to durable K0/Bridge-backed household place registry when available.
  null_geocoder_adapter.py
    -- returns explicit geocoder-unavailable results without blocking spatial context.
  null_presence_adapter.py
    -- returns explicit presence-unavailable results for privacy-safe default behavior.
  selfmodel_policy_adapter.py
    -- maps SelfModel/constitution decisions into spatial precision and redaction policy.
  session_state_adapter.py
    -- writes SpatialSection and PlaceRegistrySection projections; never writes raw coordinates into prompt-facing fields.
  event_bus_adapter.py
    -- publishes spatial events to the proper kernel or session bus.
  uuid_id_adapter.py
    -- generates production IDs for contexts, fixes, places, geofences, and projections.
  null_metrics_adapter.py
    -- no-op metrics implementation for tests and standalone mode.

k1/spatial/service/
  __init__.py
    -- keeps service imports explicit for factory wiring.
  device_surface_resolver.py
    -- classifies phone, shared hub, desktop, car, watch, browser, or unknown surface from device context.
  permission_normalizer.py
    -- normalizes granted, denied, hidden, unavailable, stale, and degraded permission states.
  location_normalizer.py
    -- validates coordinates, accuracy, timestamp freshness, source confidence, and privacy class.
  place_registry_service.py
    -- loads and normalizes household places, aliases, geofences, member defaults, and registry availability state.
  place_candidate_source.py
    -- accepts structured place candidates from task params, NLU output, calendar event locations, and device semantic hints.
  place_alias_catalog.py
    -- curated explicit aliases for home, school, work, car, room names, and family-defined place labels.
  place_resolver.py
    -- resolves place candidates to PlaceRef objects with confidence/provenance and unknown-safe fallback.
  geofence_matcher.py
    -- computes point-in-geofence and distance thresholds with explicit coordinate availability checks.
  presence_resolver.py
    -- resolves co-presence and member presence candidates through IPresencePort and policy.
  precision_selector.py
    -- selects hidden, semantic, approximate, place-id, or raw precision by consumer and task.
  privacy_projector.py
    -- redacts or downgrades spatial facts according to ISpatialPolicyPort and records redaction reasons.
  projection_builder.py
    -- builds SpatialProjection variants for Front, Back, Planner, Fabric, Agent, Tool, and Memory consumers.
  projection_renderer.py
    -- renders prompt-safe PLACE blocks from SpatialProjection only; never sees raw coordinates unless policy allowed.
  event_emitter.py
    -- converts service outcomes to spatial events through ISpatialEventPort.
  spatial_service.py
    -- top-level deterministic service API for refresh, get context, resolve place, build projection, and health.
  health.py
    -- health snapshot for device source, registry, geocoder, presence, policy, last context, degraded states, and safe mode.

k1/spatial/kernel/
  __init__.py
    -- exports kernel bootstrap and handle types.
  bootstrap.py
    -- SpatialServiceBundle, build_spatial_bundle(), health(), shutdown(); imported by KernelService Tier 1.
  handle.py
    -- SpatialHandle, build_spatial_handle(), install_into_session(), uninstall_from_session(); imported during session creation.
  session_binding.py
    -- immutable binding data for session_id, actor_id, device_id, installation_id, bus scope, and state adapter.
```

### `k1/grounding/` File Map

```text
k1/grounding/
  __init__.py
    -- exports GroundingEnvelope, projection request/response types, lease types, and factory entry points.
  config.py
    -- frozen GroundingConfig, envelope TTLs, default consumer scopes, lease TTLs, and projection defaults.
  types.py
    -- DeviceContextSnapshot, GroundingEnvelope, GroundingFreshness, GroundingSource, GroundingProjection, ConsumerScope, AgentGroundingLease, propagation IDs.
  errors.py
    -- GroundingError hierarchy for projection denial, stale envelope, missing temporal source, missing spatial source, and lease expiry.
  events.py
    -- grounding event topic constants and payload dataclasses for envelope creation, projection creation, lease creation, denial, and expiry.
  factory.py
    -- pure static GroundingFactory; wires envelope builder, projection policy, lease builder, propagation helpers, and event emitter.
  constants.py
    -- canonical consumer names, projection scopes, lease statuses, redaction reason codes, and propagation field names.
  serialization.py
    -- explicit dataclass-to-dict and dict-to-dataclass helpers for context_snapshot, reference_context, SessionState, and events.

k1/grounding/ports/
  __init__.py
    -- re-exports Protocol names for factory validation and tests.
  temporal_port.py
    -- IGroundingTemporalPort view over temporal handle/service projection methods.
  spatial_port.py
    -- IGroundingSpatialPort view over spatial handle/service projection methods.
  identity_port.py
    -- IGroundingIdentityPort for active actor/member/device identity refs, usually backed by SelfModel.
  policy_port.py
    -- IGroundingPolicyPort for consumer scope, redaction, and lease permission decisions.
  state_port.py
    -- IGroundingStatePort for writing latest envelope metadata without exposing SessionStateManager internals.
  event_port.py
    -- IGroundingEventPort for publish/subscribe through kernel or session bus adapters.
  id_port.py
    -- IGroundingIdPort for envelope, projection, and lease IDs.
  metrics_port.py
    -- IGroundingMetricsPort for envelope/projection counts, denied projections, stale reads, and lease refresh.

k1/grounding/adapters/
  __init__.py
    -- exports adapter classes for production wiring; core services do not import this package.
  temporal_handle_adapter.py
    -- adapts TemporalHandle into IGroundingTemporalPort.
  spatial_handle_adapter.py
    -- adapts SpatialHandle into IGroundingSpatialPort.
  selfmodel_identity_adapter.py
    -- adapts SelfModel handle/capsule data into identity refs for envelopes.
  selfmodel_policy_adapter.py
    -- adapts SelfModel/constitution policy into projection and lease decisions.
  session_state_adapter.py
    -- writes GroundingSection metadata and reads current temporal/spatial section IDs when needed.
  event_bus_adapter.py
    -- publishes grounding events to the proper kernel or session bus.
  uuid_id_adapter.py
    -- generates production IDs for envelopes, projections, and leases.
  null_metrics_adapter.py
    -- no-op metrics implementation for tests and standalone mode.

k1/grounding/service/
  __init__.py
    -- keeps service imports explicit for factory wiring.
  envelope_builder.py
    -- combines temporal projection, spatial projection, identity refs, freshness, provenance, and redactions into GroundingEnvelope.
  projection_policy.py
    -- chooses allowed temporal/spatial precision by consumer, actor, task, and capability contract.
  projection_builder.py
    -- builds Front, Back, Planner, Fabric, Tool, Agent, and Memory projections from one envelope family.
  lease_builder.py
    -- builds AgentGroundingLease with TTL, allowed/denied sections, redactions, and refresh policy.
  context_snapshot_builder.py
    -- builds compatibility context_snapshot payloads while typed fields propagate through codebase.
  reference_context_builder.py
    -- builds compatibility reference_context grounding payloads for TaskDispatch migration.
  invocation_metadata.py
    -- builds baseline Fabric/tool invocation metadata with anchor/context/envelope IDs and invoked_at_utc.
  propagation.py
    -- owns exact propagation field names for Front -> Back -> Planner/Fabric/Agent traces.
  prompt_block_renderer.py
    -- renders combined NOW/PLACE/EXECUTION GROUNDING blocks from projections only.
  stale_envelope_checker.py
    -- enforces envelope TTL and requests refresh for long-running work.
  event_emitter.py
    -- converts envelope/projection/lease outcomes to grounding events through IGroundingEventPort.
  grounding_service.py
    -- top-level deterministic API for create envelope, build projection, build lease, refresh, and health.
  health.py
    -- health snapshot for last envelope, projection denial counts, stale envelope counts, lease expiry, and safe mode.

k1/grounding/kernel/
  __init__.py
    -- exports kernel bootstrap and handle types.
  bootstrap.py
    -- GroundingServiceBundle, build_grounding_bundle(), health(), shutdown(); imported by KernelService Tier 1 after temporal/spatial.
  handle.py
    -- GroundingHandle, build_grounding_handle(), install_into_session(), uninstall_from_session(); imported during session creation.
  session_binding.py
    -- immutable binding data for session_id, actor_id, device_id, temporal handle, spatial handle, self model handle, and state adapter.
```

### Kernel Port File Map

```text
k1/kernel/ports/temporal_port.py
  -- kernel-visible ITemporalPort plus request/response imports; no service or adapter imports.
k1/kernel/ports/spatial_port.py
  -- kernel-visible ISpatialPort plus request/response imports; no service or adapter imports.
k1/kernel/ports/grounding_port.py
  -- kernel-visible IGroundingPort for envelope/projection/lease creation across Concierge, Planner, Fabric, and memory.
k1/kernel/ports/device_context_port.py
  -- kernel-level Protocol for installed-device context snapshots when session creation receives them from UI/app layers; pure dataclass lives in k1.grounding.types.
```

### SessionState Section File Map

```text
k1/sessionstate/sections/temporal.py
  -- canonical HOT TemporalSection with anchor, windows, resolved expressions, freshness, provenance, and last turn ID.
k1/sessionstate/sections/spatial.py
  -- canonical HOT SpatialSection with current context, active place, surface, co-presence summary, precision, redactions, and freshness.
k1/sessionstate/sections/place_registry.py
  -- WARM durable PlaceRegistrySection with household places, geofences, aliases, member defaults, timezone hints, and registry status.
k1/sessionstate/sections/grounding.py
  -- HOT GroundingSection with latest envelope IDs, projection IDs, source section versions, and redaction summaries; no raw location payload.
k1/sessionstate/sections/control.py
  -- keeps compatibility mirror for temporal_anchor and stores latest grounding envelope ID during migration.
k1/sessionstate/sections/__init__.py
  -- exports temporal, spatial, place_registry, and grounding sections so Fabric and UI can discover canonical names.
k1/sessionstate/sections/temporal_context.py
  -- compatibility shim that delegates to k1.temporal during migration, then becomes deprecated import surface.
```

### Concierge Integration File Map

```text
k1/concierge/session.py
  -- adds set_temporal(), set_spatial(), set_grounding() pre-start guards and passes handles into Front/Back routes.
k1/concierge/factory.py
  -- extends PortBundle/create_with_ports with temporal, spatial, and grounding handles or ports.
k1/concierge/fsm/controller.py
  -- refreshes temporal/spatial at turn start, creates grounding envelope, stamps turn metadata, and writes canonical sections.
k1/concierge/actors/front.py
  -- consumes Front grounding projection, resolves dispatch refs, and emits typed resolved temporal/spatial refs.
k1/concierge/actors/back.py
  -- consumes Back execution grounding projection before ReAct loop and prefers resolved refs over tool-discovered guesses.
k1/concierge/task/dispatch.py
  -- carries grounding_envelope_id, temporal_anchor_id, spatial_context_id, resolved_temporal_refs, and resolved_spatial_refs.
k1/concierge/prompt/builder.py
  -- reads temporal/spatial/grounding canonical sections and stops mapping temporal_context to control.
k1/concierge/prompt/sections.py
  -- registers temporal, spatial, and grounding prompt section names and scopes.
k1/concierge/prompt/grounding_renderer.py
  -- renders NOW, PLACE, EXECUTION GROUNDING, and PLANNING GROUNDING blocks from GroundingProjection only.
k1/concierge/prompt/back_prompt.py
  -- accepts execution grounding block/typed projection and places it before task/tool instructions.
```

### Planner And Orchestrator Integration File Map

```text
k1/orchestrator/types.py
  -- adds typed grounding field to PlanRequest and TaskEnvelope while mirroring into constraints for compatibility.
k1/orchestrator/orchestration/orchestrator_service.py
  -- preserves grounding IDs, forwards constraints, and records envelope metadata in events/logs.
k1/planner/ports/grounding_port.py
  -- planner-local Protocol for reading typed grounding projections without importing k1.grounding services.
k1/planner/adapters/grounding_adapter.py
  -- adapts kernel/session GroundingHandle into Planner grounding port.
k1/planner/stages/sketch_service.py
  -- always receives temporal constraints and unknown-safe spatial constraints before LLM prompt construction.
k1/planner/stages/expand_service.py
  -- carries temporal/spatial constraints through expansion and tool planning.
k1/planner/stages/validate_service.py
  -- validates that plans do not ignore required time/place constraints or use stale envelope IDs.
k1/planner/pipeline_controller.py
  -- threads grounding metadata through stage inputs, deltas, and plan metadata.
```

### Fabric, Tool, And Agent Integration File Map

```text
k1/fabric/core/context_builder.py
  -- reads declared temporal/spatial/grounding sections and applies contract precision before ExecutionContext creation.
k1/fabric/contracts/context_precision.py
  -- defines allowed precision values for temporal and spatial context in capability contracts.
k1/fabric/providers/agent_provider.py
  -- requests AgentGroundingLease when spawning agents and passes lease into agent context.
k1/fabric/providers/tool_provider.py
  -- passes baseline invocation grounding to deterministic tools without exposing raw spatial data by default.
k1/contracts/tools/date_calc.yaml
  -- declares required temporal context so date arithmetic is anchored.
k1/contracts/tools/build_agent.yaml
  -- declares required temporal context and optional spatial context with lease precision.
k1/contracts/schemas/grounding.schema.json
  -- contract schema for grounding_invocation, projection precision, and lease requirements.
k1/contracts/schemas/context_precision.schema.json
  -- validates temporal/spatial precision declarations in tool and agent contracts.
```

### Memory And K0 Integration File Map

```text
k1/memory/grounding_metadata.py
  -- maps grounding envelope IDs, temporal anchor IDs, and semantic place IDs into memory write metadata.
k1/memory/spatial_redaction.py
  -- enforces that raw location is excluded from memory writes unless a policy-approved path explicitly permits it.
k0/memory/time_place_index.py
  -- durable index helper for recall by local date, time window, place ID, and semantic place facets when K0 integration is active.
```

If the actual memory packages use different names when implementation starts, keep these responsibilities intact and adapt the file names to the local module convention.

### Focused Test File Map

```text
tests/k1/temporal/test_factory_wiring.py
  -- validates TemporalFactory config/port checks, duplicate rejection, and standalone/test wiring.
tests/k1/temporal/test_anchor_builder.py
  -- validates anchor creation from system clock, device timezone, locale, provenance, and confidence.
tests/k1/temporal/test_window_builder.py
  -- validates today/tomorrow/week/weekend/month windows across timezone and locale boundaries.
tests/k1/temporal/test_dst_boundaries.py
  -- validates DST spring/fall edge cases and exclusive end behavior.
tests/k1/temporal/test_expression_resolver.py
  -- validates typed rule resolution for tomorrow, next Monday, tonight, this weekend, by Friday, and in two weeks.
tests/k1/temporal/test_routine_windows.py
  -- validates after school, bedtime, dinner, and unavailable-routine ambiguity behavior.
tests/k1/temporal/test_session_state_adapter.py
  -- validates TemporalSection writes and control.temporal_anchor compatibility mirror.

tests/k1/spatial/test_factory_wiring.py
  -- validates SpatialFactory config/port checks, duplicate rejection, and standalone/test wiring.
tests/k1/spatial/test_device_context.py
  -- validates device surface, installation ID, permission state, observed timestamp, and unavailable sensor behavior.
tests/k1/spatial/test_location_normalizer.py
  -- validates coordinate sanity, accuracy, freshness, permission state, and degraded fix handling.
tests/k1/spatial/test_place_resolver.py
  -- validates known place, alias, semantic hint, calendar location, and unknown-safe fallback behavior.
tests/k1/spatial/test_geofence_matcher.py
  -- validates geofence membership and unavailable-coordinate behavior.
tests/k1/spatial/test_privacy_projector.py
  -- validates hidden, semantic, approximate, place-id, raw precision gating and redaction reasons.
tests/k1/spatial/test_session_state_adapter.py
  -- validates SpatialSection and PlaceRegistrySection writes without prompt-facing raw coordinates.

tests/k1/grounding/test_envelope_builder.py
  -- validates envelope creation from temporal, spatial, identity, freshness, provenance, and redactions.
tests/k1/grounding/test_projection_policy.py
  -- validates per-consumer projection precision for Front, Back, Planner, Fabric, Tool, Agent, and Memory.
tests/k1/grounding/test_agent_lease.py
  -- validates lease TTL, allowed/denied sections, redactions, expiry, and refresh behavior.
tests/k1/grounding/test_propagation.py
  -- validates envelope IDs through reference_context, context_snapshot, planner constraints, and Fabric invocation metadata.

tests/k1/concierge/test_grounding_turn_start.py
  -- focused integration test for FSM refresh, section writes, envelope creation, and Front prompt projection.
tests/k1/concierge/test_back_execution_grounding.py
  -- focused integration test proving Back sees execution grounding and simple tomorrow uses resolved windows.
tests/k1/planner/test_grounding_constraints.py
  -- focused integration test proving Planner always receives temporal constraints and unknown-safe spatial constraints.
tests/k1/fabric/test_grounding_context_builder.py
  -- focused integration test proving contracts receive temporal/spatial sections by declaration and precision.
```

These tests should be run only as targeted files. Do not use the full kernel or full Fabric suites for this work unless explicitly requested.

### File Ownership Boundaries

```text
Temporal owns:
  current instant, timezone, windows, expression resolution, temporal projections.

Spatial owns:
  device surface, location availability, place registry projection, presence candidates, spatial privacy projection.

Grounding owns:
  envelope creation, consumer projection, agent lease, propagation IDs, compatibility payload builders.

SessionState owns:
  durable live projections for other modules to read; it does not compute time/place.

Concierge owns:
  turn timing, prompt consumption, dispatch propagation, and actor-specific use of projections.

Planner/Fabric/Agents own:
  respecting grounding constraints and declared precision; they do not infer ambient time/place themselves.
```

## Proposed `k1.temporal` Module

### Temporal Package Sketch

```text
k1/temporal/
  __init__.py
  config.py
  types.py
  events.py
  factory.py
  ports/
    clock_port.py
    event_port.py
    parser_port.py
    routine_port.py
    state_port.py
    timezone_port.py
  adapters/
    event_bus_adapter.py
    null_parser_adapter.py
    persona_timezone_adapter.py
    session_state_adapter.py
    system_clock_adapter.py
  service/
    event_emitter.py
    expression_resolver.py
    projection_renderer.py
    temporal_service.py
    timezone_resolver.py
    window_builder.py
  kernel/
    bootstrap.py
    handle.py
  resolver.py
  windows.py
  recurrence.py
  freshness.py
  policy.py
  tests/
```

### Temporal Responsibilities

`k1.temporal` should own:

1. Current UTC instant.
2. Current local instant.
3. Active timezone.
4. Local date.
5. Local day of week.
6. Time of day bucket.
7. Weekend/weekday flag.
8. Today/tomorrow/yesterday windows.
9. Week/month boundaries.
10. Relative expression resolution.
11. Recurrence interpretation helpers.
12. Freshness and staleness checks.
13. Provenance of time source.
14. Consumer-specific prompt rendering.
15. Safe deterministic inputs for tools.

### Temporal Inputs

Potential inputs:

| Input | Source | Trust level | Notes |
| --- | --- | --- | --- |
| System clock | OS/runtime | High | Base monotonic wall clock. |
| Device timezone | device metadata | High if available | Better than persona preference. |
| Persona timezone | Persona prefs | Medium | Current fallback. |
| Spatial timezone | Spatial place | Medium/high | Derived from known place. |
| User utterance | current turn | Low as fact, high as expression source | "tomorrow", "after school", "next weekend". |
| Calendar locale | calendar provider | Medium | Useful for week start conventions. |
| Family routines | SelfModel/rhythm | Medium | "after school", "bedtime", "dinner". |

### Temporal Anchor Type

Initial type sketch:

```python
@dataclass(frozen=True)
class TemporalAnchor:
    anchor_id: str
    captured_at_utc: str
    now_utc: str
    now_local: str
    timezone: str
    timezone_source: str
    local_date: str
    local_time: str
    day_of_week: str
    hour_24: int
    time_of_day: str
    is_weekend: bool
    locale: str | None
    week_start_day: str
    freshness_ms: int
    source: str
    confidence: float
```

### Temporal Windows Type

```python
@dataclass(frozen=True)
class TemporalWindow:
    label: str
    start_local: str
    end_local: str
    start_utc: str
    end_utc: str
    timezone: str
    granularity: Literal["instant", "day", "week", "month", "custom"]
    inclusive_start: bool = True
    exclusive_end: bool = True
```

Standard windows to compute every turn:

- `yesterday`
- `today`
- `tomorrow`
- `this_week`
- `next_week`
- `this_weekend`
- `next_weekend`
- `this_month`
- `next_month`

### Resolved Temporal Expression Type

```python
@dataclass(frozen=True)
class ResolvedTemporalExpression:
    raw_text: str
    normalized_label: str
    resolution_kind: Literal["instant", "window", "recurrence", "ambiguous"]
    window: TemporalWindow | None
    instant_local: str | None
    recurrence_rule: str | None
    confidence: float
    needs_clarification: bool
    clarification_reason: str | None
```

Examples:

| Raw expression | Resolution |
| --- | --- |
| `tomorrow` | local tomorrow day window |
| `next Monday` | next Monday local day window |
| `this weekend` | Saturday/Sunday local window, locale-aware |
| `after school` | routine-backed window or ambiguous |
| `tonight` | local evening/night window |
| `in two weeks` | relative date or range depending intent |
| `by Friday` | deadline window ending Friday |

### Temporal Section In SessionState

New HOT section candidate:

```text
TemporalSection
  anchor: TemporalAnchor
  windows: dict[str, TemporalWindow]
  resolved_expressions: list[ResolvedTemporalExpression]
  last_turn_id: str
  stale_after_ms: int
  provenance: list[TemporalSource]
```

Why HOT:

- Every prompt and task depends on it.
- It should not be evicted during active sessions.
- It must be cheap to read.

Migration from current state:

1. Keep `control.get_temporal_anchor()` for compatibility.
2. Introduce `TemporalSection` as the new canonical section.
3. Make `control.temporal_anchor` a mirror or pointer during transition.
4. Change prompt `SECTION_SOURCE_MAP["temporal_context"]` from `control` to `temporal`.
5. Deprecate direct imports from `k1/sessionstate/sections/temporal_context.py`.

### Temporal Port

```python
class ITemporalPort(Protocol):
    async def get_anchor(self, session_id: str) -> TemporalAnchor: ...
    async def get_windows(self, session_id: str) -> Mapping[str, TemporalWindow]: ...
    async def resolve_expression(
        self,
        session_id: str,
        text: str,
        *,
        intent: str | None = None,
        member_id: str | None = None,
    ) -> ResolvedTemporalExpression: ...
    async def build_prompt_block(
        self,
        session_id: str,
        scope: str,
    ) -> str: ...
```

### Temporal Handle Lifecycle

```text
Kernel startup:
  build TemporalBundle

Session create:
  build TemporalHandle(session_id, ssm, clock, timezone_provider)
  compute initial anchor
  install TemporalSection into SSM
  attach handle to session and ConciergeRuntime

Each user turn:
  refresh anchor if stale or turn begins
  resolve temporal expressions from current user text
  write anchor/windows/resolutions into TemporalSection

Back task dispatch:
  copy anchor ID and relevant windows into TaskDispatch reference_context or context_snapshot

Session destroy:
  uninstall handle
```

### Temporal Prompt Blocks

Front compact block:

```text
== NOW ==
Local: Mon May 18, 2026 10:15 AM America/Chicago
Today: 2026-05-18
Tomorrow: 2026-05-19
Freshness: live
```

Back execution block:

```text
== EXECUTION TIME CONTEXT ==
Anchor ID: temp_...
Now UTC: 2026-05-18T15:15:00Z
Local now: 2026-05-18T10:15:00-05:00
Timezone: America/Chicago
Today window: 2026-05-18T00:00:00-05:00 to 2026-05-19T00:00:00-05:00
Tomorrow window: 2026-05-19T00:00:00-05:00 to 2026-05-20T00:00:00-05:00
Resolved task dates: tomorrow -> 2026-05-19
```

Planner constraint object:

```json
{
  "temporal": {
    "anchor_id": "temp_...",
    "now_utc": "2026-05-18T15:15:00Z",
    "timezone": "America/Chicago",
    "today": {"start": "...", "end": "..."},
    "tomorrow": {"start": "...", "end": "..."},
    "resolved_expressions": []
  }
}
```

## Proposed `k1.spatial` Module

### Spatial Package Sketch

```text
k1/spatial/
  __init__.py
  config.py
  types.py
  events.py
  factory.py
  ports/
    device_place_port.py
    event_port.py
    geocoder_port.py
    place_registry_port.py
    policy_port.py
    presence_port.py
    state_port.py
  adapters/
    event_bus_adapter.py
    local_place_registry_adapter.py
    null_device_place_adapter.py
    null_presence_adapter.py
    selfmodel_policy_adapter.py
    session_state_adapter.py
  service/
    device_surface_resolver.py
    event_emitter.py
    place_resolver.py
    presence_resolver.py
    privacy_projector.py
    projection_renderer.py
    spatial_service.py
  kernel/
    bootstrap.py
    handle.py
  places.py
  geofence.py
  presence.py
  privacy.py
  resolver.py
  tests/
```

### Spatial Responsibilities

`k1.spatial` should own:

1. Active device/surface location if available.
2. Active member semantic place if available.
3. Household place registry.
4. Home/work/school/frequent place mapping.
5. Geofence membership.
6. Co-presence and member presence, if allowed.
7. Device surface classification: personal phone, shared hub, car, desktop, watch, unknown.
8. Place confidence and freshness.
9. Privacy filtering for location exposure.
10. Spatial references from user utterances.
11. Tool-safe place IDs and coordinates when policy allows.
12. Prompt-safe semantic place summaries.

### Spatial Inputs

Potential inputs:

| Input | Source | Trust level | Notes |
| --- | --- | --- | --- |
| Device GPS | device provider | High but sensitive | Should be policy-gated. |
| IP geolocation | web/session | Low/medium | Approximate only. |
| Home registry | Family settings / SelfModel | High | Durable household places. |
| Calendar event locations | calendar provider | Medium | Future/past places, not current location. |
| User utterance | current turn | Low as fact | Mentioned places. |
| Wi-Fi / beacon | local device | Medium/high | Useful for home room inference if available. |
| Presence signals | family devices | Sensitive | Needs constitution/privacy rules. |
| Manual check-in | user action | High | "I am at school" type claims. |

### Spatial Place Type

```python
@dataclass(frozen=True)
class PlaceRef:
    place_id: str
    label: str
    kind: Literal["home", "work", "school", "store", "vehicle", "room", "region", "unknown"]
    semantic_name: str
    address_redacted: str | None
    timezone: str | None
    geofence_id: str | None
    confidence: float
    source: str
```

### Location Fix Type

```python
@dataclass(frozen=True)
class LocationFix:
    fix_id: str
    captured_at_utc: str
    latitude: float | None
    longitude: float | None
    accuracy_meters: float | None
    altitude_meters: float | None
    source: str
    confidence: float
    privacy_class: Literal["raw", "approximate", "semantic", "hidden"]
```

### Spatial Context Type

```python
@dataclass(frozen=True)
class SpatialContext:
    context_id: str
    captured_at_utc: str
    active_member_id: str | None
    active_device_id: str | None
    surface_kind: str
    semantic_place: PlaceRef | None
    raw_location: LocationFix | None
    approximate_region: str | None
    geofence_memberships: list[str]
    co_present_member_ids: list[str]
    mentioned_places: list[PlaceRef]
    freshness_ms: int
    confidence: float
    redactions: list[str]
```

### Spatial Section In SessionState

New HOT/WARM split candidate:

```text
SpatialSection (HOT projection)
  current: SpatialContext
  active_place: PlaceRef | None
  active_device_surface: str
  co_presence_summary: list[PresenceRef]
  mentioned_places_this_turn: list[PlaceRef]
  freshness
  redactions

PlaceRegistrySection (WARM durable projection)
  household_places: dict[place_id, PlaceRef]
  geofences: dict[geofence_id, Geofence]
  member_default_places: dict[member_id, list[place_id]]
```

Alternative:

- Keep one `spatial` section initially.
- Split registry later when persistence and sync are clearer.

### Spatial Port

```python
class ISpatialPort(Protocol):
    async def get_context(self, session_id: str) -> SpatialContext: ...
    async def resolve_place(
        self,
        session_id: str,
        text: str,
        *,
        member_id: str | None = None,
    ) -> PlaceRef | None: ...
    async def get_prompt_projection(
        self,
        session_id: str,
        scope: str,
    ) -> str: ...
    async def get_tool_projection(
        self,
        session_id: str,
        capability_name: str,
    ) -> Mapping[str, Any]: ...
```

### Spatial Privacy Levels

Spatial data should be projected by privacy level.

| Level | Example | Allowed consumers |
| --- | --- | --- |
| Hidden | no location exposed | Default for sensitive child/member states. |
| Semantic | "at home", "near school" | Front prompt, Back prompt, Planner prompt. |
| Approximate | city/region or coarse geohash | Weather, broad recommendations. |
| Place ID | internal `place_home_123` | Tools and Planner when place registry is needed. |
| Raw coordinates | lat/lon with accuracy | Only deterministic tools that require it and policy allows. |

Prompt should usually receive semantic or approximate projections, not raw coordinates.

### Spatial Prompt Blocks

Front compact block:

```text
== PLACE ==
Surface: shared home hub
Active place: home
Location precision: semantic
Freshness: live
```

Back execution block:

```text
== EXECUTION PLACE CONTEXT ==
Spatial context ID: spatial_...
Active member: Jordan
Surface: personal device
Semantic place: home
Relevant places: home, Jordan school, grocery store candidates
Location precision: semantic
Raw coordinates: not available to this actor
```

Planner constraint object:

```json
{
  "spatial": {
    "context_id": "spatial_...",
    "surface_kind": "shared_home_hub",
    "semantic_place": "home",
    "relevant_place_ids": ["place_home", "place_school_jordan"],
    "location_precision": "semantic",
    "co_presence": []
  }
}
```

## Canonical Grounding Envelope

### Envelope Type Sketch

```python
@dataclass(frozen=True)
class GroundingEnvelope:
    envelope_id: str
    session_id: str
    turn_id: str | None
    trace_id: str | None
    created_at_utc: str
    consumer: Literal["front", "back", "planner", "fabric", "agent", "tool", "memory"]
    identity_ref: str | None
    temporal: TemporalProjection
    spatial: SpatialProjection
    household_refs: list[str]
    device_surface: str | None
    policy_scope: str
    freshness: GroundingFreshness
    provenance: list[GroundingSource]
    redactions: list[str]
```

### Projections By Consumer

| Consumer | Temporal projection | Spatial projection | Notes |
| --- | --- | --- | --- |
| Front | compact human-readable plus today/tomorrow | semantic place only | Best for conversational grounding. |
| Back | execution block plus ISO windows | semantic/place IDs, raw only if needed | Best for tool calls. |
| Planner | typed constraints | typed constraints | Should be mandatory. |
| Fabric tool | contract-declared section | contract-declared precision | Deterministic and auditable. |
| Spawned agent | scoped lease | scoped lease | TTL-bound and privacy-filtered. |
| Memory writer | provenance and place/time tags | semantic/place IDs | Useful for K0 memory atoms. |

### Envelope Rules

1. The envelope is created once per turn and can be refreshed for long-running tasks.
2. Envelopes must include IDs for temporal/spatial source versions.
3. Consumers receive projections, not necessarily raw source objects.
4. Redactions are explicit.
5. Tools that require precision declare it in contracts.
6. Prompt renderers consume envelope projections, not random SessionState fields.

## AI Agent Ambient Intelligence Contract

This is the important design question: what should spawned AI agents receive?

Decision: every spawned agent receives a spatial projection object. The object may explicitly say `unknown`, `hidden`, `unavailable`, or `stale`, but omission is not allowed because omission recreates spatial blindness.

Recommended default for spawned agents:

```text
AgentGroundingLease
  lease_id
  issued_at_utc
  expires_at_utc
  temporal_anchor
  common_windows
  semantic_place
  relevant_place_refs
  active_member_ref
  household_role_refs
  task_scope
  privacy_scope
  allowed_context_sections
  denied_context_sections
  redactions
```

Agents should get:

- current local and UTC time
- timezone
- today/tomorrow windows
- task-specific resolved expressions
- semantic place
- relevant place IDs if needed
- active member ref
- household relationship summary if allowed
- freshness and confidence
- privacy boundary
- allowed and denied context sections

Agents should not get by default:

- raw GPS
- full family location history
- unrelated member locations
- private child presence details
- all place registry entries
- unrestricted K0 memory access
- hidden household constitution details not relevant to task

Agent contracts should declare:

```yaml
required_context:
  - temporal
  - spatial
optional_context:
  - self_model
context_precision:
  temporal: execution
  spatial: semantic
lease:
  ttl_seconds: 900
  allow_refresh: true
```

## Integration Plan By Subsystem

### Kernel Service

File: `k1/kernel/service.py`

Add Tier 1 fields:

```python
self._temporal_bundle: TemporalBundle | None = None
self._spatial_bundle: SpatialBundle | None = None
```

Startup ordering:

```text
S2.5 HIL
S2.6 SelfModel
S2.7 Temporal
S2.8 Spatial
S3 Fabric
```

Reasoning:

- Temporal/spatial may need HIL or SelfModel policy.
- Fabric should start after these modules so context section allowlists and providers can be wired.
- Concierge must start after per-session handles are installed.

Session creation ordering:

```text
P1 SessionState
P2 IO/model/session adapters
P3 Fabric session resources
P3.5 SelfModel handle
P3.6 Temporal handle
P3.7 Spatial handle
P4 Concierge
```

Destroy ordering:

1. Stop Concierge.
2. Uninstall Spatial handle.
3. Uninstall Temporal handle.
4. Uninstall SelfModel handle.
5. Tear down Fabric/session resources.
6. Close SessionState.

Alternative teardown:

- Uninstall handles before stopping Concierge only if handles emit callbacks into Concierge. Otherwise stop Concierge first to stop active reads.

### Concierge Factory / Runtime

Files:

- `k1/concierge/factory.py`
- `k1/concierge/session.py`

Add optional ports or handles:

```python
temporal_port: ITemporalPort | None = None
spatial_port: ISpatialPort | None = None
```

Runtime fields:

```python
self._temporal = temporal_port
self._spatial = spatial_port
```

Use cases:

- Front prompt builder receives grounding envelope.
- Back dispatch receives execution envelope.
- FSM writes current turn temporal/spatial context.
- ToolContext can expose scoped temporal/spatial helpers.

### SessionState Sections

Files:

- `k1/sessionstate/sections/temporal.py`
- `k1/sessionstate/sections/spatial.py`
- `k1/sessionstate/sections/place_registry.py`
- `k1/sessionstate/sections/grounding.py`
- `k1/sessionstate/sections/__init__.py`
- `k1/sessionstate/sections/control.py`

Recommended sections:

```text
temporal        HOT, never evict during active session
spatial         HOT projection, policy-filtered current context
place_registry  WARM, durable household places and geofence contracts
grounding       HOT, lightweight envelope/projection IDs and redaction summary
```

Transition plan:

1. Introduce `temporal` section.
2. Continue writing `control.temporal_anchor` for compatibility.
3. Introduce lightweight `grounding` section with latest envelope IDs, projection IDs, source section versions, and redaction summaries.
4. Update Front builder source map.
5. Update Back snapshot reader.
6. Add `spatial` section with policy-filtered current projection: semantic place, precision, freshness, provenance, redactions, place IDs when registered, raw-location availability state, and unknown-safe fallback.
7. Define `place_registry` contract from day one; backing storage may start local/session-scoped, but the section contract is not deferred.

### Concierge Front

Files:

- `k1/concierge/actors/front.py`
- `k1/concierge/prompt/builder.py`
- `k1/concierge/prompt/sections.py`
- `k1/concierge/prompt/scenario_templates.py`

Changes:

1. Replace hardcoded location with spatial projection.
2. Change `SECTION_SOURCE_MAP["temporal_context"]` from `control` to `temporal`.
3. Add `spatial_context` read config.
4. Add spatial renderers:
   - `_render_spatial_context_full`
   - `_render_spatial_context_slim`
5. Add promoted `== PLACE ==` or `== GROUNDING ==` block.
6. Keep SelfModel capsule for identity/family/social graph.
7. Use Spatial module for physical/semantic place.
8. Resolve simple temporal expressions before dispatch.
9. Put resolved expressions into `reference_context`.
10. Render prompt grounding from `GroundingProjection`, not raw section dictionaries.

Example dispatch reference context:

```json
{
  "resolved_temporal": {
    "tomorrow": {
      "label": "tomorrow",
      "start_local": "2026-05-19T00:00:00-05:00",
      "end_local": "2026-05-20T00:00:00-05:00",
      "timezone": "America/Chicago"
    }
  },
  "spatial": {
    "semantic_place": "home",
    "precision": "semantic"
  }
}
```

### Concierge Back

Files:

- `k1/concierge/actors/back.py`
- `k1/concierge/prompt/back_prompt.py`

Changes:

1. `_read_ss_snapshot()` reads `temporal` and `spatial` sections.
2. Back prompt receives `temporal_context` and `spatial_context` strings or typed dicts.
3. `build_back_prompt()` includes execution context block.
4. ReAct loop has access to resolved temporal windows before tools.
5. Back avoids `date_calc` for simple today/tomorrow.
6. Back uses `date_calc` only for arithmetic beyond the anchor window map.

Back prompt addition:

```text
== EXECUTION GROUNDING ==
Current local time: ...
Timezone: ...
Today: ...
Tomorrow: ...
Active place: ...
Location precision: ...
Redactions: ...
```

Back tool policy:

- Calendar read should receive ISO windows.
- Reminder create should receive local datetime and timezone.
- Shopping/location tools may receive semantic place or place ID.
- Travel tools may request raw coordinates through policy gate.

### FSM Controller

File: `k1/concierge/fsm/controller.py`

Current behavior:

- Computes temporal anchor using persona timezone.
- Writes anchor into control.

Future behavior:

1. Ask TemporalHandle to refresh anchor.
2. Ask TemporalHandle to resolve expressions in user text.
3. Ask SpatialHandle for active context projection.
4. Write both sections before Front prompt build.
5. Stamp turn with grounding envelope ID.
6. Pass envelope ID through task dispatch.

### Task Dispatch

File: `k1/concierge/task/dispatch.py`

Add fields or structured entries:

```python
grounding_envelope_id: str | None = None
temporal_anchor_id: str | None = None
spatial_context_id: str | None = None
resolved_temporal_refs: dict[str, Any] | None = None
resolved_spatial_refs: dict[str, Any] | None = None
```

Alternative:

- Keep dataclass unchanged initially and populate `reference_context["grounding"]`.
- Move to typed fields once stable.

Recommended sequence:

1. Use `reference_context["grounding"]` as a compatibility migration.
2. Add typed fields after tests prove behavior.

### Planner

Files:

- `k1/planner/stages/sketch_service.py`
- `k1/planner/stages/expand_service.py`
- `k1/planner/services/tool_call_router.py`

Changes:

1. Always inject `constraints["temporal"]`.
2. Always inject `constraints["spatial"]`, even if unknown.
3. Keep `query_session_context`, but do not rely on it for critical grounding.
4. Teach prompt stages to respect typed date windows.
5. Include envelope IDs in plan metadata.

Planner should see unknown explicitly:

```json
{
  "spatial": {
    "status": "unknown",
    "reason": "no permitted location signal",
    "precision": "hidden"
  }
}
```

### Orchestrator

Files:

- `k1/orchestrator/types.py`
- `k1/orchestrator/orchestration/orchestrator_service.py`

Changes:

1. Add typed grounding field to `PlanRequest`.
2. Add typed grounding field to `TaskEnvelope`.
3. Preserve grounding IDs in logs/events.
4. Pass constraints to Planner consistently.

Type sketch:

```python
@dataclass(frozen=True)
class PlanRequest:
    intent: Any
    trace_id: str
    context: dict[str, Any]
    constraints: dict[str, Any]
    grounding: GroundingEnvelope | None = None
```

### Fabric ContextBuilder

File: `k1/fabric/core/context_builder.py`

Changes:

1. Allow contracts to declare `temporal` and `spatial` sections.
2. Add baseline invocation timestamp to `context_override` for all calls.
3. Provide baseline grounding invocation metadata for all calls.
4. Do not inject raw spatial data automatically.
5. Respect contract precision requirements.
6. LLM-backed capabilities may receive a typed temporal projection and unknown-safe spatial projection when their contract opts into baseline grounding.

Baseline universal context override:

```json
{
  "grounding_invocation": {
    "invoked_at_utc": "...",
    "temporal_anchor_id": "...",
    "spatial_context_id": "..."
  }
}
```

### Tool Contracts

Files:

- `k1/contracts/tools/date_calc.yaml`
- `k1/contracts/tools/build_agent.yaml`
- calendar/reminder/task/shopping contracts

Changes:

`date_calc.yaml`:

```yaml
required_context:
  - temporal
```

Calendar read:

```yaml
required_context:
  - temporal
optional_context:
  - spatial
```

Reminder create:

```yaml
required_context:
  - temporal
optional_context:
  - spatial
  - self_model
```

Build agent:

```yaml
required_context:
  - temporal
  - spatial
  - beliefs_active
  - interaction_history
  - task_context
optional_context:
  - active_plans
  - pending_clarifications
```

### Memory / K0 Writeback

Relevant schemas:

- memory atoms already have time and spatial concepts.
- `origin_place_id` and `spatial[]` fields exist in memory schemas.

Changes:

1. Memory writes should include temporal anchor ID.
2. Memory writes should include semantic place ID when relevant.
3. Raw location should not be written unless explicit policy allows it for a dedicated use case.
4. K0 recall should be able to query by temporal and spatial facets.

Example memory metadata:

```json
{
  "temporal": {
    "anchor_id": "temp_...",
    "event_local_date": "2026-05-18",
    "timezone": "America/Chicago"
  },
  "spatial": {
    "origin_place_id": "place_home",
    "precision": "semantic"
  }
}
```

## Deprecation Plan

### Deprecate POC Temporal Utility As Source Of Truth

Current:

- `k1/sessionstate/sections/temporal_context.py`
- `compute_temporal_anchor(tz_name)`

Future:

- Move computation into `k1.temporal.resolver`.
- Keep compatibility import temporarily.
- Add deprecation note.

### Deprecate Hardcoded Location

Current:

- Front temporal renderer hardcodes `Location: Denton, Texas`.

Future:

- Spatial projection owns location rendering.
- If unknown, render `Location: unknown` or omit location.

### Deprecate `temporal_context -> control` Mapping

Current:

- `SECTION_SOURCE_MAP["temporal_context"] = "control"`

Future:

- `SECTION_SOURCE_MAP["temporal_context"] = "temporal"`

### Deprecate Prompt-Only Grounding

Current:

- Front prompt sees time.
- Back/Planner/Fabric may not.

Future:

- Grounding envelope is generated before prompt build and task dispatch.
- Every consumer receives projection appropriate to its scope.

### Deprecate Freeform Relative Dates In Back Dispatch

Current:

- `reference_context` may contain raw `tomorrow`.

Future:

- Dispatch includes resolved date windows.
- Raw phrase can be kept for audit, but tools use resolved windows.

## Privacy And Policy Model

### Location Privacy Principles

1. Semantic place is safer than raw coordinates.
2. Approximate place is safer than exact address.
3. Child/member location is sensitive by default.
4. Co-presence is sensitive because it reveals multiple people.
5. Location history is more sensitive than current semantic state.
6. Tool access should be least-privilege and contract-declared.
7. Prompt access should be redacted by default.

### Spatial Policy Examples

| Scenario | Front prompt | Back/tool | Notes |
| --- | --- | --- | --- |
| Weather at current place | city/region | approximate location | Raw GPS not needed. |
| Find nearby store | semantic/current region | coordinates if allowed | Tool may need coordinates. |
| Child at school | maybe "Jordan is at school" if allowed | place ID only | Parent/child policy applies. |
| Shared hub unknown speaker | no private location | none | Need identity first. |
| Emergency workflow | escalated precision | raw if approved/allowed | Requires explicit policy. |

### Temporal Policy Examples

Temporal is less sensitive than spatial but can still reveal routines.

| Data | Sensitivity | Notes |
| --- | --- | --- |
| current date/time | low | Generally safe. |
| timezone | low/medium | Can imply region. |
| routines like bedtime/school | medium | Child/family privacy. |
| calendar-derived availability | medium/high | Should be scoped. |
| historical movement/routine pattern | high | Should not leak to generic prompts. |

## Observability And Debugging

Add structured logs/events:

```text
temporal.anchor.created
temporal.expression.resolved
temporal.anchor.stale
spatial.context.created
spatial.context.redacted
grounding.envelope.created
grounding.projection.rendered
grounding.projection.denied
```

Log fields:

- `session_id`
- `turn_id`
- `trace_id`
- `anchor_id`
- `spatial_context_id`
- `consumer`
- `precision`
- `redaction_count`
- `freshness_ms`
- `source`
- `confidence`

Do not log raw coordinates unless debug mode explicitly allows it and logs are protected.

Session State UI should show:

- temporal anchor
- windows
- resolved expressions
- spatial semantic place
- precision level
- redactions
- freshness
- source/provenance

## Test Strategy

Important constraint:

- Do not run the full `tests/k1/kernel/` suite.
- Do not run full Fabric suite unsolicited.
- Use focused tests only.

### Unit Tests

Temporal:

- compute anchor from timezone
- compute today/tomorrow windows
- resolve `tomorrow`
- resolve `next Monday`
- mark ambiguous expressions
- stale anchor detection
- DST boundary cases
- timezone fallback order

Spatial:

- semantic projection from known place
- raw coordinate redaction
- geofence match
- unknown location projection
- privacy level filtering
- co-presence redaction
- mentioned place vs current place distinction

### Integration Tests

Concierge Front:

- prompt contains NOW from temporal section
- prompt no longer hardcodes Denton
- spatial block appears when section exists
- unknown spatial renders safely

Concierge Back:

- Back prompt contains execution grounding
- Back receives resolved tomorrow window
- Back does not call date_calc for simple tomorrow when resolved window present

Planner:

- PlanRequest includes temporal constraints
- PlanRequest includes spatial unknown object when location unavailable

Fabric:

- ContextBuilder injects `temporal` when contract declares it
- `date_calc` receives temporal section
- spawned agent default context includes temporal and an explicit spatial projection object

### Golden Scenarios

1. "What does Jordan have tomorrow?"
2. "Remind me after school to pack cleats."
3. "Find a grocery pickup time after soccer."
4. "What is nearby for dinner?"
5. "Can you add that to Dad's calendar next Monday?"
6. Shared hub: "Remind me when I get home."
7. Unknown speaker asks for private child location.
8. Agent spawned to plan weekend errands.

## Implementation Phases

### Phase 0: Design Lock

Deliverables:

1. Approve this whiteboard direction.
2. Lock canonical section names: `temporal`, `spatial`, `place_registry`, and `grounding`.
3. Lock `k1.grounding` as the package that owns `GroundingEnvelope`, `GroundingProjection`, `AgentGroundingLease`, and the shared `DeviceContextSnapshot` dataclass.
4. Lock `k1/kernel/ports/device_context_port.py` as the producer/reader Protocol for installed-device snapshots.
5. Lock `SpatialSection` and `PlaceRegistrySection` as separate contracts from day one.
6. Lock control mirror behavior: `control.temporal_anchor` stays temporarily but is not source of truth.
7. Lock implementation order: temporal foundation, grounding shell, relative-date dispatch propagation, spatial foundation, Fabric/agents, place registry/geofences, K0 memory integration.

### Phase 1: Temporal Kernel Foundation

Goal:

- Build the production-grade temporal kernel service and remove temporal blindness across Front, Back, Planner, Fabric, spawned agents, and memory writeback.

Tasks:

1. Add `TemporalSection`.
2. Add `k1.temporal` package with factory, ports, adapters, service, kernel bundle, and per-session handle.
3. Add installed-device context ingestion through shared `DeviceContextSnapshot`: device timezone, locale, observed timestamp, surface, installation ID, and clock-skew metadata.
4. Compute authoritative anchor, today/tomorrow/week/month windows, freshness, confidence, and provenance.
5. Resolve common relative expressions deterministically through typed candidates, tokens, phrase catalogs, routine registries, and explicit rule classes.
6. Write temporal section at turn start and refresh long-running task anchors by TTL.
7. Keep control mirror for compatibility.
8. Front reads temporal projection.
9. Back reads execution temporal projection.
10. Planner receives typed temporal constraints.
11. Fabric contracts can request temporal context.
12. Spawned agents receive temporal lease data by default.
13. Memory writes carry temporal anchor metadata.
14. Add focused tests for boundaries, DST, stale anchors, and dispatch propagation.

### Phase 1.5: Grounding Shell And Propagation

Goal:

- Create the production grounding envelope path immediately after temporal so temporal is not wired directly into every subsystem in a way that must be undone when spatial lands.

Tasks:

1. Add `GroundingSection` as a lightweight HOT section with envelope IDs, projection IDs, source section versions, and redaction summaries.
2. Add `k1.grounding` package with types, factory, ports, adapters, service, kernel bundle, and per-session handle.
3. Define shared `DeviceContextSnapshot` dataclass in `k1.grounding.types`.
4. Add `k1/kernel/ports/grounding_port.py` and `k1/kernel/ports/device_context_port.py`.
5. Build Front, Back, Planner, Fabric, Agent, Tool, and Memory projection request/response types.
6. Add `GroundingProjection` prompt block rendering path for Concierge without raw section reads.
7. Add compatibility builders for `reference_context` and `context_snapshot` while typed fields migrate.
8. Add envelope ID propagation through Front -> Back -> Planner/Fabric/Agent metadata.
9. Add focused grounding tests for envelope creation, projection policy, agent lease, and propagation.

### Phase 2: Resolve Relative Dates Before Dispatch

Goal:

- Stop Back from needing date_calc for simple relative dates.

Tasks:

1. Extract temporal expressions from user text or task params.
2. Resolve common expressions.
3. Put resolved windows into typed dispatch fields and mirror into `reference_context` only for compatibility.
4. Teach Back to prefer resolved windows.
5. Keep raw text for audit.
6. Add golden tests around `tomorrow` and `next Monday`.

### Phase 3: Spatial Kernel Foundation

Goal:

- Build the production-grade spatial kernel service with installed-device context, place contracts, privacy projection, and unknown-safe behavior across all AI surfaces.

Tasks:

1. Add `SpatialSection`.
2. Add `k1.spatial` package with factory, ports, adapters, service, kernel bundle, and per-session handle.
3. Ingest installed-device context through shared `DeviceContextSnapshot`: active device surface, installation ID, location permission state, optional location fix, optional semantic place hint, and observed timestamp.
4. Add full projection model: hidden, semantic, approximate, place ID, and policy-gated raw coordinates.
5. Add place registry contract and unknown-safe registry state.
6. Add privacy projector and redaction metadata from day one.
7. Replace hardcoded Denton.
8. Add Front spatial block.
9. Add Back spatial execution block.
10. Add Planner spatial constraints with unknown-safe default.
11. Fabric contracts can request spatial context by precision.
12. Spawned agents receive required spatial projection objects with redactions, even when the state is unknown, hidden, unavailable, or stale.
13. Add focused tests for missing permissions, stale location, redaction, place resolution, and prompt non-leakage.

### Phase 4: Fabric And Agents

Goal:

- Make temporal/spatial available through contracts.

Tasks:

1. Add `temporal` and `spatial` to allowed context sections.
2. Update `date_calc.yaml` to require temporal.
3. Update `build_agent.yaml` to require temporal and a spatial projection object.
4. Add baseline grounding invocation override.
5. Add spawned agent lease object.
6. Add focused Fabric tests only.

### Phase 5: Place Registry And Geofences

Goal:

- Move beyond semantic unknown/home to real household places.

Tasks:

1. Add place registry.
2. Add home/school/work place refs.
3. Add geofence matching.
4. Add timezone derivation from place.
5. Add travel/proximity support for planner.
6. Add privacy policy gates.

### Phase 6: K0 Memory Integration

Goal:

- Make memory time/place aware without overexposing location.

Tasks:

1. Add temporal anchor metadata to memory writes.
2. Add semantic place metadata to memory writes.
3. Populate `origin_place_id` where relevant.
4. Query recall by temporal/spatial facets.
5. Keep raw location out of memory by default unless a dedicated policy-approved use case explicitly allows it.

## Resolved Architecture Decisions

| Decision | Resolution | Implementation consequence |
| --- | --- | --- |
| Section names | Use `temporal`, `spatial`, `place_registry`, and `grounding`. | Prompt labels can keep `temporal_context` or `spatial_context`, but system sections use canonical names. |
| Grounding package | Use `k1.grounding`. | Kernel wires grounding; Concierge, Planner, Fabric, agents, tools, and memory consume its projections without importing kernel internals. |
| Device context ownership | Pure `DeviceContextSnapshot` dataclass lives in `k1.grounding.types`; producer Protocol lives in `k1/kernel/ports/device_context_port.py`. | Temporal and spatial consume the same installed-device observation shape. |
| Grounding SessionState section | Add lightweight HOT `grounding` section from day one. | Store envelope IDs, projection IDs, source section versions, and redaction summaries; no raw location payload. |
| Control mirror | Keep `control.temporal_anchor` temporarily. | `TemporalSection` is source of truth; control mirror exists only for migration compatibility. |
| Spatial split | Define `SpatialSection` and `PlaceRegistrySection` immediately. | `spatial` is HOT current context; `place_registry` is WARM durable household place contract. |
| Raw GPS support | Add interface and policy gate now; source availability may be unavailable. | Raw coordinates remain contract-gated and redacted by default. |
| Agent default spatial | Spatial projection object is required. | It may explicitly say unknown, hidden, unavailable, or stale; it must not be omitted. |
| Planner context | Typed grounding field is the target. | Mirror temporal/spatial into constraints only during migration. |
| Timezone source order | Device -> spatial place -> persona -> UTC. | UTC is safe mode, not a silent default. |
| Expression resolution | No regular-expression-driven core resolver. | Use typed candidates, token objects, curated catalogs, registries, state machines, and explicit rule classes. |
| Implementation order | Temporal, grounding shell, dispatch propagation, spatial, Fabric/agents, place registry/geofences, K0 memory. | Grounding appears before spatial so temporal propagation does not become direct point-to-point wiring. |
| Prompt rendering ownership | Render from `GroundingProjection`. | Prompt renderers do not read raw temporal/spatial section dictionaries. |
| Raw location in memory | Default is no raw coordinates. | Memory writes store anchor IDs and semantic/place IDs unless a dedicated policy-approved use case allows more. |
| Unknown behavior | Unknown is a valid production state. | Unknown must not block normal assistant behavior and must not be silently guessed. |

## Risks

| Risk | Mitigation |
| --- | --- |
| Prompt bloat | Use compact projections and scope-specific renderers. |
| Privacy leak | Default semantic/hidden spatial projection. Raw coordinates require policy. |
| Double sources of truth | Make TemporalSection/SpatialSection canonical. Keep mirrors temporary. |
| Back still uses raw dates | Add tests proving resolved windows reach Back. |
| Planner ignores constraints | Make prompt and schema explicit; include tests. |
| Fabric contracts drift | Add validator allowlist and contract tests. |
| Long-running task staleness | Envelope TTL and refresh behavior. |
| Unknown location treated as failure | Unknown is valid and should be explicit. |

## Success Criteria

1. Front prompt no longer hardcodes location.
2. Back prompt always includes current time and timezone.
3. Back receives today/tomorrow windows for calendar/reminder tasks.
4. Basic `tomorrow` does not require `date_calc`.
5. Planner always receives temporal constraints.
6. Planner always receives a spatial constraint object, even if unknown.
7. Fabric can inject temporal section by contract.
8. Spawned agents receive temporal grounding by default.
9. Spatial prompt projection is semantic by default.
10. Session State UI can show temporal/spatial payloads.
11. Logs show envelope IDs through Front -> Back -> Planner/Fabric.
12. No raw location appears in prompt dumps by default.
13. `grounding` section shows latest envelope/projection IDs without raw location payload.
14. `DeviceContextSnapshot` is shared by temporal, spatial, and grounding paths.
15. Prompt rendering reads `GroundingProjection`, not raw section dictionaries.
16. Spawned agents always receive a spatial projection object, even when it says unknown, hidden, unavailable, or stale.

## Production V0 Kernel Checklist

Production V0 is the smallest version that is still architecturally complete. It is not a shortcut around kernel ownership, typed contracts, device context, privacy, or cross-surface propagation.

```text
k1.temporal production V0
  package shape: config/types/events/factory/ports/adapters/service/kernel
  TemporalServiceBundle at Tier 1
  TemporalHandle at Tier 2
  shared DeviceContextSnapshot ingestion through kernel device context port
  system UTC + device timezone + locale + clock-skew metadata
  anchor + standard windows + freshness + provenance
  deterministic household expression resolver without regex as core contract
  TemporalSection as canonical HOT section
  control.temporal_anchor compatibility mirror
  Front projection
  Back execution projection
  Planner typed constraints
  Fabric context section
  Agent grounding lease fields
  Memory writeback metadata
  health() + events + focused tests

k1.spatial production V0
  package shape: config/types/events/factory/ports/adapters/service/kernel
  SpatialServiceBundle at Tier 1
  SpatialHandle at Tier 2
  shared DeviceContextSnapshot ingestion through kernel device context port
  device surface + installation ID + permission state
  optional raw location fix with accuracy/freshness/provenance
  semantic/approximate/place-id/raw projection types
  privacy projector and redaction metadata
  place_registry WARM contract, even if registry is empty
  SpatialSection as canonical HOT section
  Front projection
  Back execution projection
  Planner typed constraints
  Fabric context section with precision declaration
  Agent grounding lease fields
  Memory writeback metadata
  health() + events + focused tests

k1.grounding production V0
  package shape: config/types/events/factory/ports/adapters/service/kernel
  GroundingServiceBundle after temporal foundation and before spatial foundation
  GroundingHandle at Tier 2
  shared DeviceContextSnapshot dataclass
  typed GroundingEnvelope from day one
  typed TemporalProjection and SpatialProjection
  consumer-scoped projection methods
  lightweight GroundingSection as canonical HOT metadata section
  envelope IDs carried through Front -> Back -> Planner/Fabric/Agent
  compatibility mirror in reference_context/context_snapshot only where needed
  AgentGroundingLease with required spatial projection object
  explicit unknown/hidden/unavailable/stale states
  no raw location in prompts by default
```

This production V0 should be able to run in a billion-household deployment with different device capabilities. The interfaces stay complete; each deployment reports which inputs are available, hidden, stale, or unavailable.

## Appendix A: Current Specific Gaps From Audit

### Front

- Has temporal anchor.
- Has NOW block.
- Has temporal_context section.
- Location is hardcoded.
- Spatial means mostly household/social graph.
- SelfModel capsule path is good and should be reused.

### Back

- Reads control for safety band only.
- Does not read temporal anchor.
- Does not read spatial context.
- Prompt template has no time/place fields.
- Relative dates burn tool budget.
- Needs execution grounding block.

### Planner / Orchestrator

- Temporal context conditional on constraints or voluntary query.
- Spatial not typed.
- PlanRequest/TaskEnvelope lack grounding field.
- Null state adapter can silently remove grounding.

### Fabric / Agents

- ContextBuilder only injects declared sections.
- date_calc does not require temporal.
- build_agent default context omits temporal/spatial.
- MentionedLocation is conversational, not authoritative.

### Kernel / Session

- Temporal utility is POC.
- No spatial module.
- SelfModel/HIL pattern is right model for lifecycle wiring.
- Install temporal/spatial before Concierge starts.

## Appendix B: Example End-To-End Flow

User asks:

```text
What does Jordan have tomorrow after school?
```

Desired flow:

```text
1. FSM receives user turn.
2. TemporalHandle refreshes anchor.
3. TemporalHandle resolves:
   - tomorrow -> 2026-05-19 day window
   - after school -> Jordan routine window or ambiguous
4. SpatialHandle builds semantic context:
   - active surface: family hub or user's device
   - place: home or unknown
5. GroundingEnvelope is created for Front.
6. Front prompt receives compact NOW/PLACE and SelfModel context.
7. Front determines this is a calendar query for Jordan.
8. If "after school" is known, Front dispatches resolved window.
9. If "after school" is ambiguous, Front asks clarification or dispatches with needs_human depending task.
10. Back receives execution grounding.
11. Back calls calendar tool with ISO start/end.
12. Calendar returns events.
13. Back completes task.
14. Front delivers answer.
15. Memory write includes temporal anchor and semantic place if relevant.
```

Desired Back tool params:

```json
{
  "member_id": "jordan",
  "start": "2026-05-19T15:00:00-05:00",
  "end": "2026-05-19T23:59:59-05:00",
  "timezone": "America/Chicago",
  "source_temporal_anchor_id": "temp_..."
}
```

## Appendix C: First Files To Touch When Implementing

Temporal first:

1. `k1/sessionstate/sections/temporal_context.py`
2. `k1/sessionstate/sections/control.py`
3. `k1/concierge/fsm/controller.py`
4. `k1/concierge/prompt/builder.py`
5. `k1/concierge/actors/back.py`
6. `k1/concierge/prompt/back_prompt.py`
7. `k1/planner/stages/sketch_service.py`
8. `k1/orchestrator/types.py`

Spatial second:

1. `k1/sessionstate/sections/spatial.py`
2. `k1/concierge/prompt/builder.py`
3. `k1/concierge/actors/back.py`
4. `k1/concierge/prompt/back_prompt.py`
5. `k1/planner/stages/sketch_service.py`
6. `k1/orchestrator/types.py`

Fabric/agents after:

1. `k1/fabric/core/context_builder.py`
2. `k1/fabric/providers/agent_provider.py`
3. `k1/contracts/tools/date_calc.yaml`
4. `k1/contracts/tools/build_agent.yaml`

## Appendix D: Naming Candidates

Module names:

- `k1.temporal`
- `k1.spatial`
- `k1.grounding`

Section names:

- `temporal`
- `spatial`
- `place_registry`

Event names:

- `k1.temporal.anchor.created.v1`
- `k1.temporal.expression.resolved.v1`
- `k1.spatial.context.created.v1`
- `k1.spatial.context.redacted.v1`
- `k1.grounding.envelope.created.v1`

Prompt block names:

- `== NOW ==`
- `== PLACE ==`
- `== EXECUTION GROUNDING ==`
- `== PLANNING GROUNDING ==`

## Appendix E: Key Design Sentence

Time and place should become kernel-owned, typed, policy-filtered context services whose projections are consumed by every AI actor and tool path, instead of being scattered prompt strings or LLM guesses.
