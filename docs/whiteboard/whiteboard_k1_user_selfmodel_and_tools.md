# Whiteboard: K1 User Self Model, Family Self Model, Constitution, and Memory-Grounded Tools

Date: 2026-05-03
Status: whiteboard / design exploration
Related architecture:

- `architecture_diagrams/bridge/bridge_architecture.mmd`
- `architecture_diagrams/bridge/interkernel_fabric_layer.mmd`
- `architecture_diagrams/k0/k0_source_of_truth_v2.mmd`
- `architecture_diagrams/k0/p03_consolidation_architecture.mmd`
- `docs/plans/POC_MIGRATION_PLAN.md` M11 — Native Family Tools

## Thesis

Before M11 native family tools are designed as individual CRUD-style MCP servers, K1 needs a native self-model layer.

A family is not one user. It is a mesh of K1 instances:

```text
K1_MOM     <-> K1_DAD
   |             |
   v             v
K1_CHILD_1 <-> K1_CHILD_2 <-> K1_CHILD_3
```

Each installed app has a local K1 kernel that must know:

- Who am I in this family?
- Which family member am I representing right now?
- What is my role, authority, privacy boundary, and relationship graph?
- What family constitution governs my behavior?
- What K0 memories are allowed and useful for this turn?
- What tool actions can I safely take for this person, this family, this device, and this moment?

K0 remains the durable memory/truth layer. K1 needs a local, fast, offline-safe self model that grounds LLM intelligence before recall, planning, orchestration, and tool execution.

The correct direction is:

```text
K1 native self model -> family self model -> constitution/policy -> K0 recall bundle -> LLM plan -> Fabric tools -> K0 memory/writeback
```

Not:

```text
LLM -> arbitrary K0 query -> arbitrary tool call
```

## Why This Matters

If FamilyOS is installed for five members, the same sentence can mean different things depending on local self context.

Example:

```text
User: "Remind me to pack my cleats."
```

On `K1_CHILD_1`, this means:

- actor: child_1
- reminder owner: child_1
- authority: self-level write, AMBER but allowed
- possible memory recall: soccer schedule, school day, routines

On `K1_MOM`, this might mean:

- actor: mom
- ambiguous owner: mom or a child?
- needs clarification unless current conversation establishes the child
- parent authority allows assigning reminder to child

On a shared family hub:

- active user may be unknown
- requires speaker/user identification or confirmation
- should avoid exposing private memories until identity is resolved

Without a K1-native self model, the LLM has no stable ground. K0 may contain memories, but K1 must decide what identity, permissions, relationships, and family rules shape the query and tool action.

## Existing Architecture Signals

The current architecture already points here:

- K1 is self-sufficient and offline-safe.
- K0 is enhancement, long-term memory, graph, consolidation, and sync.
- Bridge handles K1->K0 commands, K1<->K0 queries, K0->K1 SSE, feedback, and offline queueing.
- SessionState already has `MetaSection` with `user_id`, `device_id`, `privacy_band`, anonymous/demo state.
- SessionState already has `PersonaSection`, but persona is currently more response style than identity/authority/social self.
- K0 P03 has social memory, KG entities, KG edges, semantic patterns, procedural memory, and prospective memory.
- Bridge supports query selectors: episodic, semantic, session, device, belief, graph.
- Bridge supports command topics: `memory.write`, `session.snapshot`, `beliefs.archive`, `history.archive`, `plan.committed`, `sync.delta`.
- Bridge supports feedback via `/k0/obs.emit` with `kind=feedback`.

The missing design layer is a K1-native `SelfModel` that binds those pieces together at runtime.

## Grounding in Current Concierge Code

This whiteboard is grounded in the current Concierge architecture and scan artifacts:

- `k1/concierge/concierge_unified.mmd` defines Concierge as K1's user-facing intelligence, with 8 hexagonal ports, two LLM actors, mode-driven prompts, and the single-writer SessionState invariant.
- `k1/concierge/_scan_temp/05_prompt_llm.md` confirms `DynamicPromptBuilder` builds prompts from mode sections, scenario data, domain rules, affect, and SessionState renderers.
- `k1/concierge/_scan_temp/06_tools_react.md` confirms front/back tool schemas are centralized and `ToolDispatcher` has a 7-step dispatch pipeline.
- `k1/concierge/_scan_temp/07_fabric_bus_orchestrator.md` confirms `FabricOrchestratorAdapter` is the tier-routing bridge from Concierge to Fabric/Orchestrator.
- `k1/concierge/_scan_temp/10_ledger_experience_identity_compression.md` confirms the existing Experience/Identity layer and event-sourced ledger are already part of Concierge's lifecycle.

Current concrete hooks:

| Concern | Current hook | Design implication |
| --- | --- | --- |
| Session identity | `MetaSection.SessionIdentity` has `session_id`, `user_id`, `device_id`, `privacy_band`, anonymous/demo flags | `K1SelfModel` should extend or sit beside this; do not duplicate basic identity. |
| Response persona | `PersonaSection` stores style, voice, vocabulary, response preferences | Persona is not self model; it is communication style. Keep it separate. |
| Family hints | `PersonaSection._preferences["family"]` is already used by Concierge family context extraction | `FamilySelfModel` should formalize this into typed structure, not invent an unrelated path. |
| Per-turn identity | OPP-7 `DynamicIdentityContext` / `IdentitySnapshot` | Existing per-turn identity overlay; `K1SelfModel` should be session-scoped and feed it. |
| Prompt injection | `DynamicPromptBuilder.build()` and scenario data templates | Grounding capsule should be rendered here, not scattered in actor code. |
| Memory recall | Front/back `recall_memory` tool via `IMemoryPort` | K0 recall must go through `IMemoryPort`; no direct Bridge calls from prompt/tool code. |
| Tool visibility | `get_tool_allowlist(mode, affect_confidence, tier)` | Add pure self/constitution filtering before schemas are shown to the LLM. |
| Tool execution | `ToolDispatcher` 7-step pipeline | Add a pre-execution policy gate as step 0. |
| Real side effects | Back tools + Fabric/Orchestrator path | Authority/constitution enforcement must apply here, not only in prompts. |
| Safety escalation | HITL / safety band protocol | Constitution RED/AMBER rules should reuse HITL approval instead of creating a parallel approval system. |

Important correction: the self model should usually hydrate at session/runtime start, not from scratch on every turn. Per-turn updates belong to the existing dynamic identity overlay. Shared devices are the exception: if the active person is unknown, each turn may need identity resolution before private recall or sensitive tools.

## The Set Algebra Spine

This section is the design spine. Every later section (concepts, runtime, policy, V0 product design, E0 substrate) is grounded against the algebra here. The spine answers: what *are* the things, what are their intersections, what must never intersect, and what V0 freezes.

### Notation

```text
S = SELF MODEL          -- one per person, per K1 device-binding
F = FAMILY MODEL        -- one per household, derived shared surface
C = CONSTITUTION        -- one per household, signed rule corpus

T = TIME / MOMENT       -- now, recent, historical
D = DEVICE / SURFACE    -- personal K1, shared hub, child K1, guest device
```

Every set is implicitly evaluated at `(T, D)`. There is no static "self model" or "family model" — they are projections at a moment, on a device.

### The Three Base Sets

#### S — Self Model elements (per person)

```text
S.core       = { name, age_band, language, developmental_stage, capabilities }
S.identity   = { role_in_family, declared_relations, responsibilities }
S.pattern    = { routines, preferences, habits, rhythms }
S.context    = { current_activity, co_present, device_in_use }
S.state      = { mood, location, focus, fatigue, presence }
S.consent    = { what_I_allow_family_to_see, what_I_allow_K0_to_see }
S.authority  = { what_I_can_decide_alone, what_I_can_decide_for_others }
S.status     = active | archived | emancipated | memorial | severed
S.external_household_refs = []   -- reserved for V1 multi-household
```

#### F — Family Model elements (derived view)

```text
F.members         = { person_refs }                   -- pointers, not contents
F.relationships   = { (a, b, kind) confirmed }        -- derived from S.declared_relations + C overrides
F.shared_resources= { calendars, devices, spaces, money_pools, pets }
F.joint_routines  = { dinner, school_run, bedtime, weekend }
F.copresence      = { who_is_with_whom_now }          -- device-observed, authoritative
F.care_deps       = { who_depends_on_whom_for_what }
F.hub_state       = { current_tier, who_is_addressing_hub } -- device-observed, authoritative
```

F is **derived** from `( ⋃ S(member) , C )`. It is materialized for query speed but is never authoritative except for the two device-observed slots (`F.copresence`, `F.hub_state`).

#### C — Constitution elements

```text
C.identity_rules    = { who_is_a_member, how_added, how_removed }
C.authority_rules   = { decision_owner_per_domain, escalation_paths }
C.visibility_rules  = { default_projection_per_category }
C.autonomy_rules    = { per_role: { can, must_ask, cannot } }
C.protection_rules  = { child_protections, guest_limits, BLACK_categories }
C.governance        = { how_C_is_amended, signing_quorum }   -- V0: bootstrap-immutable
C.shared_values     = []                                     -- household-declared values
```

### The Six Pairwise Intersections

```text
1. S ∩ S         Inter-Personal       Edges between selves
2. S ∩ F         Shareable Self       Self projected onto family surface
3. S ∩ C         Granted Self         Capabilities, autonomies, protections
4. F ∩ C         Governed Family      Decision ownership, escalation paths
5. S ∩ S ∩ F     Relational Surface   Joint activities between specific members
6. S ∩ C ∩ S     Cross-Person Auth    What I may do that affects another self
```

#### 1. S ∩ S — Inter-Personal

What two selves know about each other, **without going through F**.

```text
S(Alice).declared_relations = { (Bob, "partner") }
S(Bob).declared_relations   = { (Alice, "partner") }
        \                                 /
         \-> consensual edge in F.relationships <-/
```

Asymmetric protected relations (parent → child) are constitution-asserted: only the parent declares; the child's side is auto-implied by C.

#### 2. S ∩ F — Shareable Self

The projection of one self onto the family-visible surface.

```text
family_visible(S, viewer, category) -> projection
```

Governed by `C.visibility_rules` + `S.consent`. F never sees raw S — only what S∩F∩C permits.

#### 3. S ∩ C — Granted Self

What this person is permitted, required, and protected to do.

```text
capabilities(S, C) -> { can_do, must_ask, cannot_do, protections }
```

This is what the dispatcher consults at the policy gate.

#### 4. F ∩ C — Governed Family

Which family-level actions need which authority.

```text
governance(F, C) -> { decision_owner, escalation_path, quorum }
```

#### 5. S ∩ S ∩ F — Relational Surface

Joint activities, co-presence, shared calendars between specific members.

```text
"Alice and Bob's anniversary" lives here, not in F directly.
```

#### 6. S ∩ C ∩ S — Cross-Person Authority

What I am permitted to do **on behalf of, or affecting,** another person.

```text
Parent → child:    approve, restrict, see location
Partner → partner: shared finance authority
Guest → anyone:    almost nothing
```

This is **not** in S∩C alone because it requires the other self to exist.

### The Triple Intersection — SituationFrame

```text
SituationFrame(actor, T, D) = S(actor) ∩ F ∩ C
                              evaluated at (T, D)
                              filtered to the situation kind
```

This is the **only composed object** the runtime ever consumes. The dispatcher gate, the prompt grounding capsule, the LLM Front actor, the tool execution path — all of them see the SituationFrame, not raw S, raw F, or raw C.

```text
        S(actor)                  F                       C
           \                      |                      /
            \                     |                     /
             \                    |                    /
              \--> SituationFrame composer (at T, D) <--/
                            |
                            v
              +-------------------------------+
              | actor:        ProjectedSelf    |
              | context:      L4_L5            |
              | relations:    relevant_subset  |
              | rules:        applicable_C     |
              | capabilities: granted ∧ ctx    |
              | visibility:   what may know    |
              +-------------------------------+
                            |
                            v
                  Dispatcher gate, capsule, LLM, tools
```

### The Four Meaningful Unions

```text
U1.   S ∪ F                   "Everything the household knows"
                              -> NEVER materialized (privacy)

U2.   ⋃ S(member)             "All selves on this household's K1 mesh"
                              -> Sync moves projections only, never raw S

U3.   F ∪ C                   "Household runtime"
                              -> Materialized; every K1 needs a coherent local view

U4.   S ∪ C(actor-scope)      "Personal runtime"
                              -> What this person needs to operate alone, offline
```

### The Differences (Sharp Edges)

```text
D1.   S \ F                   "Private Self"
                              -> Things in my self model the family NEVER sees in any form
                              -> Includes BLACK category items, private journal, therapy notes
                              -> Never syncs, never projects, never enters anyone else's SituationFrame

D2.   S \ C                   "Ungoverned Self"
                              -> Things in my self model the constitution does not regulate
                              -> Personal taste in music, private mood log
                              -> Exist but no rule applies; system treats as inert

D3.   F \ S(any)              "Pure Family Facts"
                              -> Facts that belong to the household, not to any one person
                              -> House address, dog's name, family wifi
                              -> No one "owns" them; constitution governs who can change them

D4.   C \ (S ∪ F)             "Latent Rules"
                              -> Rules in the constitution with no current subject
                              -> Guest rules when no guest present, teen rules when no teen exists
                              -> Activate the moment a subject appears
```

### The Empty-Set Invariants

These are **must-never-happen** rules. If any becomes non-empty, we have a bug.

```text
E1.   (S \ consent) ∩ F = ∅
        No self-data reaches family without consent. Ever.

E2.   (S \ C.visibility_rules) ∩ F = ∅
        No self-data reaches family without a visibility rule applying. Default-deny.

E3.   K0_outbound ∩ BLACK = ∅
        BLACK never leaves K1. Architectural invariant.

E4.   C.amendments \ signed = ∅
        Constitution changes without signature don't exist.

E5.   raw_S(other) ∩ ProjectedSelf(actor) = ∅
        SituationFrame never carries another person's raw S. Only projections.

E6.   tool_authority \ SituationFrame.capabilities = ∅
        No tool executes outside the actor's resolved capabilities.
```

Each invariant is a test target.

### V0 Locked Algebra Decisions

These ten decisions freeze the algebra for V0. They are the answers to the design questions raised during the V0 algebra pass.

```text
Q1. Relationship ownership
    -> Consensual edges. S declares its side; F derives the relationship
       only when both sides agree. Removal is unilateral.
    -> Exception: parent → child is constitution-asserted, not consensual.

Q2. Family Self
    -> No F.self entity in V0. Shared values live as C.shared_values.
    -> "FamilySelf" deferred to V1.

Q3. Guests
    -> Guests are first-class S with a degenerate schema:
       only S.core (display_name, age_band?) and S.context (present_since, host).
    -> Session-scoped by default; auto-purged when copresence ends.

Q4. Multi-device same person
    -> L1 (Core) + L2 (Identity): strong sync, signed, one truth.
    -> L3 (Pattern): CRDT merge (additive, time-decayed observations).
    -> L4 (Context) + L5 (State): per-device only, never synced.

Q5. Constitution self-amendment
    -> V0: C.governance is bootstrap-immutable.
    -> Only changeable by `factory_reset_household`.
    -> V1: meta-governance with super-quorum + waiting period.

Q6. Household = set or entity
    -> F is a derived view over (⋃ S(member), C).
    -> Exception: F.copresence and F.hub_state are device-observed authoritative facts.

Q7. Non-human members
    -> Pets, devices, the house = F.shared_resources, typed entries.
    -> No degenerate S for non-humans in V0.

Q8. Cross-household
    -> Out of scope for V0.
    -> One hook reserved: S.external_household_refs (declared, unused in V0).

Q9. Time scope of L4/L5
    -> L5 (State): per-turn, RAM only, decays after 5min gap (marked stale).
    -> L4 (Context): per-session (until activity boundary or 30min inactivity), RAM + ephemeral disk.
    -> L4/L5 never persisted as facts; may be persisted as observations
       (historical only) which feed L3 over time.

Q10. Ghost problem (former members)
     -> Four lifecycle states, no hard deletes in V0:
        ARCHIVED    : member opts out (frozen, no new writes, queryable historically)
        EMANCIPATED : child grows up (becomes own household root, edges -> external)
        MEMORIAL    : death (read-only, no inference, special language handling)
        SEVERED     : forced removal (hidden, recoverable only by household reset)
     -> Encrypt-shred is the only true delete; requires founding-adult quorum.
```

### How the Algebra Drives the Rest of the Document

```text
Three Sets             -> Core Concepts data shapes (next section)
Six Intersections      -> Runtime flow + Bridge query design
Triple (SituationFrame)-> Grounding capsule + ToolDispatcher gate (E0 substrate)
Unions                 -> Multi-K1 mesh + sync policy
Differences            -> Privacy category defaults (V0 Operating Design)
Empty-Set Invariants   -> System invariants I1-I10 + test matrix
V0 Locked Decisions    -> Inform every V0 product/policy decision below
Five Layers of S       -> Sync, persistence, inference policy per layer
```

## Layer Boundary: Kernel API vs UI Surfaces

This whiteboard is a **K1 kernel** design. Everything else in this document — SelfModelService, FamilyModelService, ConstitutionService, SituationFrame composer, IdentitySessionManager, AmendmentService, ToolDispatcher gate, CitationPackBuilder — is a kernel concern.

The kernel must be a **generalized component** in the same sense as the existing K1 components (`k1.bus`, `k1.sessionstate`, `k1.concierge`, `k1.fabric`, `k1.model_hub`, `k1.orchestrator`, `k1.planner`, `k1.memory_writer`). Each of those exposes a hexagonal port surface, defines its own typed contracts, and is consumed by other kernel components and (eventually) by UI adapters. None of them know about pixels, taps, keypads, push services, or platform SDKs.

Reference architectures in this repo:

```text
k1/concierge/ARCHITECTURE.md      -> 8 ports, adapter matrix, FSM, invariants
k1/sessionstate/ARCHITECTURE.md   -> 5 ports (ABC), co-defined types, single-writer
k1/fabric/ARCHITECTURE.md         -> capability resolver port, dispatch types
k1/model_hub/ARCHITECTURE.md      -> ILLMPort/IModelHubPort with HubRequest/HubResponse
k1/bus/ARCHITECTURE.md            -> IBus protocol, envelope contract
k1/orchestrator/ARCHITECTURE.md   -> task envelope, aggregated result
k1/planner/ARCHITECTURE.md        -> plan port, stepwise contracts
k1/memory_writer/ARCHITECTURE.md  -> recall/writeback port discipline
```

The new self-model component (working name `k1.selfmodel`, alongside the existing list above) follows the same shape: hexagonal ports, typed contracts, no transport opinion, no UI opinion.

### The Hard Rule

```text
K1 kernel exposes capabilities and consumes proofs.
The kernel never describes interaction.
```

If any kernel signature mentions a tap, a keypad, a tier-promotion timer, a notification channel, an avatar, a font, a copy string, or a platform SDK, the kernel has leaked UI concerns and the design is wrong.

### Layer Split

```text
+----------------------------------------------------------+
|                      UI LAYER                             |
|    per-platform: phone app, hub app, child tablet app,    |
|    web console, voice front-end, etc.                     |
|                                                           |
|    - Renders profile picker / avatars / copy / language   |
|    - Captures PIN keypad input                            |
|    - Invokes OS passkey / biometric / face APIs           |
|    - Renders amendment review screen                      |
|    - Subscribes to platform push (APNs, FCM, in-app)      |
|    - Owns the soft inactivity timer                       |
|    - Renders capsule freshness banner                     |
|    - Renders override prompt and captures user choice     |
|    - Translates kernel events into user-visible affordance|
+--------------------------+-------------------------------+
                           |
                  K1 Kernel Public API
                  (transport-agnostic; in-process call,
                   IPC, gRPC, ws — UI's choice)
                           |
+--------------------------+-------------------------------+
|                    K1 KERNEL LAYER                        |
|    k1.selfmodel  (NEW component, this design)             |
|    + existing  k1.concierge, k1.sessionstate, k1.bus,     |
|                k1.fabric, k1.model_hub, k1.orchestrator,  |
|                k1.planner, k1.memory_writer, k1.tools     |
|                                                           |
|    - SelfModelService                                     |
|    - FamilyModelService                                   |
|    - ConstitutionService                                  |
|    - SituationFrame composer                              |
|    - IdentitySessionManager  (verifies proofs, holds tier)|
|    - CredentialVerifier      (PIN hash, passkey signature)|
|    - AmendmentService        (DRAFT->ACTIVE state machine)|
|    - PolicyEvaluator                                      |
|    - CitationPackBuilder                                  |
|    - GroundingCapsuleBuilder                              |
|    - ToolDispatcher policy gate (step 0)                  |
+----------------------------------------------------------+
```

### Responsibility Mapping (Four Worked Examples)

| Concern | UI layer owns | Kernel layer owns |
| --- | --- | --- |
| Identity / Profile | Avatars, picker layout, tap handling, copy ("Tap your profile") | `list_eligible_profiles(device_context)`, `start_identity_session(profile_id, proof?)`, session token, tier value, hard TTL, revocation |
| PIN / Passkey | 4-digit keypad UX, error animations, "Forgot PIN" link, OS passkey/biometric prompt invocation | `present_credential(session_token, credential)` — verifies PIN hash or WebAuthn assertion; rate limits attempts; returns `VerificationResult`; emits `IDENTITY_VERIFIED` / `IDENTITY_REJECTED` |
| Amendment Approval | Review screen layout, plain-language diff rendering, "Approve and sign" button, step-up dialog | `draft_amendment`, `submit_amendment`, `sign_amendment(amendment_id, signing_proof)`, `decline_amendment`; emits `AMENDMENT_PENDING_SIGNATURE`, `AMENDMENT_ACTIVE`, `CONSTITUTION_CONFLICT_DETECTED` |
| Freshness / Override | Banner copy, "Proceed anyway" prompt, override confirmation UX | Returns `PolicyVerdict { decision, reason_code, override_eligible }`; accepts `proceed_with_stale(pending_id, reason?)`; audit-logs override with freshness state at decision time |
| Notifications | APNs/FCM subscription, notification text formatting, deeplink handling | Emits typed kernel events on the event stream; UI adapter translates events into platform notifications |
| Inactivity | Soft timer (e.g., 30min idle since last input) → calls `end_identity_session` | Hard TTL ceiling (e.g., 12h) — enforced regardless of UI state; UI bug or crash never extends a session |

The kernel never says "show this." The UI never says "this user is now Tier 2."

### Public Kernel API Surface (V0)

This is the canonical list of calls the UI layer is permitted to make. Every call is JSON-in / JSON-out, transport-agnostic, idempotent where applicable, and carries a session token (except the bootstrap calls).

```text
# Identity & sessions
list_eligible_profiles(device_context)                 -> [ProfileSummary]
start_identity_session(profile_id, proof?)             -> { session_token, tier, expires_at_ms }
present_credential(session_token, credential)          -> VerificationResult
end_identity_session(session_token)                    -> void

# Self / family / constitution reads
get_grounding_capsule(session_token)                   -> GroundingCapsule
get_household_rules_diff(constitution_id, va, vb)      -> ConstitutionDiff
get_pending_amendments(session_token)                  -> [AmendmentSummary]
get_review_queue(session_token)                        -> [SuggestionCard]

# Amendments
draft_amendment(session_token, body | suggestion_ref)  -> amendment_id
submit_amendment(amendment_id)                         -> void          # DRAFT -> PENDING
sign_amendment(amendment_id, signing_proof)            -> void          # appends signature
decline_amendment(amendment_id, reason?)               -> void

# Tool invocation
invoke_tool(session_token, tool_call)                  -> ToolResult | PolicyVerdict
confirm_tool(pending_id, confirmation_proof)           -> ToolResult
proceed_with_stale(pending_id, reason?)                -> ToolResult | DENIED

# Event stream (subscribe; transport adapter delivers to UI)
subscribe_events(session_token, topics)                -> EventStream
```

Argument and return types are defined in the kernel contract layer (next to `k1.selfmodel.types/`), not by the UI. UI adapters serialize/deserialize these types onto whichever transport the platform uses.

### Kernel Event Stream (Outbound, V0)

The kernel emits domain events. UI adapters translate these into platform-specific surfaces (push notifications, banners, deeplinks, voice replies). The kernel does not know any of those exist.

```text
IDENTITY_VERIFIED                  -> tier promoted; UI may dismiss step-up dialog
IDENTITY_REJECTED                  -> proof failed; UI may show error
IDENTITY_SESSION_ENDED             -> session token invalid; UI returns to picker
AMENDMENT_PENDING_SIGNATURE        -> required signers' UIs may notify
AMENDMENT_ACTIVE                   -> household rules updated; UI may show diff banner
AMENDMENT_REJECTED                 -> proposer's UI may show outcome
CONSTITUTION_CONFLICT_DETECTED     -> all UIs show conflict card
TOOL_REQUIRES_CONFIRMATION         -> UI shows confirmation prompt
TOOL_REQUIRES_IDENTITY             -> UI prompts for step-up
TOOL_DEFERRED_OFFLINE              -> UI shows queued state
PROJECTION_FRESHNESS_CHANGED       -> UI may update banner
SUGGESTION_CARD_AVAILABLE          -> UI may surface in review queue
```

### Anti-Patterns (Things This Whiteboard Must Not Imply)

```text
- Kernel function named "show_picker"                  -- BAD (UI verb)
- Kernel returning a string "Tap your profile"          -- BAD (copy)
- Kernel scheduling a 30-minute UI inactivity timer     -- BAD (UX timer)
- Kernel choosing PIN length or keypad layout           -- BAD (input UX)
- Kernel sending an APNs/FCM payload                    -- BAD (transport)
- Kernel deciding whether passkey or PIN is offered     -- BAD (capability negotiation belongs to UI)
- LLM asking "who is speaking?" as the identity primitive -- BAD (untrusted self-id; tier transitions are out-of-band)
- UI computing a SituationFrame                         -- BAD (UI consumes capsule, never composes it)
- UI deciding a tool should be allowed offline          -- BAD (UI cannot grant policy)
- UI maintaining its own copy of the constitution       -- BAD (UI reads via API; kernel owns truth)
```

### k1.selfmodel as a K1 Component

To follow the same shape as the rest of K1, the new component will eventually have the standard artifacts:

```text
k1/selfmodel/
  ARCHITECTURE.md
  selfmodel.mmd
  ports/                  # IIdentityPort, ICredentialPort, IConstitutionPort,
                          # ISituationFramePort, IAmendmentPort
  adapters/               # SQLite projection store, Bridge sync adapter,
                          # PolicyEvaluator, CitationPackBuilder
  contracts/              # Typed dataclasses (mirrors algebra: S, F, C, SituationFrame)
  service/                # SelfModelService, FamilyModelService,
                          # ConstitutionService, IdentitySessionManager,
                          # AmendmentService, GroundingCapsuleBuilder
  kernel/                 # Bootstrap wiring + lifecycle
  obs/                    # Metrics
  events/                 # Canonical kernel event types
```

This mirrors `k1.concierge`, `k1.sessionstate`, `k1.fabric`. The key takeaway: **`k1.selfmodel` is generalized kernel infrastructure**, not a one-off feature. Every UI surface (phone app, hub app, child tablet, voice, web) consumes the same kernel API. The UI layer is plural; the kernel is singular.

### Where This Document Has Been Tightened

The four subsections most affected by the kernel/UI distinction \u2014 they were written before the boundary was made explicit \u2014 should be read with these clarifications:

```text
Shared Hub Identity Tiers (V0 Identity Resolution Mechanism)
  -> "Profile picker tap" means UI invokes `start_identity_session`.
  -> "30min inactivity drops to Tier 0" means UI fires `end_identity_session`
     on its idle timer; kernel hard TTL is independent and authoritative.
  -> "Voice/face advisory" means UI may pre-fill the picker; kernel still
     requires `present_credential` for tier > 0.

Amendment User Experience
  -> "Approve and sign" is a UI button; it calls `sign_amendment(id, proof)`.
  -> "Push to required signers" means kernel emits AMENDMENT_PENDING_SIGNATURE;
     per-platform notification adapters deliver pushes.
  -> "Conflict card" is UI rendering of CONSTITUTION_CONFLICT_DETECTED event.

Memory Citation
  -> CitationPackBuilder is kernel-side; UI never sees raw recall payloads.
  -> "Citation handles" appear in the GroundingCapsule returned by the kernel;
     UI may render them but cannot mint or expand them \u2014 expansion goes
     through `recall_memory` (an LLM-facing tool, also kernel-side).

Offline / Stale Override
  -> "Proceed anyway" prompt is UI; the call is `proceed_with_stale(pending_id)`.
  -> Kernel decides eligibility via the risk \u00d7 freshness matrix; UI cannot
     promote a DENY into ALLOW.
```

## Core Concepts

The data shapes below are concrete realizations of the abstract sets above. `K1SelfModel` is one materialized snapshot of S at `(T, D)`; `FamilySelfModel` is the derived view of F; `FamilyConstitution` is the typed C. Read them with the algebra in mind — the dataclass field lists are illustrative, not normative; the algebra above is the contract.

### 1. K1 Self Model

A K1 Self Model is the local runtime representation of the current app/user/device identity.

It answers:

```text
Which person/device/session is this K1 acting for?
What can this actor see?
What can this actor change?
What communication style should the LLM use?
What local state is authoritative offline?
What K0 memory scopes are eligible for recall?
```

It is not just persona. It includes identity, role, authority, privacy band, consent, relationship context, device context, and memory scope.

Proposed shape:

```python
@dataclass(frozen=True)
class K1SelfModel:
    self_id: str                 # stable K1-local self id
    family_member_id: str        # canonical K0/KG person entity id
    device_id: str
    tenant_id: str
    family_space_id: str
    display_name: str
    role: str                    # parent, guardian, child, elder, guest, system
    age_band: str                # adult, teen, child, unknown
    authority_level: str         # admin, caregiver, self, limited, guest
    privacy_band: str            # GREEN, AMBER, RED, BLACK
    active_presence: str         # personal_device, shared_device, supervised_child, unknown
    locale: str
    timezone: str
    memory_scope_policy: dict
    tool_authority_policy: dict
    constitution_version: str
    last_hydrated_at_ms: int
    confidence: float
```

### 2. Family Self Model

A Family Self Model is the local K1 view of the household as a social/constitutional unit.

It answers:

```text
Who belongs to this family?
How are they related?
Who can act for whom?
What shared routines, norms, preferences, and boundaries exist?
Which facts are local-only vs K0-consolidated truth?
```

Proposed shape:

```python
@dataclass(frozen=True)
class FamilySelfModel:
    family_space_id: str
    household_name: str
    members: list[FamilyMemberRef]
    relationship_edges: list[RelationshipEdge]
    household_routines: list[RoutineRef]
    care_responsibilities: list[CareResponsibility]
    shared_preferences: list[PreferenceRef]
    constitution_ref: str
    sync_state: str              # fresh, stale, offline_local_only, conflict_pending
    memory_truth_revision: str
```

Example relationship edges:

```text
mom parent_of child_1
 dad parent_of child_1
child_1 sibling_of child_2
mom authorized_for health.child_1
 dad authorized_for pickup.child_2
```

These should map to K0 KG entities and KG edges over time, but K1 keeps a compact local projection for fast prompt grounding and offline operation.

### 3. Family Constitution

The constitution is the normative layer: what FamilyOS is allowed to do, how it behaves, and how authority is resolved.

It should include:

- family values and house rules
- privacy rules
- child safety rules
- authority hierarchy
- confirmation policy
- tool safety rules
- memory sharing policy
- external connector policy
- proactive behavior limits
- escalation rules

Proposed shape:

```python
@dataclass(frozen=True)
class FamilyConstitution:
    constitution_id: str
    version: str
    family_space_id: str
    values: list[str]
    household_rules: list[Rule]
    privacy_policy: PrivacyPolicy
    child_safety_policy: ChildSafetyPolicy
    authority_matrix: AuthorityMatrix
    tool_policy: ToolPolicy
    memory_policy: MemoryPolicy
    proactive_policy: ProactivePolicy
    emergency_policy: EmergencyPolicy
    effective_at_ms: int
    updated_by: str
```

Important: the constitution is not a vibe. It is an executable policy object used before memory recall and tool execution.

### 4. K0 Memory as Durable Truth, K1 as Working Self

K0 stores and consolidates the long-term material:

- episodic memory: what happened
- semantic memory: stable preferences and facts
- procedural memory: routines and habits
- social memory: relationships and roles
- prospective memory: intentions/goals
- KG entities: canonical members, schools, doctors, vehicles, devices, lists
- KG edges: parent_of, sibling_of, assigned_to, attends_school, allergic_to, authorized_for
- embeddings: recall and similarity

K1 stores working projections:

- active self model
- family self model snapshot
- constitution snapshot
- active session identity
- prompt-ready memory capsule
- local operational state for tools
- offline write queue

K0 is the source of durable memory. K1 is the source of immediate embodied agency.

## The Five Layers of Self

The S set has internal layering. Higher layers can be inferred; lower layers must be declared. This layering governs sync policy, persistence policy, and inference policy.

```text
+----------------------------------------------------------+
| L5  STATE     "What is true about me right now?"          | volatile, per-device
|               mood, location, focus, fatigue, presence    |
+----------------------------------------------------------+
| L4  CONTEXT   "What am I doing / who am I with?"          | short-lived, per-device
|               current activity, co-present, device-in-use |
+----------------------------------------------------------+
| L3  PATTERN   "What do I usually do?"                     | learned, CRDT-synced
|               routines, rhythms, preferences, habits      |
+----------------------------------------------------------+
| L2  IDENTITY  "Who am I in this household?"               | semi-stable, strong-sync
|               role, declared_relations, responsibilities  |
+----------------------------------------------------------+
| L1  CORE      "What is non-negotiable about me?"          | stable, strong-sync
|               name, age_band, language, capabilities,     |
|               consent posture, developmental stage, status|
+----------------------------------------------------------+
```

### Inference Direction

```text
L1, L2  -> Declared by humans (onboarding + constitution).
L3      -> Learned over time, surfaced as suggestions, never silently committed.
L4, L5  -> Ambient sensing, never persisted as truth, only as transient context.
```

This is why "privacy = settings" fails — L1/L2 are the only things settings can carry. L3-L5 must be governed by **principles**, not toggles.

### Cross-Device Sync Policy

| Layer | Sync mode | Persistence | Conflict policy |
| --- | --- | --- | --- |
| L1 Core | Strong sync, signed | Durable | LWW + audit log; review on next interactive session |
| L2 Identity | Strong sync, signed | Durable | LWW + audit log |
| L3 Pattern | CRDT merge (additive, time-decayed) | Durable | Set union |
| L4 Context | Per-device only | RAM + ephemeral disk (crash recovery) | No conflict (partition) |
| L5 State | Per-device only | RAM only | No conflict (partition) |

### Time Scope and Decay

```text
L5: per-turn truth
    decay rule: if no observation in 5min, mark stale=true
    Front actor must hedge: "I think you're still at the gym?" not assert
    persisted only as observations, never as facts

L4: per-session truth
    boundary: explicit activity change OR device handoff OR 30min inactivity
    persisted only as observations (feeds L3 over time)

L3: rolling pattern
    accretes from L4/L5 observations over weeks
    surfaced as suggestions ("Should I remember soccer as Liam's interest?")
    never auto-committed as durable rule

L1, L2: stable
    changes go through onboarding/constitution flow with signing
```

### Layer-to-Intersection Map

```text
S ∩ F (Shareable Self)         : projects L1, L2, filtered L3 only
                                 L4/L5 never enter F unless via copresence sensor
S ∩ C (Granted Self)           : evaluates L1, L2 capabilities; L3 informs preferences
S ∩ C ∩ S (Cross-Person Auth)  : L1, L2 only (authority must be stable)
SituationFrame                 : L1+L2+filtered L3 as ProjectedSelf;
                                 L4+L5 as transient context block
```

The layered model is what makes `K1SelfModel` a *living projection* rather than a static profile: each turn assembles the visible slice of L1-L5 for the current actor, on the current device, at the current moment.

## Runtime Flow: Grounded Intelligence

### Session Start / Runtime Hydration

```text
1. ConciergeRuntime starts for a session/device.
2. SelfModelService resolves user_id, device_id, family_space_id, privacy band.
3. FamilyModelService loads the compact family projection.
4. ConstitutionService loads the signed local constitution snapshot.
5. Objects are stored in a runtime context or SessionState-owned section via the single-writer path.
6. Prompt/tool layers receive immutable read-only views.
```

This should respect Concierge's single-writer invariant: services may compute or hydrate models, but SessionState writes must be applied through the existing SessionState/Controller write path.

### Turn Start

```text
1. User/device input enters K1.
2. K1 resolves or verifies active self:
   - personal device -> known member
   - shared device -> identify or ask
   - child device -> supervised/member-scoped
3. K1 reads hydrated K1SelfModel + FamilySelfModel + FamilyConstitution.
4. K1 computes memory recall policy:
   - allowed selectors
   - allowed family members
   - privacy band ceiling
   - whether graph/social recall is allowed
5. K1 builds a prompt grounding capsule: identity, role, authority, family context, constitution rules, and allowed memory scopes.
6. The LLM may call `recall_memory` through `IMemoryPort` when additional K0 memory is needed.
7. LLM plans/responds/tools using this capsule and any approved recall result.
```

The default should be permission-first and recall-on-demand. We should not pre-fetch broad K0 memories every turn. That keeps prompts lean, avoids privacy leaks, and respects the existing `recall_memory` tool philosophy.

### Prompt Grounding Capsule

The LLM should not receive raw unlimited K0 memory. It should receive a compact capsule:

```json
{
  "active_self": {
    "member_id": "mom",
    "role": "parent",
    "authority": "caregiver_admin",
    "device": "mom_phone",
    "privacy_band": "AMBER"
  },
  "family_context": {
    "members": ["mom", "dad", "child_1", "child_2", "child_3"],
    "relevant_relationships": ["mom parent_of child_1", "dad parent_of child_2"],
    "active_routines": ["school_morning", "sunday_meal_plan"]
  },
  "constitution": {
    "tool_confirmations": ["RED always confirm", "child pickup changes parent only"],
    "privacy_rules": ["do not reveal child health details to siblings"],
    "proactive_limits": ["max 3 proactive pings per day per member"]
  },
  "k0_recall": {
    "semantic": [],
    "procedural": [],
    "social": [],
    "prospective": [],
    "episodic": []
  },
  "local_state_refs": {
    "calendar_snapshot_id": "...",
    "tasks_snapshot_id": "...",
    "reminders_snapshot_id": "..."
  }
}
```

### Tool Execution

Before tool execution:

```text
CapabilityRequest
  -> ToolDispatcher step 0: SelfModelAuthorityGate
  -> ConstitutionPolicyGate
  -> MemoryScopeGate
  -> existing ToolDispatcher validation/budget/timeout/result pipeline
  -> Fabric Resolver / Orchestrator / Back tool implementation
  -> MCP/BRIDGE/WASM provider
```

The gate checks:

- Is this actor allowed to perform the action?
- Is the target member allowed?
- Is confirmation required?
- Is this a child/safety/health/finance action?
- Should K0 memory be written after execution?
- Should a feedback signal be emitted?

This gate is enforcement, not advice. Prompt instructions and tool descriptions can guide the LLM, but real safety must live in the dispatcher/Fabric path.

### After Tool Execution

Every meaningful tool outcome should be classified:

```text
local state only
local state + K0 memory.write
local state + K0 plan.committed
local state + feedback only
local state + domain audit event
```

Examples:

- Child completes chore -> local chores DB + `memory.write` if pattern-forming + feedback outcome.
- Parent changes pickup -> local school/transport DB + `memory.write` + audit event.
- Medication changed -> local health DB + RED audit + `memory.write` with high privacy band.
- User corrects LLM preference -> obs feedback to K0 P21 + possible semantic memory update.

## Multi-K1 Family Mesh

### Personal K1

Each member has a local K1 instance:

```text
K1_MOM: role=parent, authority=admin, device=mom_phone
K1_DAD: role=parent, authority=admin, device=dad_phone
K1_CHILD_1: role=child, authority=self_limited, device=child_tablet
K1_CHILD_2: role=child, authority=self_limited, device=child_phone
K1_HUB: shared device, active_self=unknown until identified
```

Each K1 can work offline with local state and queued writes. K0/Bridge later syncs, consolidates, and emits updated truth/memory events.

### Shared Family Truth

K0 eventually reconciles:

```text
K1 local event -> Bridge command.submit -> K0 P02/P03/P07
K0 consolidation -> memory.formed.v1 / sync.complete.v1 SSE
K1 receives SSE -> refresh self/family projections
```

### Conflict Cases

Examples:

- Mom assigns pickup to Dad while Dad assigns pickup to Grandma.
- Child completes chore offline while parent reassigns it.
- Shared hub creates reminder without identifying speaker.

Resolution should use:

- authority matrix
- event timestamp/device provenance
- LWW only for low-risk fields
- explicit conflict queue for safety-sensitive changes
- K0 P03 consolidation for truth/memory, not blind overwrite

## Self Model Storage and SessionState Integration

This section is about *where in K1* the layered self model lives at runtime. The five conceptual layers (L1-L5) are defined above; this section addresses the storage and SessionState wiring.

Existing `MetaSection` and `PersonaSection` should not be overloaded.

Suggested K1 runtime sections/components:

```text
MetaSection
  session_id, user_id, device_id, privacy_band, lifecycle

PersonaSection
  response style, voice, vocabulary, user communication preferences

NEW: SelfModelSection
  active member identity, role, authority, memory scope, constitution version

NEW: FamilyModelSection
  compact household member graph, relationship edges, active routines

NEW: ConstitutionSection
  local signed policy snapshot, authority matrix, confirmation rules
```

If we avoid adding sections immediately, this can begin as a service over Meta/Persona plus local SQLite cache:

```text
k1/self_model/service.py
k1/self_model/models.py
k1/self_model/storage.py
k1/self_model/authority.py
k1/self_model/context_builder.py
```

Later it can become formal SessionState sections.

### Relationship to Existing Sections

Do not overload `PersonaSection` with authority and family policy. Persona should remain communication preference and style. It can keep short family hints for prompt rendering, but the durable model should be typed elsewhere.

Recommended migration path:

```text
Phase A: SelfModelService reads MetaSection + PersonaSection._preferences["family"] + local projection cache.
Phase B: Add typed local projection store for self/family/constitution.
Phase C: Add formal SessionState sections if needed by latency/token budgets.
Phase D: K0/KG becomes durable source for family members, relationships, routines, and constitution revisions.
```

Keep the distinction clear:

```text
K1SelfModel       = session-scoped identity/authority/memory scope.
IdentitySnapshot  = per-turn dynamic identity overlay from OPP-7.
PersonaSection    = response style and communication preferences.
FamilySelfModel   = compact local projection of family graph and routines.
K0 memory/KG      = durable truth and consolidation layer.
```

## Bridge/K0 Query Design

K1 self model should influence every recall query.

Example recall selectors for a family planning turn:

```json
{
  "selectors": [
    {"type": "semantic", "query": "family meal preferences allergies dislikes", "limit": 10},
    {"type": "procedural", "query": "weekday dinner routine grocery planning", "limit": 5},
    {"type": "social", "topic": "family.relationships", "limit": 20},
    {"type": "graph", "topic": "member child_1 constraints", "limit": 10},
    {"type": "prospective", "query": "current family goals intentions", "limit": 5}
  ],
  "space_id": "family_space",
  "max_latency_ms": 200,
  "fail_fast": false,
  "policy_caps": {
    "actor_member_id": "mom",
    "privacy_band_ceiling": "AMBER",
    "target_members": ["family"]
  }
}
```

If K0 is offline, K1 should use the last local projection and mark the grounding capsule:

```json
{"memory_freshness": "offline_cached", "staleness_ms": 86400000}
```

## Tool Design Comes After Self Model

M11 tools should be designed against this substrate.

A tool should not simply say:

```text
tool.write.chores_assign(title, assigned_to)
```

It should be understood as:

```text
actor_self -> target_member -> authority check -> constitution check -> local write -> memory/audit/writeback policy
```

### Tool Contract Extensions

Future M11 tool contracts should include these policy blocks:

```yaml
self_model_policy:
  requires_identified_actor: true
  target_member_input: "assigned_to"
  allowed_roles: ["parent", "guardian"]
  child_visible: true

memory_policy:
  recall:
    enabled: true
    selectors: ["semantic", "procedural", "social", "graph"]
  writeback:
    enabled: true
    topics: ["memory.write"]
  grounding_required: false

constitution_policy:
  confirmation_required: true
  authority_rule: "parent_or_guardian_for_child_assignment"
  privacy_band_ceiling: "AMBER"

outcome_policy:
  emits_domain_event: true
  event_topic: "k1.chores.assigned.v1"
  feedback_signal: "OUTCOME"
```

These policy fields should serve two different consumers:

1. Prompt/tool schema generation: hide or annotate tools before the LLM sees them.
2. Runtime enforcement: deny, require HITL approval, or allow at `ToolDispatcher` / Fabric execution time.

The second path is mandatory. The first path is UX and steering.

### LLM-Operable Tools

Tools need descriptions and output shapes that let Planner compose them.

Good tool output:

```json
{
  "status": "created",
  "task_id": "...",
  "target_member_id": "child_1",
  "memory_write_recommended": true,
  "suggested_followups": [
    {"tool": "tool.write.reminders_create", "reason": "due date exists"},
    {"tool": "tool.execute.messaging_send", "reason": "assigned to another member"}
  ]
}
```

This does not force the tool to call other tools. It gives Planner/Orchestrator structured hints.

## Revised M11 Order

The earlier M11 domain list is still useful, but it should come after identity/self modeling.

Recommended order:

1. K1 Self Model design and service
2. Family Self Model local projection
3. Family Constitution policy model
4. K0 recall grounding capsule builder
5. Authority/constitution gate before Fabric tool execution
6. Tool contract policy extensions
7. Family context tools:
   - `tool.read.family_context`
   - `tool.read.family_daily_briefing`
   - `tool.read.family_member_profile`
   - `tool.read.family_routines`
8. Then M11 native tools:
   - tasks
   - reminders
   - messaging
   - calendar enhancements
   - chores
   - meal planner/grocery
   - school/transport
   - budget/health

## Concrete Example: Daily Morning Flow

```text
Workflow: family_daily_briefing, scheduled 7:00 AM

1. Workflow fires from K1 scheduler.
2. Active self: family hub or parent device.
3. K1 loads family model + constitution.
4. K1 queries K0:
   - procedural: morning routines
   - prospective: today intentions/goals
   - social/KG: family members, schools, responsibilities
   - semantic: preferences, constraints
5. K1 reads local tools:
   - calendar today
   - reminders due
   - chores due
   - school pickup
   - open tasks
6. LLM composes briefing with policy:
   - parent sees all
   - child sees own items only
   - health details hidden unless authorized
7. Optional actions:
   - create reminder
   - message assigned driver
   - flag conflict
8. Outcomes:
   - local state updates
   - K0 feedback if user dismisses/accepts
   - memory.write for new stable pattern
```

## Concrete Example: Child Device

```text
User on child tablet: "What do I have to do today?"

K1_CHILD_1 self model:
  role=child
  authority=self_limited
  privacy_band=GREEN/AMBER child-scoped

Allowed recall:
  own chores
  own reminders
  own school schedule
  family public calendar

Denied recall:
  sibling private health
  parent finance
  family-wide sensitive messages

Output:
  friendly child-appropriate daily list

Tool actions allowed:
  complete own chore
  snooze own reminder within policy
  ask parent approval for schedule-changing action
```

## Concrete Example: Parent Device

```text
User on mom phone: "Move Liam's dentist appointment and tell Dad."

K1_MOM self model:
  role=parent
  authority=caregiver_admin

Plan:
  1. recall Liam health scheduling constraints from K0 if allowed
  2. update calendar/health appointment
  3. send family message to Dad
  4. write memory/audit event

Policy:
  health appointment changes are AMBER/RED depending details
  requires explicit confirmation before final write
```

## Locked Design Decisions

These are now accepted decisions for the first self-model implementation path.

```text
Decision 1: SelfModel starts as a full service plus local projection store.
            It is not a new SessionState section in v0.

Decision 2: Persona is communication style only.
            It must not become authority, identity, or policy storage.

Decision 3: Constitution is executable policy.
            It is not just prompt text or family values prose.

Decision 4: ToolDispatcher enforces policy before execution.
            Prompt allowlists can steer; dispatcher gates must enforce.

Decision 5: K0 recall always goes through IMemoryPort.
            No direct Bridge/K0 recall calls from prompt, actor, or tool code.

Decision 6: Shared devices default to low privilege until identity is known.
            Unknown speaker means public/low-risk context only.
```

The `poc/k1_poc` Concierge POC remains useful as the proving ground because it already expresses the important runtime shape:

- bus-driven FSM
- Front LLM as user voice
- Back LLM as worker
- shared ReAct loop
- tool dispatch surfaces
- single-writer SessionState discipline
- OPP-7 dynamic identity

The production Concierge has evolved beyond the POC, but the POC gives us a compact end-to-end sandbox for self-model behavior tests before permanent contracts are carved into the kernel.

## System Invariants

Invariants are the rules that must remain true even as implementation changes. They should be testable.

### I1: SelfModel Is a Service Boundary

```text
K1SelfModel v0 lives behind SelfModelService.

Allowed:
  MetaSection -> SelfModelService
  PersonaSection family hints -> SelfModelService
  local projection store -> SelfModelService
  K0/KG projection refresh -> SelfModelService

Not allowed:
  direct SessionState section dependency for v0
  prompt code constructing identity ad hoc
  tool code reading raw PersonaSection as authority
```

Test target:

```text
Given MetaSection + PersonaSection family hints + local projection,
SelfModelService returns one immutable K1SelfModel snapshot.
```

### I2: Persona Cannot Grant Authority

```text
PersonaSection answers:
  How should Concierge speak?

PersonaSection does not answer:
  Who is allowed to do this?
  Which child can be acted on?
  Which memories may be recalled?
  Which tool requires approval?
```

If a future prompt says the user prefers a casual tone, that changes wording only. It cannot unlock a calendar write, child health recall, payment action, or school pickup change.

### I3: Constitution Must Be Executable

```text
FamilyConstitution -> policy verdict

Verdict types:
  ALLOW
  DENY
  REQUIRE_CONFIRMATION
  REQUIRE_IDENTITY
  REQUIRE_PARENT_OR_GUARDIAN
  REQUIRE_K0_FRESHNESS
  AUDIT_ONLY
```

The constitution can be summarized into prompts, but the authoritative version must be evaluated by code.

```text
Prompt text:     guidance for the LLM
Policy verdict:  enforcement for K1
```

### I4: ToolDispatcher Step 0 Is the Enforcement Gate

```text
LLM tool call
    |
    v
+-------------------------------+
| ToolDispatcher step 0          |
| SelfModelAuthorityGate         |
| ConstitutionPolicyGate         |
| MemoryScopeGate                |
+---------------+---------------+
                |
      +---------+---------+
      |         |         |
      v         v         v
    ALLOW     DENY      HITL
      |         |         |
      v         v         v
 existing   blocked   ask/approve
 dispatch             then resume
```

No tool implementation should be responsible for inventing its own family authority logic. Domain tools can add domain validation, but the family/self/constitution gate is central.

### I5: K0 Recall Is Permissioned and Port-Bound

```text
Front/Back LLM
    |
    v
recall_memory tool
    |
    v
IMemoryPort
    |
    v
BridgeRecallAdapter
    |
    v
K0 recall/query
```

The recall request must carry a memory scope derived from K1SelfModel and FamilyConstitution:

```text
actor_member_id
device_id
privacy_band_ceiling
allowed_target_members
allowed_selectors
denied_selectors
freshness_requirement
```

Test target:

```text
Child device cannot recall sibling private health memory.
Shared unknown device cannot recall private memory.
Parent device can recall child schedule if constitution allows caregiver scope.
```

### I6: Shared Device Starts Unknown and Low-Privilege

```text
Shared hub input
    |
    v
active_self = unknown
    |
    v
Allowed:
  public family info
  generic conversation
  harmless local suggestions

Denied or requires identity:
  private memory recall
  child-specific sensitive info
  calendar/task/reminder writes
  health/school/finance actions
  external messages
```

Identity resolution is not a UX nicety here. It is a security and family-trust invariant.

### I7: Dynamic Identity Is an Overlay, Not Durable Truth

```text
K1SelfModel        = session/runtime identity substrate
IdentitySnapshot   = per-turn OPP-7 adaptation overlay
PersonaSection     = communication style
K0/KG              = durable truth and memory
```

OPP-7 can adapt tone, role framing, expertise, and emotional attunement. It cannot mutate durable family identity or authority by itself.

### I8: Offline K1 Must Fail Softly, Not Blindly

```text
K0 online:
  fresh projection + recall allowed by policy

K0 offline:
  cached self/family/constitution projection
  freshness marker in grounding capsule
  sensitive actions may require confirmation or deny
```

Offline state can support daily life, but stale context must be visible to the LLM and policy layer.

### I9: Single Writer Still Holds

SelfModelService can compute, hydrate, and return snapshots. It must not become an untracked SessionState writer.

```text
SelfModelService computes snapshot
    |
    v
Concierge/FSM applies any SessionState-visible change through existing writer path
```

This keeps the current Concierge invariant intact: Back, tools, planner, and orchestrator do not directly write SessionState.

### I10: Every Invariant Gets a POC Test Before Production Contract

The first proving lane should be `poc/k1_poc` or a similarly isolated Concierge integration harness.

```text
POC behavior test passes
    |
    v
production service contract
    |
    v
kernel-level integration test
```

This prevents us from freezing the wrong shape too early while still keeping the design honest.

## Open Design Questions

The ten algebra-level questions (Q1-Q10) are resolved in **V0 Locked Algebra Decisions** above. The questions in this section are the policy/product-level questions that sit on top of the algebra and were already in flight before the algebra pass.

Resolved now:

1. `SelfModel` starts as service plus local projection, not a SessionState section.
2. Persona is communication style only.
3. Constitution is executable policy, not prompt text.
4. ToolDispatcher enforces policy before execution.
5. K0 recall always goes through `IMemoryPort`.
6. Shared devices default to low privilege until identity is known.

### Resolution Matrix

| Question | Current decision | Notes |
| --- | --- | --- |
| Constitution authored manually or inferred? | Both | Parent/guardian-authored rules are authoritative. K0/K1 can infer soft preferences and suggest rule candidates, but suggestions do not become constitution until approved. |
| Child privacy bands across sibling devices | Needs design now | Current code has `PrivacyBand` in K1 SessionState. Bridge wire decisions say GREEN/AMBER/RED only; BLACK is K1-local if needed. We need subject/member-scoped privacy, not just global band. |
| Minimum identity proof on shared devices | Needs design now | Suggested: public/no-risk actions need no proof; member-private recall/write needs step-up identity such as PIN/passkey/profile confirmation; RED actions need stronger guardian approval. |
| K0 KG schema for family members/edges | Defer until K1 service emits stable outputs | K1 should emit identifiable self/family/constitution snapshots first. K0 KG schema can capture those outputs during K0 enhancement work. |
| Can K0 P03 modify constitution-like truths? | Defer and constrain | For now, K0 may only produce suggestions/proposed changes. It must not silently modify constitution. Revisit after K1 service output is stable. |
| Version/sign constitution snapshots | Use sync/signing architecture | ADR-0050d gives device Ed25519 signing keys + X25519 encryption for sync. Bridge architecture says one Ed25519 envelope signature; K0 does not sign responses. Constitution snapshots should be locally signed by authorized K1/device identities. |
| Memory citations without prompt overload | Needs design now | Use compact citation handles and short summaries, not raw memory dumps. Full memory details should stay behind `IMemoryPort` and be fetched only on demand. |
| K0 offline + stale local model | Needs design now | Use cached projection with explicit freshness marker. Allow low-risk local behavior; restrict or confirm sensitive recall/writes when stale. |
| Parent confirmation even for parent actions | Needs design now | Parent authority is not unlimited autopilot. High-impact or irreversible actions still need confirmation/audit. |
| POC test set | Reframe | `poc/k1_poc` is not a tiny unit-test surface; it is a working UI + real LLM bootstrap. Use it as a broad behavior sandbox plus targeted scripted tests. |

### Child Privacy Band Direction

The important correction is that a band alone is not enough. Sibling privacy needs three dimensions:

```text
privacy verdict = band + subject_member + allowed_audience
```

Recommended first model:

```text
GREEN:
  family-public or harmless data.
  Example: public chore title, public family event, shared grocery item.

AMBER:
  family-private but still audience-scoped.
  Example: child_1 school reminder visible to parents and child_1, not all siblings by default.

RED:
  sensitive individual-private data.
  Example: health, therapy, discipline, legal, finance, location history.
  Visible only to subject and authorized caregivers unless constitution says otherwise.

BLACK:
  K1-local ephemeral only if needed.
  Bridge/K0 wire currently uses GREEN/AMBER/RED, so BLACK should not be synced as durable K0 memory.
```

This gives us the rule we need for sibling devices:

```text
Sibling device cannot access another child's AMBER/RED subject-scoped memories
unless the memory is explicitly marked family-public or the constitution grants access.
```

### Shared Device Identity Proof Direction

Shared devices should be tiered instead of using one proof rule for everything.

```text
Tier 0: No proof
  allowed: public family info, general chat, harmless suggestions
  denied: private recall, writes, external messages

Tier 1: Lightweight member proof
  examples: profile tap + PIN, passkey, device-local biometric, parent-approved child profile
  allowed: member's own non-sensitive tasks/reminders/calendar reads

Tier 2: Strong / guardian proof
  examples: parent PIN, passkey, OS biometric, second adult confirmation for configured actions
  allowed: caregiver actions, child-sensitive changes, external sends, RED actions after confirmation
```

Open design detail: we need to decide whether voice recognition is advisory only or accepted as proof. My current recommendation is advisory only for v0. It can help route the conversation, but it should not unlock private recall or side-effecting tools without PIN/passkey/biometric step-up.

### K0/KG Deferral Boundary

We should not block K1 SelfModelService on final K0 KG schema. Instead K1 should produce clean, capture-friendly outputs:

```text
k1.self_model.snapshot.v1
k1.family_model.snapshot.v1
k1.constitution.snapshot.v1
k1.constitution.change_proposed.v1
k1.constitution.change_approved.v1
```

These outputs should include stable IDs:

```text
tenant_id
family_space_id
member_id
device_id
constitution_id
constitution_version
projection_revision
```

Then K0 enhancement work can map them into KG `Person`, family-space, relationship, authority, and constitution nodes later without forcing K1 to wait.

### Where K0 Sync Sits

The bridge architecture diagram makes the layering explicit:

```text
K1 is self-sufficient and offline-safe.
K0 is the enhancement layer for cross-device sync, long-term memory, and KG.
Bridge is the security/transport gateway between them.
```

For self/family/constitution projections, the first model should be:

```text
K1 local projection store
    |
    | local change: self/family/constitution snapshot or delta
    v
Bridge Local Outbox
    |
    | when K0 reachable
    v
/k0/command.submit
    |
    | topic: sync.delta
    v
K0 st_sync / P07 CRDT device sync
    |
    | after K0-mediated sync completes
    v
/k0/sse.subscribe
    |
    | event: k0.sync.complete.v1
    v
K1 refreshes local projection freshness/revision
```

So K0 sync does not own the first K1 self model. It distributes and consolidates the durable cross-device truth after K1 has emitted stable, identifiable snapshots/deltas.

Important distinction:

```text
K1 local store:
  immediate runtime truth for this device/session

Bridge local outbox:
  offline queue for commands/sync deltas when K0 is unavailable

K0 P07 sync:
  cross-device convergence layer for accepted snapshots/deltas

K0 KG/P03:
  later enhancement layer for family graph, memory consolidation, and suggestions
```

### Constitution Versioning and Signing Direction

Use the multi-device sync architecture, but keep authority local and explicit.

```text
FamilyConstitutionSnapshot
  constitution_id
  family_space_id
  version
  parent_version
  body_hash
  created_at_ms
  effective_at_ms
  approved_by_member_id
  signer_device_id
  signer_public_key_id
  signature_alg = Ed25519
  signature
  sync_state
```

Flow:

```text
Parent approves constitution change
    |
    v
K1 creates canonical snapshot JSON
    |
    v
K1 signs snapshot with authorized device Ed25519 key
    |
    v
Bridge local outbox queues signed snapshot/delta if K0 is offline
  |
  v
Bridge submits `sync.delta` command to K0 P07 when reachable
    |
    v
K0 emits `k0.sync.complete.v1` by SSE after sync completes
  |
  v
Other K1 devices refresh projection and verify signer + version lineage
    |
    v
K0 may store/capture receipt, but K0 response signature is not required
```

This follows the existing direction:

- ADR-0050d uses Ed25519 signing keys per device and X25519 encryption for sync.
- Bridge architecture uses one Ed25519 signature on canonical envelopes.
- The bridge architecture routes device sync through command topic `sync.delta` into K0 `st_sync` / P07 and announces completion with `k0.sync.complete.v1` SSE.
- K0 does not sign responses; it returns receipts/query payloads.

#### Amendment User Experience (V0)

The technical signing path above is necessary but not sufficient. The user-facing flow has equal weight: a constitution amendment must feel deliberate, reviewable, and reversible-before-commit.

Lifecycle states of an amendment proposal:

```text
DRAFT       -> proposal created, not yet submitted for approval
PENDING     -> submitted; awaiting required signer(s)
APPROVED    -> all required signatures present; queued for sync
ACTIVE      -> distributed and verified by other K1 devices
SUPERSEDED  -> a later version is now ACTIVE
REJECTED    -> a required signer declined; proposal closed
EXPIRED     -> PENDING longer than the freshness window (default 7 days)\n```\n\nUI surfaces:\n\n```text\n+-----------------------------------------------------+\n| Source of proposal                                  |\n|   - Direct edit by guardian in \"Household Rules\"    |\n|   - Acceptance from review queue (suggested rule)   |\n|   - Inline accept (\"Should this become a rule?\"     |\n|     during a turn)                                  |\n+-----------------------------------------------------+\n             |\n             v\n+-----------------------------------------------------+\n| Proposal review screen (one screen, one decision)   |\n|   - Plain-language diff: \"Was X. Now Y.\"            |\n|   - Affected members listed                         |\n|   - Affected categories highlighted                 |\n|   - Effective date selector (now / next morning /   |\n|     specific date)                                  |\n|   - Required approvers list with status pills       |\n+-----------------------------------------------------+\n             |\n             v\n+-----------------------------------------------------+\n| Approval action                                     |\n|   - \"Approve and sign\" -> step-up auth              |\n|     (PIN / passkey / OS biometric)                  |\n|   - \"Request changes\"  -> back to draft             |\n|   - \"Decline\"          -> REJECTED                  |\n+-----------------------------------------------------+\n```\n\nApproval quorum (V0 defaults):\n\n```text\nSingle-guardian household        : 1 guardian signature.\nMulti-guardian household         : 1 guardian signature for routine rules;\n                                   2 guardian signatures for protected categories\n                                   (child autonomy, health, location, custody,\n                                   finance, external comms, constitution governance).\nProtected category set is itself in C.protection_rules and is editable only with\nthe higher quorum.\n```\n\nNotifications:\n\n```text\nOn PENDING -> push to required signers' personal K1.\nOn APPROVED -> push summary to all adult members.\nOn ACTIVE   -> visible diff in Household Rules timeline; 7-day undo banner.\nOn REJECTED -> proposer is notified with optional reason.\n```\n\nUndo window:\n\n```text\nFor 7 days after an amendment becomes ACTIVE, any required-quorum group of\nguardians may issue a \"revert\" amendment that produces the prior body_hash.\nRevert is itself a signed amendment with the same flow; it is not a magic button.\nAfter 7 days, the only path is a forward amendment.\n```\n\nOffline conflict resolution \u2014 two parents approve different versions:\n\n```text\nThis is the realistic conflict case.\n\nScenario:\n  Mom on her K1 (offline)  approves proposal P_A based on parent_version v3.\n  Dad on his K1 (offline)  approves proposal P_B based on parent_version v3.\n  Both come back online; both reach K0 P07.\n\nResolution rule (V0):\n  parent_version is the linearization key.\n  Both proposals share parent_version=v3, so they are siblings, not a chain.\n  K0 P07 detects sibling commit attempts and emits a CONFLICT event\n  carrying both signed proposals.\n\nWhat happens next:\n  - No version is auto-promoted to ACTIVE.\n  - Constitution projection on every K1 enters conflict_pending state.\n  - All K1 devices show a \"Conflicting amendment\" card listing both proposals\n    with diffs and signers.\n  - The guardians (signers of either proposal plus any other adult guardians)\n    must collectively choose one of:\n        * Accept P_A          (Dad must add signature to P_A's body, producing v4)\n        * Accept P_B          (Mom must add signature to P_B's body, producing v4)\n        * Compose a new P_C   (drafted from both; goes through normal flow)\n        * Withdraw both       (no change; v3 remains ACTIVE)\n  - During conflict_pending, the constitution operates at body_hash(v3) for\n    enforcement. New protected-category actions REQUIRE_CONFIRMATION until\n    resolved (per the freshness \u00d7 risk matrix below).\n\nNon-protected sibling conflicts may be auto-resolved:\n  When both proposals modify disjoint, non-protected categories, K0 P07 may\n  emit a MERGE_PROPOSAL event suggesting the union as P_M for guardian approval.\n  This is a *suggestion*, never an auto-commit.\n```\n\nNo-authorized-signer fallbacks:\n\n```text\nCase 1: Single-guardian household, signer device lost / unreachable.\n  - Constitution stays at last ACTIVE version. No amendments possible.\n  - Recovery path: device pairing via factory_reset_household OR by adding a\n    new guardian device through the device-pairing flow (requires the original\n    recovery secret captured at household onboarding).\n\nCase 2: Multi-guardian household, one guardian unreachable for an extended period.\n  - Routine amendments still proceed (1-of-N quorum where allowed).\n  - Protected-category amendments are blocked unless the C.governance section\n    declared a fallback quorum at onboarding (e.g., \"1 guardian + 7-day waiting\n    period if the other guardian is unreachable\"). V0 default is NO fallback;\n    households must opt in at onboarding.\n\nCase 3: All guardians unavailable (incapacitation, emergency).\n  - V0 has no \"escalate to a non-guardian\" path. The constitution is frozen at\n    the last ACTIVE version. The system continues operating under that version.\n  - C.emergency_policy may permit specific safety-sensitive *actions* (call\n    contact, share location) to a designated non-guardian, but those actions\n    cannot amend C.\n  - Recovery requires household reset with the onboarding recovery secret OR\n    manual support flow (out of scope for V0).\n```\n\nAudit invariants for amendments:\n\n```text\n- Every amendment proposal is recorded from DRAFT onward, even if REJECTED.\n- Signatures are append-only; a signature cannot be silently removed.\n- The body_hash chain (parent_version -> version) is the canonical history.\n- An ACTIVE constitution always has a complete signer chain back to the\n  bootstrap signers from household onboarding.\n```\n\n### Memory Citation Direction

The LLM should receive evidence handles, not the whole memory lake.

```text
Recall result -> CitationPack

CitationPack:
  c1: short summary, source layer, confidence, freshness, privacy band
  c2: short summary, source layer, confidence, freshness, privacy band
  c3: short summary, source layer, confidence, freshness, privacy band

Hidden behind handle:
  raw memory text
  full episode
  embeddings
  long provenance chain
```

Prompt rule:

```text
Give the LLM at most 3-5 compact citations for normal turns.
Use citation handles like [m:c1], [m:c2].
Let the LLM ask for more through `recall_memory` only if needed.
Never include RED/raw child-sensitive text unless policy explicitly allows it.
```

#### Citation Schema (V0)

The "compact citation" shape is normative. Every recall result that surfaces to the LLM uses this shape.

```json
{
  "handle":         "m:c1",
  "summary":        "Liam's school pickup is normally Dad on Tuesdays",
  "source_layer":   "procedural",
  "subject":        "child_1",
  "privacy_band":   "AMBER",
  "confidence":     0.82,
  "freshness":      "fresh",
  "observed_at_ms": 1777700000000,
  "audience_ok":    true
}
```

Field rules:

```text
handle         : opaque, stable for the turn; format "m:cN".
summary        : <= 140 chars, redacted to actor's privacy ceiling, no raw RED text.
source_layer   : episodic | semantic | procedural | social | prospective | graph.
subject        : member_id, "family", or "household". Used for sibling-privacy checks.
privacy_band   : effective band of the underlying memory (not the actor's ceiling).
confidence     : float 0..1 from the recall layer.
freshness      : fresh | stale | offline_cached  (matches projection freshness states).
observed_at_ms : when the memory was last observed/consolidated.
audience_ok    : true if SituationFrame already verified this citation
                 against actor visibility; LLM may quote summary verbatim.
                 false if citation is shown but should not be paraphrased
                 outward without re-check (rare; defensive).
```

Token budget per turn:

```text
3-5 citations default (briefing/answer turns)
1-2 citations preferred (chit-chat / clarification turns)
10 hard ceiling (deep planning turns; requires explicit Planner intent)

Approx token cost per citation: ~80-120 tokens.
Total capsule citation budget: <= 600 tokens for a normal turn.
```

#### Fetching Behind a Handle

The LLM does not get raw memory by default. It can request expansion through the existing `recall_memory` tool, with the handle as a parameter.

```text
LLM call: recall_memory(handle="m:c1", expand="snippet")
  -> returns: short snippet (<= 400 chars), still policy-filtered.

LLM call: recall_memory(handle="m:c1", expand="full")
  -> returns: full memory text IF policy allows;
     otherwise returns redacted form + reason_code.

LLM call: recall_memory(query="...", limit=N)
  -> classic recall path; returns a fresh CitationPack.
```

Expansion rules:

```text
GREEN citation     -> snippet/full freely allowed.
AMBER citation     -> snippet allowed if subject in actor's allowed_target_members;
                      full requires audience match AND no cross-member sharing.
RED citation       -> snippet only with explicit policy permit;
                      full almost never; requires confirmation flow.
BLACK citation     -> never expanded; never crossed K1 boundary in the first place.
```

#### Interaction with Existing `recall_memory` Tool

```text
recall_memory                          (already exists in front/back tool schemas)
  |
  v
IMemoryPort                            (port discipline)
  |
  v
BridgeRecallAdapter                    (existing)
  |
  v
K0 recall                              (existing)
  |
  v
CitationPackBuilder    <-- NEW         (filters + shapes results into citation schema)
  |
  v
GroundingCapsule.k0_recall.citations
```

The existing tool stays. The new piece is the **CitationPackBuilder** that wraps the recall response into the normative citation schema before it ever reaches the LLM. Raw recall payloads must not bypass this builder.

#### Citation Lifetime

```text
Handles are turn-scoped by default.
  m:c1 in turn N is not the same memory as m:c1 in turn N+1.
  The capsule re-keys handles each turn to avoid stale references.

A handle may be promoted to session-scoped if explicitly pinned
  (e.g., active planning thread). Pinned handles get prefix "m:p1".
  Pinned set is bounded (default 8) and visible in the capsule.
```

### Offline / Stale Fallback Direction

K1 should remain useful offline, but it must be honest about freshness.

```text
fresh:
  normal recall/tool policy

stale:
  allow low-risk local reads/writes
  mark grounding capsule: memory_freshness=stale
  require confirmation for cross-member writes
  deny or defer RED/sensitive changes unless emergency policy allows

offline_local_only:
  local-only operations allowed
  queue writeback/sync
  do not claim K0-confirmed truth
  warn LLM via grounding capsule

conflict_pending:
  read with caution
  block irreversible writes in affected domain
  ask user/parent to resolve if needed
```

#### Freshness Thresholds (V0)

Freshness state is a **function of last successful K0 sync**, evaluated per projection (self / family / constitution). Thresholds are V0 defaults; constitution may tighten but not loosen them.

```text
State                Trigger                                    Default threshold
---------------------------------------------------------------------------------
fresh                last K0 sync ok and recent                 <  5 minutes
stale                last K0 sync ok but aging                  5 min  -  24 hours
offline_local_only   K0 unreachable on last attempt             > 24 hours OR
                     OR last sync attempt failed > 3 retries       last sync failed
conflict_pending     K0 reported unresolved conflict             until resolved
                     in this projection
```

Per-projection overrides:

```text
self_projection         : same as defaults above.
family_projection       : tighter   (fresh < 2min, stale 2min-1h, offline_local_only > 1h)
                          because copresence / hub_state moves faster.
constitution_projection : looser    (fresh < 1h,  stale 1h-7d,   offline_local_only > 7d)
                          because C changes are infrequent and signed.
```

Freshness evaluation runs on every grounding-capsule build. It is not a background thread; it is a pure function of `last_k0_sync_at_ms` and `now_ms`.

#### "Low-Risk" Definition

"Low-risk" is **not** an LLM judgement. It is a per-tool declared property in the tool contract, gated by hard category rules.

```text
risk_class is one of: low | medium | high | safety_sensitive

Low-risk (auto-allowed in stale state):
  - read self projection
  - read own GREEN routines/reminders/tasks
  - write to actor's OWN low-impact domain
      (own reminder, own note, own task completion, own preference)
  - read family-public household info

Medium-risk (requires confirmation in stale state, allowed when fresh):
  - read another member's AMBER context (within actor's allowed scope)
  - write to a shared low-impact domain (family grocery list)
  - assign a task to another member
  - calendar writes affecting another member

High-risk (deferred or denied in stale state, allowed when fresh + confirmed):
  - external messages
  - recurring automation creation
  - bulk edits across members
  - any constitution amendment

Safety-sensitive (deferred or denied in any non-fresh state, except emergency policy):
  - health / medication / medical appointment
  - finance / payment / budget
  - location sharing / pickup / custody
  - child account authority changes
  - device pairing / unpairing
  - RED memory operations
```

Mapping risk class × freshness state → default verdict:

| Risk \ State | fresh | stale | offline_local_only | conflict_pending |
| --- | --- | --- | --- | --- |
| low | ALLOW | ALLOW (capsule marked stale) | ALLOW (queue writeback) | ALLOW if not in affected domain |
| medium | ALLOW | REQUIRE_CONFIRMATION | REQUIRE_CONFIRMATION + queue | DENY in affected domain, else ALLOW |
| high | REQUIRE_CONFIRMATION | DEFER_OFFLINE | DEFER_OFFLINE | DENY |
| safety_sensitive | REQUIRE_CONFIRMATION | DEFER_OFFLINE (emergency: ALLOW + audit) | DEFER_OFFLINE (emergency only) | DENY |

The constitution may **tighten** any cell (e.g., move "medium / fresh" from ALLOW to REQUIRE_CONFIRMATION), but cannot loosen safety-sensitive cells.

#### Override Policy

User override exists, but is constrained.

```text
Who may override?
  - The actor for their OWN low/medium-risk action.
  - A guardian for a high-risk action they own.
  - Nobody for safety-sensitive actions in offline_local_only or conflict_pending,
    except via the constitution's emergency_policy path.

How override is expressed:
  - The capsule shows the verdict reason and a "proceed anyway" prompt for
    eligible cells only.
  - Override is logged to the audit trail with reason_code = USER_OVERRIDE_STALE
    and the freshness state at decision time.
  - Override does not change the tool result's freshness marker; the receipt
    still says the action was taken on stale projection.

What override cannot do:
  - Cannot promote a DENY to ALLOW.
  - Cannot bypass identity tier requirements.
  - Cannot skip signing for a constitution amendment.
  - Cannot reach K0 when K0 is unreachable; queue still applies.
```

Emergency policy carve-out:

```text
C.emergency_policy may name explicit safety-sensitive actions that ALLOW under
offline_local_only when actor is a guardian and a brief reason is captured.
Default contents:
  - call emergency contact
  - share live location with named guardian
  - access medication info for own dependent
Every emergency invocation is audit-logged and surfaced for guardian review
when K0 connectivity returns.
```

#### Freshness in the Grounding Capsule

The capsule already has a `freshness` block. V0 makes it explicit per projection so the LLM and the dispatcher see the same numbers:

```json
{
  "freshness": {
    "self_projection":         {"state": "fresh", "age_ms":     45000},
    "family_projection":       {"state": "stale", "age_ms":   3600000},
    "constitution_projection": {"state": "fresh", "age_ms":    600000},
    "k0_reachable":            true,
    "last_k0_sync_at_ms":      1777777732000,
    "queued_writes":           0
  }
}
```

The LLM is instructed to mention staleness in user-visible language only when a verdict was affected by it ("I can do this, but I haven't synced with the family in about an hour — want me to go ahead?"). It must not pad every reply with freshness chatter.

### Parent Confirmation Direction

Even a parent should confirm high-impact actions. Proposed v0 confirmation list:

```text
Always confirm:
  constitution changes
  device pairing / child account authority changes
  school pickup or custody-sensitive changes
  health/medication/doctor changes
  finance/payment/budget transfers
  external messages sent outside the family
  sharing child location or RED memory
  deleting or overwriting shared family records
  actions affecting another caregiver's responsibility

Usually confirm:
  calendar writes involving another member
  reminder/task assignment to another person
  proactive recurring workflows
  bulk edits or automations

Can auto-allow when policy permits:
  parent edits own low-risk reminder
  parent reads shared GREEN/AMBER household context
  child completes own chore
```

### POC Testing Surface Direction

`poc/k1_poc` is a broad proving surface, not a minimal one. It has real UI/LLM bootstrap behavior, so the testing strategy should be layered:

```text
Layer 1: deterministic unit tests for policy verdicts
Layer 2: scripted Concierge/ToolDispatcher behavior tests
Layer 3: poc/k1_poc UI + real LLM exploratory runs
Layer 4: production Concierge kernel integration tests
```

The POC should prove experience and behavior. The deterministic tests should prove invariants cheaply.

## V0 Family Situation Design

The next design step is not a service, schema, or dispatcher gate. Those are downstream. The first useful unit is a family situation: a real moment where FamilyOS must decide who is speaking, who is affected, what can be seen, what can be changed, and whether the system should ask before acting.

The design order is:

```text
Family situation
  |
  v
What FamilyOS must understand
  |
  v
What the constitution must decide
  |
  v
Private / shared / confirm-required / forbidden classification
  |
  v
Executable policy
  |
  v
Service, storage, prompt, and tool contracts
```

### V0 Situation Matrix

| Situation | Model must know | Constitution must decide | Default classification |
| --- | --- | --- | --- |
| Child asks: "What do I need to do today?" | Child identity, personal device or shared device proof, own tasks, school schedule, chores, age band, visible routines | Child may read own routine obligations; child may not see sibling/private caregiver notes; child may complete own allowed chores | Shared with subject child and caregivers; no confirmation for read; confirm or parent-approve schedule changes |
| Parent asks: "What does Liam need today?" | Parent identity, caregiver relationship, Liam's visible schedule/tasks/routines, sensitive categories, freshness | Caregiver can view child routine context; health/school-sensitive details may be summarized or require stronger scope | Shared with authorized caregiver; RED details constrained; confirmation only for writes/actions |
| Shared hub hears: "Remind me to pack my cleats." | Active speaker unknown, device is shared, possible members with cleats/sports, ambiguity level | Unknown hub cannot create private/member-specific reminder without identity; may ask who the reminder is for | Confirm identity or target profile before write; public-only until resolved |
| Parent changes pickup plan | Actor caregiver identity, target child, current pickup responsibility, other caregiver involvement, school/custody sensitivity | Pickup/custody-sensitive changes require confirmation and may notify affected caregiver | Confirm-required; audit; never silent automation |
| Child completes or disputes a chore | Child identity, chore owner, assignment source, allowed completion/dispute behavior, conflict state | Child can complete own chore; dispute may notify caregiver; sibling chore mutation denied | Own chore completion allowed; dispute shared with caregivers; sibling mutation forbidden |
| Parent asks: "Why are mornings chaotic?" | Morning routines, repeated delays, school/work obligations, recent patterns, family-visible context, privacy-safe summaries | Pattern analysis may use family routine data but should avoid exposing private child/parent-sensitive causes without scope | Shared household summary allowed; sensitive citations hidden; memory write only if approved or pattern-safe |
| Child asks about sibling's appointment | Asking child identity, sibling subject, appointment category, public vs private status | Sibling routine/public events may be visible; health/therapy/discipline/private appointments denied or redacted | Usually denied/redacted unless family-public; no hidden inference |
| FamilyOS detects schedule or responsibility conflict | Affected members, event sources, responsibility owners, freshness, conflict severity | Low-risk conflicts can be surfaced; safety-sensitive conflicts require caregiver confirmation before changes | Shared with responsible caregivers; confirmation before writes; conflict audit |
| Parent creates recurring routine | Parent identity, affected members, recurrence, burden on children/caregivers, notification scope | Parent can create household routine; affected members may be notified; intrusive/proactive behavior has limits | Usually confirm before recurring automation; shared according to routine scope |
| Someone asks FamilyOS to remember a family preference | Speaker identity, preference subject, scope: self/family/child/sensitive, durability, who can rely on it | Self preferences can be remembered for self; family-wide or child-affecting preferences need explicit scope/approval | Ask whether one-time, personal, or family rule; never infer sensitive durable memory silently |
| Child wants privacy from sibling while caregiver safety remains | Child identity, sibling audience, caregiver audience, content category, safety implications | Sibling privacy is respected by default; caregiver visibility depends on safety/category/age policy | Private from siblings; caregiver-visible for safety categories; no broad family sharing |

### What The Model Must Understand

The model is not just identity plus permissions. It is a projection of a person inside a household.

```text
Person-in-family model
  identity
  role and age/development band
  device context
  care relationships
  autonomy level
  privacy expectations
  communication needs
  routines and obligations
  preferences and sensitivities
  consent and memory boundaries
  current context and freshness
```

For every turn, FamilyOS should derive a situation frame:

```text
SituationFrame
  actor_member_id
  subject_member_id
  device_context
  relationship(actor, subject)
  action_kind: read | write | share | remember | automate | message
  domain: routine | school | health | finance | location | chore | calendar | preference
  sensitivity: public | family_private | subject_private | safety_sensitive
  freshness: fresh | stale | offline_local_only | conflict_pending
```

This is the bridge between lived family context and later executable policy.

### What The Constitution Must Decide

The constitution is the household operating agreement. It should decide categories and boundaries, not micromanage every object.

```text
Family constitution decides:
  who can see which categories of information
  who can act for whom
  what children can do independently
  what caregivers may see or change
  what always requires confirmation
  what FamilyOS may remember durably
  what should stay temporary or expire
  when FamilyOS may interrupt or be proactive
  how device conflicts are resolved
  what happens when K0 is stale/offline
  what happens in urgent situations
```

Example constitution defaults:

```text
Children can read their own routine obligations.
Children cannot read sibling private appointments or sensitive notes.
Caregivers can read child routine/school context when authorized.
Health, therapy, discipline, finance, custody, and location are sensitive by default.
Shared hubs start public-only until identity is known.
External messages and pickup changes require confirmation.
FamilyOS may suggest new rules but cannot silently create them.
```

### Privacy Cannot Be A Settings Wall Or A Guess

This is the critical design point.

```text
Bad path:
  Ask families to configure every privacy edge in settings.
  Result: setup fatigue, mistakes, and low trust.

Bad path:
  Infer private/shared/forbidden purely from conversation.
  Result: unsafe hidden decisions about family privacy.
```

The v0 path should be layered:

```text
Conservative defaults
  |
  v
Situation templates
  |
  v
Small contextual questions only at boundary crossings
  |
  v
Suggested rules from observed patterns
  |
  v
Parent/guardian approval for durable constitution changes
```

The product should feel like guided family onboarding plus contextual clarification:

```text
"Should siblings see each other's chores?"
"Should health appointments be visible only to caregivers?"
"Can this hub create reminders for anyone, or only after a profile is selected?"
"Should I remember this as a one-time preference, your preference, or a household rule?"
```

Inferred behavior can become a candidate, not authority:

```text
Conversation pattern
  |
  v
Candidate preference or rule
  |
  v
Parent/guardian approval when shared, child-affecting, or sensitive
  |
  v
Constitution/projection update
```

### First Product Principle

FamilyOS should make the safe default obvious and ask only when the family crosses a real boundary.

```text
No giant settings wall.
No silent privacy inference.
No LLM-only authority.
No hidden sharing.
No irreversible family action without the right person confirming.
```

## V0 Family Operating Design

This section turns the family-situation direction into v0 product and policy design. The goal is to make FamilyOS helpful without becoming either a settings-heavy admin panel or an overconfident system that guesses household boundaries.

The core behavior loop is:

```text
User asks or acts
      |
      v
FamilyOS identifies the situation
      |
      v
Use conservative defaults
      |
      v
Do the safe part immediately
      |
      v
If a boundary is crossed, ask one small question
      |
      v
If a pattern repeats, suggest a rule
      |
      v
If an authorized person approves, update constitution/projection
```

Design mantra:

```text
Be useful by default.
Be humble at boundaries.
Never turn inference into authority.
Never make privacy invisible.
```

### 1. Final V0 Situation Set

The v0 situation set should prove the hard family axes without trying to cover every possible tool domain.

Final v0 situations:

| ID | Situation | Why it matters |
| --- | --- | --- |
| S1 | Child asks: "What do I need to do today?" | Proves child-scoped read, routine visibility, age-appropriate response, and own-task autonomy. |
| S2 | Parent asks: "What does Liam need today?" | Proves caregiver authority, child routine visibility, and sensitive detail handling. |
| S3 | Shared hub hears: "Remind me to pack my cleats." | Proves unknown speaker handling, ambiguity resolution, and no private write without identity. |
| S4 | Parent changes pickup or responsibility plan. | Proves high-impact confirmation, caregiver notification, audit, and conflict handling. |
| S5 | Child completes or disputes a chore. | Proves child autonomy, own-action writes, dispute escalation, and sibling boundaries. |
| S6 | Parent asks: "Why are mornings chaotic?" | Proves pattern analysis without exposing sensitive memory raw material. |
| S7 | Child asks about sibling's appointment or task. | Proves sibling privacy and safe redaction instead of broad denial. |
| S8 | FamilyOS detects a schedule/responsibility conflict. | Proves proactive surfacing, stale/conflict state, and safe resolution rules. |
| S9 | Parent creates a recurring routine. | Proves recurring automation confirmation and affected-member visibility. |
| S10 | Someone asks FamilyOS to remember a family preference. | Proves memory scope, one-time vs durable rule, and approval for shared/child-affecting memory. |
| S11 | Child says: "Don't tell my sibling." | Proves sibling privacy, caregiver safety boundary, and explicit audience handling. |
| S12 | Parent asks: "What should I know before school pickup?" | Proves context briefing, school/pickup sensitivity, and caregiver-scoped recall. |
| S13 | Child asks: "Can I go to Maya's house?" | Proves child request flow, guardian approval, location/social safety, and not auto-deciding. |

V0 should not begin with every domain tool. It should begin with these situations because they force the right model:

```text
actor
subject
device
relationship
action kind
sensitivity
freshness
authority
memory scope
confirmation boundary
```

### 2. Privacy Category Defaults

Privacy should be category-based and situation-based, not a giant edge-by-edge settings graph.

Default categories:

| Category | Default audience | Examples | Default behavior |
| --- | --- | --- | --- |
| Family-public | All identified family members; shared hub may show safe summaries | Shared grocery list, public family event, public chore board, non-sensitive household routine | Show without confirmation; avoid personal details on unknown shared hub. |
| Subject + caregivers | Subject member and authorized caregivers | Child school schedule, child routine tasks, pickup logistics, own reminders | Show to subject/caregiver; hide from siblings unless marked family-public. |
| Caregiver-only sensitive | Authorized caregivers; sometimes subject depending age/safety | Health, therapy, discipline, legal/custody, finance, location history | Do not show to siblings/shared unknown; confirm before sharing or external send. |
| Personal-private | Subject only unless explicitly shared or safety policy applies | Journal-like notes, private emotional disclosures, personal preferences | Keep private; ask before durable memory; escalate only for safety categories. |
| Household rule/preference | Authorized adults can approve; visible according to rule | Dinner protected time, chore board visibility, family communication norm | Must be explicit if durable and family-wide. |
| Never-store / ephemeral | No durable memory | Secrets, one-off sensitive disclosures, temporary conflict details when user declines memory | Use only for current turn/session; do not write to K0 durable memory. |

Ambiguous examples should default conservatively:

| Item | Default classification | Notes |
| --- | --- | --- |
| Chore assignment | Family-public or subject + caregivers | Public if on shared chore board; otherwise subject-scoped. |
| Chore completion history | Subject + caregivers | Do not expose as sibling comparison by default. |
| School reminder | Subject + caregivers | Public only if explicitly shared family event. |
| Friend plan | Subject + caregivers for children | May need parent approval depending age/location. |
| Behavior note | Caregiver-only sensitive | Never sibling-visible by default. |
| Food preference | Personal or household preference | Ask if personal, child-specific, or household rule. |
| Sleep pattern | Subject + caregivers or sensitive | Treat carefully for children/health implications. |
| Pickup/location | Caregiver-only sensitive | Confirm changes and external sharing. |
| Parent-child message | Participants only by default | Do not turn into family-public memory without approval. |

Redaction pattern:

```text
Answer safe part.
Hide private part.
Explain simply.
Offer identity/approval path only if appropriate.
```

Example:

```text
Child: "What is Ava doing today?"

FamilyOS:
  "I can show family-public plans. Ava has soccer after school.
   Private appointments are only visible to Ava and caregivers."
```

### 3. Infer vs Suggest vs Remember

FamilyOS can notice patterns, but it cannot make household law from them.

Inference ladder:

```text
May infer for this turn
      |
      v
May suggest as candidate preference
      |
      v
May remember after explicit approval
      |
      v
May become household rule only after authorized approval
```

Decision table:

| System behavior | Allowed? | Rule |
| --- | --- | --- |
| Infer likely referent for one turn | Yes, if low risk | Ask when ambiguous or when action affects another person. |
| Infer tone/communication preference | Yes, low risk | Can adapt response style; cannot grant authority. |
| Infer private/shared boundary | No | Must use defaults or ask. |
| Suggest a durable preference | Yes | Present as suggestion, not fact. |
| Remember personal preference | Yes, with user approval or low-risk explicit request | Scope to that person unless family-wide approval exists. |
| Remember child-affecting preference | Only with caregiver/allowed subject policy | Ask who it applies to and who can see it. |
| Create household rule | Only authorized adult/guardian approval | Never silently from conversation. |
| Store sensitive memory | Only explicit scope and policy allow | Offer ephemeral/no-store option. |

Examples:

```text
"Liam keeps asking about soccer."
  Allowed: infer soccer may be relevant this turn.
  Allowed: suggest "Should I remember soccer as Liam's interest?"
  Not allowed: silently create a durable family rule.

"She gets anxious before school."
  Allowed: use if explicitly provided and relevant.
  Required: treat as sensitive.
  Not allowed: expose broadly, label clinically, or silently share.
```

Memory scope prompt:

```text
"Should I remember this just for you, for Liam, or as a household preference?"
```

Sensitive memory prompt:

```text
"This sounds personal. Should I keep it only for this conversation,
remember it privately for you, or not remember it at all?"
```

Memory durability categories:

```text
one_turn_context
session_memory
temporary_family_note
durable_personal_preference
durable_child_note
durable_household_preference
constitution_rule_candidate
sensitive_memory_with_expiry
never_store
```

### 4. Constitution Onboarding Style

The constitution should feel like guided household setup plus contextual refinement, not a compliance form.

Onboarding should ask a small number of high-leverage questions:

```text
Who are the adults/guardians?
Which devices are personal and which are shared?
Should shared devices start public-only until someone chooses a profile?
Should siblings see each other's chores on a shared board?
Should health, school-sensitive, location, and discipline details be caregiver-only by default?
Should FamilyOS ask before sending messages outside the family?
How often may FamilyOS proactively nudge family members?
Should child routines encourage independence before escalating to parents?
```

Everything else should be contextual:

```text
"Should this become a household rule?"
"Should this stay private to you?"
"Should caregivers be able to see this?"
"Should this expire after this week?"
"Is this a one-time exception or a new routine?"
```

Onboarding layers:

```text
Initial family setup
  guardians, members, devices, shared hub posture
      |
      v
Safety defaults
  health/location/custody/external messages/proactivity
      |
      v
Situation-based refinements
  asked only when a real boundary appears
      |
      v
Review queue
  approve/edit/ignore/expire suggested rules
```

Review queue pattern:

```text
FamilyOS noticed:
  - Dinner time is usually protected from reminders.
  - Chores are usually visible on the shared board.
  - Health appointments are only discussed with caregivers.

Actions:
  Approve
  Edit
  Ignore
  Expire
```

This lets the constitution evolve without becoming hidden drift.

### 5. Shared Hub Identity Tiers

Shared hub behavior is the sharpest privacy edge. It should be useful while unknown, but never private or side-effecting by default.

| Tier | Identity state | Allowed | Denied / requires step-up |
| --- | --- | --- | --- |
| Tier 0 | Unknown speaker | General chat, public household info, harmless suggestions, public family routine summaries | Private recall, member-specific writes, external messages, health/school/finance/location details |
| Tier 1 | Profile selected or lightweight proof | Member's own non-sensitive reminders/tasks/calendar, own routine reads, low-risk local actions | RED/sensitive recall, external sends, caregiver actions, cross-member writes |
| Tier 2 | Strong member proof | Private member context within policy, member-specific writes, more complete personal context | Guardian-only actions and high-impact changes |
| Tier 3 | Guardian proof | Caregiver actions, child-sensitive changes, external sends after confirmation, constitution changes if authorized | Second-adult actions if configured; custody/legal constraints |

Voice recognition direction:

```text
Voice can be advisory for routing and UX.
Voice should not unlock private recall or side-effecting tools in v0.
Private or side-effecting actions need profile/PIN/passkey/OS biometric/guardian approval.
```

#### V0 Identity Resolution Mechanism

The tier system above answers "what is allowed at each identity level." This subsection answers "how does a shared hub move between tiers." V0 commits to a concrete, ship-able mechanism; richer modalities can layer on later.

V0 mechanism stack (from lowest to highest):

```text
M0  Implicit Tier 0 (no proof)
      -> Default state on every shared-hub turn until proof exists.
      -> No prompt, no UI, no LLM question. Hub just operates in public-only scope.

M1  UI Profile Picker  (lightweight proof for Tier 1)
      -> Always-visible row of family member avatars on the shared hub home surface.
      -> Tap-to-select makes that profile the active speaker for the session.
      -> Times out after 30min inactivity OR explicit "end session" tap.
      -> Optional 4-digit PIN per profile (default off for adults, default on for teens/children
         when constitution is configured for child-protected hubs).

M2  PIN / Passkey  (strong proof for Tier 2)
      -> Required when an action escalates beyond Tier 1 scope mid-session.
      -> Inline step-up: hub shows the prompt, action waits, no LLM rerun needed.
      -> Passkey preferred when device supports it; PIN is the fallback floor.

M3  Guardian Proof  (Tier 3)
      -> Same as M2 but the resolved member must hold guardian authority in C.
      -> For configured high-impact actions, two-adult co-confirmation is required
         (one adult on the hub, second adult acknowledges via their personal K1).

ADVISORY  Voice / Face / Presence sensors
      -> Always advisory in v0. They can pre-select a profile in the picker
         ("Is this Mom?") and bias routing, but cannot unlock Tier 1+ alone.
      -> The picker tap or PIN is what actually moves the tier.
```

Who asks the question — LLM or UI:

```text
LLM never asks "who is speaking?" as its first move on a shared hub.
The picker is a UI affordance, not a conversational turn.

LLM may say:
  "I can answer that for the family generally. If you tap your profile,
   I can show your private items too."

LLM must not say:
  "Please tell me your name."  (untrusted self-identification)
  "Are you Mom?"                (suggestible; biases the answer)
```

This keeps identity resolution **out-of-band from the LLM**. The conversation can hint at scope, but tier transitions happen through trusted UI, not chat.

Resolution flow on shared hub:

```text
+---------------------------+
| Shared hub idle / new turn |
+-------------+-------------+
              |
   advisory sensors fire? (voice, face)
              |
     yes -----+----- no
      |              |
      v              v
  pre-select       picker
  in picker        shows neutral
  (still Tier 0)   (Tier 0)
      |              |
      +------+-------+
             |
             v
   user taps profile?  ----- no -> stay Tier 0, public-only response
             |
            yes
             v
   profile requires PIN/passkey?
             |
     no ----+---- yes
      |           |
      v           v
   Tier 1     prompt for PIN/passkey
               |
           success / fail
               |
        success -> Tier 2 if guardian -> Tier 3
        fail    -> stay Tier 0
```

Session lifecycle on shared hub:

```text
Profile tap                 -> Tier 1 active, session started
+ PIN success               -> Tier 2 (or Tier 3 if guardian)
30min inactivity            -> session ends, drop to Tier 0
Explicit "sign out" tap     -> session ends, drop to Tier 0
Device handoff (face change
  detected by advisory)     -> session pauses, picker reappears, drop to Tier 0
                               until next tap (do not auto-promote)
```

Why this is the right v0 floor:

```text
- Boring: profile picker + PIN is well understood by every household.
- Safe: untrusted modalities (voice, face) cannot unlock private context alone.
- Honest: the LLM never has to *guess* who is speaking; tier is set out-of-band.
- Layerable: passkey, biometric, and richer multi-modal arbitration can be added
  without changing the tier semantics or the SituationFrame composer.
```

### 6. Child Autonomy Rules

FamilyOS should help children grow independence without turning every child action into surveillance.

Autonomy should vary by age/development band, family constitution, and domain sensitivity.

Default autonomy levels:

| Actor | Can do alone by default | Needs approval | Forbidden by default |
| --- | --- | --- | --- |
| Child | Read own routine tasks, complete own chore, create own low-risk reminder, ask for help | Snooze/change due date, message outside family, change shared plan, create recurring automation | Access sibling private context, delete caregiver-created records, change pickup/location/health/school-sensitive plans |
| Teen | Child permissions plus more personal scheduling and private preferences, within household policy | Location sharing, external sends, school/health-sensitive changes, recurring automations affecting others | Sibling/parent private context, caregiver-only records, custody/legal/finance changes |
| Parent/guardian | Read/act within caregiver scope, approve child-affecting rules, manage routines | High-impact actions, external messages, health/pickup/location/custody/finance changes | Silent override of another authorized caregiver where constitution requires conflict resolution |
| Guest/babysitter | Assigned temporary responsibilities and public household info | Child-sensitive changes, external messaging, private recall | Constitution changes, durable memory writes, finance/legal/custody/health decisions |

Child privacy principle:

```text
Children deserve privacy from siblings by default.
Caregiver visibility exists for safety, care, and responsibility, not curiosity.
FamilyOS should not make private child disclosures family-public.
```

Escalation principle:

```text
Encourage independence first for low-risk routine tasks.
Ask caregiver approval for boundary-crossing actions.
Escalate immediately only for safety-sensitive situations.
```

Examples:

```text
Child completes own chore:
  allow, optionally notify caregiver or update board.

Child deletes assigned chore:
  require caregiver approval or create dispute.

Teen creates private study reminder:
  allow as personal memory/reminder.

Teen shares live location externally:
  require confirmation and policy check.

Child asks private emotional question:
  keep private by default unless safety policy requires escalation.
```

### Helpful Without Overconfidence

FamilyOS should behave less like an admin panel and less like an oracle, and more like a careful household participant.

```text
Not:
  "Configure 80 privacy settings before using FamilyOS."

Not:
  "I inferred your family boundaries from chat history."

But:
  "I can help now using safe defaults. When something affects privacy,
   another person, memory, or outside communication, I will ask a small,
   specific question."
```

The useful middle path is:

```text
Default conservatively.
Act locally when safe.
Ask only at meaningful boundaries.
Turn repeated answers into suggestions.
Require explicit approval before changing durable family rules.
```

Boundary triggers:

```text
another person is affected
private information might be revealed
a memory may become durable
an external message may be sent
a routine/automation may repeat
a child/school/health/location topic appears
a shared device has unknown speaker
```

Household-language explanations:

```text
Instead of:
  "Denied by PolicyVerdict.REQUIRE_IDENTITY due to AMBER subject scope."

Say:
  "I need to know who is using the hub before showing Liam's private schedule."

Instead of:
  "Confirmation required for external connector side effect."

Say:
  "This would send a message to Dad, so I need you to confirm first."
```

The resulting experience:

```text
Safe ordinary tasks feel immediate.
Private or durable boundaries feel visible.
Family rules evolve by approval, not hidden inference.
The system can explain why it asks.
```

## Appendix: E0 Self Model Substrate Compilation Target

This section is a later compilation target. It should not drive the design by itself. Once the v0 family situations and constitution defaults feel right, these contracts can become the implementation shape for Concierge, prompt grounding, policy evaluation, and tool gating.

### E0 Runtime Shape

```text
Session / device input
        |
        v
+--------------------+
| SelfModelService   |
+---------+----------+
          |
          | immutable runtime snapshot
          v
+--------------------------+
| GroundingCapsuleBuilder  |
+------------+-------------+
             |
             | prompt-safe capsule
             v
+---------------------+        +---------------------+
| DynamicPromptBuilder|------->| Front / Back LLM    |
+---------------------+        +----------+----------+
                                           |
                                           | tool call
                                           v
                                +---------------------+
                                | ToolDispatcher      |
                                | step 0 policy gate  |
                                +----------+----------+
                                           |
                                  ALLOW / DENY / HITL
                                           |
                                           v
                                Fabric / tools / K0 ports
```

### 1. Data Models

E0 should define typed models that are compact, serializable, and stable enough for tests.

```text
K1SelfModel
  self_id
  member_id
  family_space_id
  tenant_id
  device_id
  display_name
  role
  age_band
  authority_level
  active_presence
  privacy_band
  memory_scope
  constitution_version
  projection_revision
  freshness
  confidence

FamilySelfModel
  family_space_id
  household_name
  members[]
  relationships[]
  routines[]
  shared_preferences[]
  constitution_id
  projection_revision
  freshness

FamilyConstitution
  constitution_id
  family_space_id
  version
  authority_rules[]
  privacy_rules[]
  tool_rules[]
  memory_rules[]
  confirmation_rules[]
  proactive_rules[]
  signer_device_id
  signature
  effective_at_ms

GroundingCapsule
  active_self
  family_context
  constitution_summary
  memory_scope
  tool_scope
  freshness
  local_state_refs

PolicyVerdict
  decision
  reason_code
  user_message
  required_confirmation
  required_identity_level
  audit_required
  memory_write_policy
```

The data model boundary should be boring and explicit. No prompt prose should be the source of identity, authority, or privacy rules.

### 2. Storage / Projection Schema

E0 storage should be local-first and projection-oriented. It does not need to solve final K0 KG schema.

```text
+------------------------------+
| K1 local projection store     |
+------------------------------+
| self_projection               |
| family_projection             |
| constitution_projection       |
| projection_sync_state         |
+------------------------------+
```

Suggested local tables:

```text
self_projection
  self_id TEXT PRIMARY KEY
  member_id TEXT NOT NULL
  family_space_id TEXT NOT NULL
  tenant_id TEXT NOT NULL
  device_id TEXT NOT NULL
  role TEXT NOT NULL
  age_band TEXT NOT NULL
  authority_level TEXT NOT NULL
  active_presence TEXT NOT NULL
  privacy_band TEXT NOT NULL
  memory_scope_json TEXT NOT NULL
  constitution_version TEXT NOT NULL
  projection_revision TEXT NOT NULL
  freshness TEXT NOT NULL
  updated_at_ms INTEGER NOT NULL

family_projection
  family_space_id TEXT PRIMARY KEY
  household_name TEXT NOT NULL
  members_json TEXT NOT NULL
  relationships_json TEXT NOT NULL
  routines_json TEXT NOT NULL
  shared_preferences_json TEXT NOT NULL
  constitution_id TEXT NOT NULL
  projection_revision TEXT NOT NULL
  freshness TEXT NOT NULL
  updated_at_ms INTEGER NOT NULL

constitution_projection
  constitution_id TEXT PRIMARY KEY
  family_space_id TEXT NOT NULL
  version TEXT NOT NULL
  body_json TEXT NOT NULL
  body_hash TEXT NOT NULL
  signer_device_id TEXT NOT NULL
  signer_public_key_id TEXT NOT NULL
  signature_alg TEXT NOT NULL
  signature TEXT NOT NULL
  sync_state TEXT NOT NULL
  effective_at_ms INTEGER NOT NULL
  updated_at_ms INTEGER NOT NULL

projection_sync_state
  projection_key TEXT PRIMARY KEY
  projection_type TEXT NOT NULL
  projection_revision TEXT NOT NULL
  k0_sync_state TEXT NOT NULL
  last_k0_sync_at_ms INTEGER
  last_k0_event_id TEXT
  conflict_state TEXT NOT NULL
```

Projection freshness values:

```text
fresh
stale
offline_local_only
conflict_pending
unknown
```

Storage flow:

```text
Local write accepted by K1
      |
      v
Update local projection store
      |
      v
Queue Bridge command if syncable
      |
      v
/k0/command.submit topic=sync.delta
      |
      v
K0 st_sync / P07 convergence
      |
      v
SSE k0.sync.complete.v1
      |
      v
Refresh projection_sync_state
```

### 3. Hydration Lifecycle

SelfModel hydration happens at runtime/session start, then per-turn overlays refine it.

```text
ConciergeRuntime starts
      |
      v
Read MetaSection
  session_id, user_id, device_id, privacy_band
      |
      v
Read PersonaSection style + family hints
      |
      v
Load local self/family/constitution projections
      |
      v
Verify freshness + signature where applicable
      |
      v
Return SelfModelRuntimeSnapshot
      |
      v
Concierge/FSM may expose read-only context through single-writer path
```

Per turn:

```text
Turn input
   |
   v
Resolve active presence
   |
   +-- personal device: use known member
   |
   +-- child device: use supervised child member
   |
   +-- shared device: unknown until identity proof
   v
Apply OPP-7 dynamic identity overlay
   |
   v
Build grounding capsule
```

Hydration invariants:

- `SelfModelService` may compute snapshots.
- `SelfModelService` must not directly mutate SessionState outside the existing writer path.
- `PersonaSection` may influence style and family hints only.
- K0 unavailability must not block local hydration if cached projections exist.
- Signature/freshness problems must be visible in the returned snapshot.

### 4. Grounding Capsule Schema

The grounding capsule is what the LLM sees. It is prompt-safe and compact.

```json
{
  "active_self": {
    "member_id": "mom",
    "role": "parent",
    "authority_level": "caregiver_admin",
    "device_id": "mom_phone",
    "active_presence": "personal_device",
    "privacy_band": "AMBER"
  },
  "family_context": {
    "family_space_id": "family_123",
    "household_name": "Kansagra Family",
    "visible_members": ["mom", "dad", "child_1"],
    "visible_relationships": ["mom parent_of child_1"],
    "visible_routines": ["school_morning"]
  },
  "constitution": {
    "version": "v3",
    "summary_rules": [
      "RED actions require confirmation",
      "shared unknown devices cannot access private memories"
    ]
  },
  "memory_scope": {
    "allowed_selectors": ["semantic", "procedural", "social", "graph"],
    "allowed_target_members": ["mom", "child_1"],
    "privacy_band_ceiling": "AMBER",
    "freshness": "fresh"
  },
  "tool_scope": {
    "allowed_tool_ids": ["tool.read.family_context"],
    "requires_confirmation_tool_ids": [],
    "denied_tool_ids": []
  },
  "freshness": {
    "projection_freshness": "fresh",
    "last_k0_sync_at_ms": 1777777777000
  }
}
```

Capsule construction:

```text
SelfModelRuntimeSnapshot
        |
        v
FamilyConstitution policy summarizer
        |
        v
Memory scope calculator
        |
        v
Tool scope calculator
        |
        v
GroundingCapsule
        |
        v
DynamicPromptBuilder scenario data
```

Rules:

- Include IDs and policy summaries, not raw private memory.
- Include freshness markers every time.
- Include only visible members and relationships for the current actor.
- Keep citation handles separate from raw memory content.
- Do not include RED/raw child-sensitive text unless explicitly allowed.

### 5. Policy Verdict Schema

Policy evaluation should return one central verdict shape.

```text
PolicyRequest
  actor_member_id
  device_id
  active_presence
  target_member_id
  action_id
  tool_id
  resource_kind
  requested_privacy_band
  projection_freshness
  k0_freshness_required
  has_identity_proof
  has_confirmation

PolicyVerdict
  decision
  reason_code
  reason_detail
  required_identity_level
  confirmation_prompt
  allowed_memory_scope
  audit_required
  k0_writeback_allowed
  hitl_resume_token
```

Decision enum:

```text
ALLOW
DENY
REQUIRE_CONFIRMATION
REQUIRE_IDENTITY
REQUIRE_PARENT_OR_GUARDIAN
REQUIRE_K0_FRESHNESS
DEFER_OFFLINE
AUDIT_ONLY
```

Policy evaluator shape:

```text
PolicyRequest
      |
      v
+-----------------------------+
| SelfModelAuthorityGate       |
+--------------+--------------+
               |
               v
+-----------------------------+
| ConstitutionPolicyGate       |
+--------------+--------------+
               |
               v
+-----------------------------+
| MemoryScopeGate              |
+--------------+--------------+
               |
               v
          PolicyVerdict
```

Example verdicts:

```json
{
  "decision": "ALLOW",
  "reason_code": "PARENT_READ_FAMILY_CONTEXT",
  "allowed_memory_scope": {
    "privacy_band_ceiling": "AMBER",
    "allowed_target_members": ["family"]
  },
  "audit_required": false
}
```

```json
{
  "decision": "REQUIRE_IDENTITY",
  "reason_code": "SHARED_DEVICE_UNKNOWN_PRIVATE_CONTEXT",
  "required_identity_level": "member_pin_or_passkey",
  "confirmation_prompt": "Please identify who is using the family hub."
}
```

```json
{
  "decision": "DENY",
  "reason_code": "SIBLING_PRIVATE_MEMORY_DENIED",
  "reason_detail": "Child devices cannot access another child's AMBER or RED subject-scoped context."
}
```

### 6. ToolDispatcher Gate Contract

ToolDispatcher step 0 should run before existing schema validation, execution budget, timeout, provider dispatch, and result normalization.

```text
LLM emits tool call
      |
      v
+-------------------------------+
| ToolDispatcher.step0           |
| Build PolicyRequest            |
| Evaluate PolicyVerdict         |
+---------------+---------------+
                |
      +---------+----------+----------------+----------------+
      |                    |                |                |
      v                    v                v                v
    ALLOW                DENY       REQUIRE_IDENTITY  REQUIRE_CONFIRMATION
      |                    |                |                |
      v                    v                v                v
existing dispatch   blocked result   identity flow      HITL approval flow
```

Step 0 inputs:

```text
tool_id
tool_args
current SelfModelRuntimeSnapshot
FamilyConstitution
GroundingCapsule memory/tool scope
projection freshness
session identity state
```

Step 0 outputs:

```text
ALLOW:
  continue existing ToolDispatcher pipeline

DENY:
  return structured blocked result to LLM/FSM

REQUIRE_IDENTITY:
  pause tool execution and ask for identity proof

REQUIRE_CONFIRMATION:
  route through existing HITL/safety approval path

REQUIRE_K0_FRESHNESS / DEFER_OFFLINE:
  block, defer, or ask user to proceed with stale context depending on constitution
```

Blocked result shape:

```json
{
  "status": "blocked",
  "tool_id": "tool.read.family_context",
  "policy_decision": "REQUIRE_IDENTITY",
  "reason_code": "SHARED_DEVICE_UNKNOWN_PRIVATE_CONTEXT",
  "user_message": "I need to know who is using this device before showing private family details."
}
```

Contract rule: domain tools can add domain-specific validation, but they must not invent family authority rules. Central policy gates own self/family/constitution enforcement.

### 7. Test Matrix

E0 tests should be deterministic first, then Concierge-integrated.

```text
+--------------------------+
| Layer 1: policy unit      |
+--------------------------+
          |
          v
+--------------------------+
| Layer 2: ToolDispatcher   |
+--------------------------+
          |
          v
+--------------------------+
| Layer 3: Concierge flow   |
+--------------------------+
          |
          v
+--------------------------+
| Layer 4: POC exploratory  |
+--------------------------+
```

Required test scenarios:

| Scenario | Expected result |
| --- | --- |
| Parent personal device reads family context | Allowed up to constitution privacy ceiling. |
| Child personal device reads own context | Allowed for own GREEN/AMBER visible context. |
| Child personal device reads sibling private context | Denied. |
| Shared hub unknown asks private family question | Requires identity. |
| Shared hub unknown asks harmless public family question | Allowed with public-only context. |
| Parent changes constitution | Requires confirmation and authorized signer. |
| Parent sends external message about child | Requires confirmation. |
| K0 offline with fresh-enough cached projection | Low-risk local reads allowed with stale marker. |
| K0 offline with RED action | Denied or deferred unless emergency policy allows. |
| Projection conflict pending | Irreversible affected writes blocked. |
| Persona says user likes casual tone | Tone changes only; authority unchanged. |
| Tool tries direct recall outside `IMemoryPort` | Fails contract/test. |

Concrete E0 test ladder:

```text
test_policy_parent_read_family_context_allowed
test_policy_child_sibling_private_context_denied
test_policy_shared_unknown_requires_identity
test_grounding_capsule_limits_visible_members
test_grounding_capsule_marks_offline_stale
test_tooldispatcher_step0_blocks_denied_tool
test_tooldispatcher_step0_routes_confirmation_to_hitl
test_concierge_family_context_parent_flow
test_concierge_family_context_child_flow
test_concierge_family_context_shared_unknown_flow
```

### 8. First Proving Tool: `tool.read.family_context`

The first tool should be read-only. It proves identity, memory scope, family projection visibility, grounding, and policy gating without dangerous side effects.

Tool intent:

```text
Return the family context visible to the current actor for this turn.
```

Tool contract:

```yaml
tool_id: tool.read.family_context
side_effects: false
self_model_policy:
  requires_identified_actor: false
  shared_unknown_allowed: true
  public_only_when_unknown: true
memory_policy:
  recall_enabled: true
  allowed_selectors:
    - semantic
    - procedural
    - social
    - graph
  recall_must_use_port: IMemoryPort
constitution_policy:
  privacy_band_ceiling_from_actor: true
  subject_member_scope_required: true
outcome_policy:
  emits_domain_event: false
  memory_writeback: false
```

Input shape:

```json
{
  "focus": "today",
  "target_member_id": "family",
  "include": ["members", "relationships", "routines", "visible_constraints"],
  "max_items": 20
}
```

Output shape:

```json
{
  "status": "ok",
  "visibility": "actor_scoped",
  "actor_member_id": "mom",
  "projection_freshness": "fresh",
  "members": [
    {"member_id": "mom", "display_name": "Mom", "role": "parent"},
    {"member_id": "child_1", "display_name": "Liam", "role": "child"}
  ],
  "relationships": [
    {"from": "mom", "type": "parent_of", "to": "child_1"}
  ],
  "routines": [
    {"routine_id": "school_morning", "summary": "School morning routine"}
  ],
  "citations": [
    {"handle": "m:c1", "summary": "Morning routine projection", "freshness": "fresh"}
  ],
  "policy": {
    "privacy_band_ceiling": "AMBER",
    "redacted_count": 0
  }
}
```

Shared unknown output should be intentionally narrow:

```json
{
  "status": "ok",
  "visibility": "public_only",
  "actor_member_id": null,
  "projection_freshness": "fresh",
  "members": [],
  "relationships": [],
  "routines": [
    {"routine_id": "family_public_today", "summary": "Public household items for today"}
  ],
  "policy": {
    "privacy_band_ceiling": "GREEN",
    "redacted_count": 6,
    "identity_required_for_more": true
  }
}
```

First proving flow:

```text
User: What is happening in the family today?
        |
        v
Concierge resolves active self
        |
        v
Grounding capsule says allowed scope
        |
        v
LLM calls tool.read.family_context
        |
        v
ToolDispatcher step 0 evaluates policy
        |
        v
Tool reads local projection + allowed K0 recall via IMemoryPort
        |
        v
Tool returns actor-scoped family context
        |
        v
LLM answers within visible scope
```

This tool becomes the proving wedge. Once it works for parent, child, shared unknown, and offline stale scenarios, then M11 write tools can build on the same contract.

## Summary

The design direction, in algebra form:

```text
Three Sets:           S (self), F (family, derived), C (constitution)
Six Intersections:    S∩S, S∩F, S∩C, F∩C, S∩S∩F, S∩C∩S
Triple:               S ∩ F ∩ C  =  SituationFrame   <- runtime consumes only this
Four Unions:          U1..U4 (S∪F never materialized; F∪C is household runtime)
Four Differences:     Private Self, Ungoverned Self, Pure Family Facts, Latent Rules
Six Empty-Sets:       Default-deny invariants (E1..E6) that must be testable
Ten V0 Decisions:     Q1..Q10 freeze the algebra for V0
Five Layers of S:     L1 Core, L2 Identity, L3 Pattern, L4 Context, L5 State
                       with strong-sync / CRDT / per-device policy per layer
```

The product direction, in operating form:

```text
Start from family situations, not tools.
Model what FamilyOS must understand in those situations as a SituationFrame.
Let the constitution decide household boundaries; never infer them silently.
Default privacy by category, not by per-edge toggle.
Be useful by default, humble at boundaries, explicit at durability.
```

The compilation direction, in substrate form:

```text
SituationFrame composer is the actual E0 substrate target.
SelfModelService computes layered S; FamilyModelService derives F;
ConstitutionService loads signed C. The composer joins them at (T, D).
ToolDispatcher step 0 evaluates the SituationFrame; nothing else gates family authority.
```

K1 remains the local embodied self of a family member/device. K0 remains the durable memory, sync, and consolidation substrate. The source of design truth is the algebra above and the household's lived situations. If we get the algebra and the situations right, M11 tools become memory-grounded family capabilities composed from a single SituationFrame, rather than isolated CRUD endpoints with ad-hoc authority logic.

---

## Part C — V0 Conscience Model (shipped)

> Status: **shipped** as part of Part B (M6 → M11). Tagged
> `selfmodel-m6` … `selfmodel-m11`. CI lockdown: see
> [tests/integration/scripts/test_phase9_llm_mock.py](tests/integration/scripts/test_phase9_llm_mock.py).

The Part B inversion replaced IAM-style allowlists (`Capabilities`, `autonomy_rules`) with a **conscience-first algebra**: the policy gate is *default-allow* and only consults a small `ConsciencE Digest` for the four ways a constitution can constrain an act:

| Step | Field             | Verdict                  | Reason                  |
| ---- | ----------------- | ------------------------ | ----------------------- |
| 1    | `forbidden_acts`  | `DENY`                   | `capability_not_granted` |
| 2    | `tier_floor`      | `REQUIRE_IDENTITY`       | `identity_tier_too_low` |
| 3    | `risk_overrides`  | bumps baseline risk      | (matrix recompute)      |
| 4    | `must_ask_acts`   | `REQUIRE_CONFIRMATION`   | `needs_confirmation`    |
| —    | else              | `ALLOW`                  | `ok`                    |

Capability metadata moved into the agent fabric: every `CapabilityContract` now declares `risk_class` and `social_act`, and unknown capabilities fail-closed to `safety_sensitive`. The `IRiskCatalogPort` (M9) lets the gate query a single source of truth for risk/social-act metadata.

Onboarding (M10) is YAML-seedable via [scripts/onboarding_seed.py](scripts/onboarding_seed.py), with example seeds under [examples/seeds/](examples/seeds). The four M11 scripted prompts — *introspection, must_ask send_message, forbidden prescribe_medication, default-allow create_reminder* — are recorded in [data/m11_golden_transcript.json](data/m11_golden_transcript.json) and replayed in CI by [scripts/kernel_probe_phase9_v2.py](scripts/kernel_probe_phase9_v2.py) `--mode mock`.

**Deferred from Part B** (intentional, tracked as transitional):
- M9.E1.I3 — `risk_class_registry.py` retained as `FabricRiskCatalog` fallback.
- M9.E2.I2 — legacy `Capabilities` / `autonomy_rules` not yet deleted; back-compat tests still ship under [tests/k1/selfmodel/invariants/test_e6_capabilities.py](tests/k1/selfmodel/invariants/test_e6_capabilities.py) and [tests/k1/selfmodel/integration/test_identity_to_amendment.py](tests/k1/selfmodel/integration/test_identity_to_amendment.py). Removal is gated on migrating remaining v0 fixture writers.
- M11.E2.I2 — IAM-style test deletion deferred with M9.E2.I2 (deleting tests for code that still ships would create coverage gaps).
