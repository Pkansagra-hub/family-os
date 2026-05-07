<!-- markdownlint-disable MD031 MD040 -->
# Service Design: `k1.selfmodel`

Date: 2026-05-03
Status: draft / design (whiteboard companion to `whiteboard_k1_user_selfmodel_and_tools.md`)
Scope: K1 kernel component design. Concrete ports, adapters, services, lifecycle, and integration points. No UI concerns.

---

## 0. Source Anchors

This design implements the algebra and operating decisions captured in:

- `docs/whiteboard/whiteboard_k1_user_selfmodel_and_tools.md`
  - **The Set Algebra Spine** — Three Sets (S, F, C), Six Pairwise Intersections, the Triple (SituationFrame), Unions, Differences, Empty-Set Invariants, V0 Locked Algebra Decisions (Q1–Q10).
  - **The Five Layers of Self** — L1 Core, L2 Identity, L3 Pattern, L4 Context, L5 State; sync policy per layer.
  - **Layer Boundary: Kernel API vs UI Surfaces** — kernel exposes capabilities; UI never appears in kernel signatures.
  - **V0 Family Operating Design** — situations S1–S13, privacy categories, identity tier mechanism, child autonomy.
  - **Appendix: E0 Self Model Substrate** — data model targets, ToolDispatcher gate, citation schema, freshness × risk matrix.

Existing component patterns this design must follow (each has its own `ARCHITECTURE.md` + `.mmd`):

- `k1/concierge/ARCHITECTURE.md` — 8 hexagonal ports, adapter matrix, FSM, single-writer discipline.
- `k1/sessionstate/ARCHITECTURE.md` — 5 ABC ports, co-defined types, tier-based sections.
- `k1/bus/ARCHITECTURE.md` — `IBus` protocol, `Envelope` dataclass, topic registry.
- `k1/fabric/ARCHITECTURE.md`, `k1/model_hub/ARCHITECTURE.md`, `k1/orchestrator/ARCHITECTURE.md`,
  `k1/planner/ARCHITECTURE.md`, `k1/memory_writer/ARCHITECTURE.md` — cross-component conventions.

---

## 1. Component Overview

`k1.selfmodel` is a **generalized K1 kernel component** that owns the runtime composition of the household's self / family / constitution model and exposes it as a stable surface to Concierge, ToolDispatcher, prompt building, and recall.

### 1.1 Mission

```text
Compose ( S(actor)  ∩  F  ∩  C )  at  (T, D)  =  SituationFrame
Expose the SituationFrame as the only object the rest of K1 consumes.
Enforce the Empty-Set Invariants (E1–E6) at every boundary.
```

### 1.2 What it owns

| Capability | Owner inside `k1.selfmodel` |
| --- | --- |
| L1/L2 declared identity, role, age band, capabilities | `SelfModelService` |
| L3 learned pattern projection (CRDT-merged across devices) | `SelfModelService` (read), pattern feed from `memory_writer` |
| L4/L5 transient context/state (per-device, RAM-only) | `SelfModelService` |
| Family member graph + relationship edges + routines + copresence | `FamilyModelService` |
| Signed constitution snapshots, amendment lifecycle, conflict resolution | `ConstitutionService` + `AmendmentService` |
| Identity sessions on shared hub (tiers 0–3, hard TTL) | `IdentitySessionManager` |
| PIN / passkey / WebAuthn proof verification | `CredentialVerifier` |
| Policy verdicts (`ALLOW`, `DENY`, `REQUIRE_*`, `DEFER_OFFLINE`) | `PolicyEvaluator` |
| Composition of the SituationFrame at `(T, D)` | `SituationFrameComposer` |
| Prompt-safe capsule the LLM actor sees | `GroundingCapsuleBuilder` |
| Wrapping raw recall into normative citation pack | `CitationPackBuilder` |
| Step-0 policy gate inside ToolDispatcher | `PolicyGate` (adapter into `k1.concierge.tools.dispatcher`) |

### 1.3 What it does NOT own

- Rendering anything (UI layer).
- Long-term memory storage / consolidation (K0).
- Sync transport (Bridge owns it; `k1.selfmodel` only emits typed deltas).
- Tool execution (Fabric / Orchestrator / `k1.tools` MCP servers).
- LLM inference (`k1.model_hub`).
- The single-writer SessionState invariant — `k1.selfmodel` writes only via `IWriterPort`.

---

## 2. Hexagonal Port Surface

Following the K1 convention (Concierge: 8 ports; SessionState: 5 ABC ports), `k1.selfmodel` defines **7 ports**. New protocols use `@runtime_checkable Protocol` (Concierge style) unless they mutate session state, in which case ABC nominal subtyping is used (SessionState style).

### 2.1 Port Inventory

| # | Port | Style | File (proposed) | Key methods |
| --- | --- | --- | --- | --- |
| 1 | `IIdentityPort` | Protocol | `k1/selfmodel/ports/identity.py` | `start_session`, `end_session`, `present_credential`, `get_session_tier`, `list_eligible_profiles` |
| 2 | `ICredentialPort` | Protocol | `k1/selfmodel/ports/credential.py` | `verify(profile_id, credential) -> VerificationResult` |
| 3 | `IConstitutionPort` | Protocol | `k1/selfmodel/ports/constitution.py` | `get_active`, `get_diff`, `propose`, `submit`, `sign`, `decline`, `list_pending`, `list_history` |
| 4 | `ISelfFamilyPort` | Protocol | `k1/selfmodel/ports/selffamily.py` | `get_self(actor_id, T, D)`, `get_family_view(actor_id, T, D)`, `update_layer(layer, observation)` |
| 5 | `ISituationFramePort` | Protocol | `k1/selfmodel/ports/situation.py` | `compose(actor_id, T, D, situation_kind) -> SituationFrame` |
| 6 | `IPolicyPort` | Protocol | `k1/selfmodel/ports/policy.py` | `evaluate(PolicyRequest) -> PolicyVerdict` |
| 7 | `IProjectionStorePort` | ABC | `k1/selfmodel/ports/projection_store.py` | `read_self`, `read_family`, `read_constitution`, `write_self`, `write_family`, `write_constitution`, `freshness` |

`IProjectionStorePort` is ABC (mutating; we want explicit nominal subtyping for adapter implementations) — same rationale SessionState uses for `IStoragePort`/`IWriterPort`.

### 2.2 Co-defined types

Each port co-defines the dataclasses it exchanges. All are frozen dataclasses (no Pydantic, matching repo convention).

```text
ports/identity.py
  ProfileSummary, IdentitySession, VerificationResult,
  IdentityTier (IntEnum 0..3), DeviceContext, CredentialPresentation

ports/constitution.py
  ConstitutionSnapshot, ConstitutionDiff, AmendmentProposal,
  AmendmentStatus (Enum), ConflictDescriptor, SigningProof

ports/selffamily.py
  K1SelfModelSnapshot, FamilySelfModelSnapshot, RelationshipEdge,
  FamilyMemberRef, RoutineRef, LayerObservation

ports/situation.py
  SituationFrame, ProjectedSelf, RelationsSubset, ApplicableRules,
  Capabilities, Visibility

ports/policy.py
  PolicyRequest, PolicyVerdict, PolicyDecision (Enum),
  ReasonCode (Enum), RiskClass (Enum: low|medium|high|safety_sensitive)

ports/projection_store.py
  ProjectionFreshness (Enum: fresh|stale|offline_local_only|conflict_pending),
  ProjectionRevision, StoreReadResult, StoreWriteResult
```

### 2.3 Port → Algebra mapping

This map is the contract between the algebra (whiteboard) and the code (this design):

| Algebra concept | Port | Method |
| --- | --- | --- |
| `S(actor, T, D)` | `ISelfFamilyPort` | `get_self(actor, T, D)` |
| `F` (derived view) | `ISelfFamilyPort` | `get_family_view(actor, T, D)` |
| `C` (signed corpus) | `IConstitutionPort` | `get_active()` |
| `S ∩ F ∩ C` (SituationFrame) | `ISituationFramePort` | `compose(...)` |
| `S ∩ C` (Granted Self) — runtime check | `IPolicyPort` | `evaluate(PolicyRequest)` |
| Identity tier transition | `IIdentityPort` + `ICredentialPort` | `present_credential` |
| Constitution amendment lifecycle | `IConstitutionPort` | `propose`/`submit`/`sign` |
| Five-layer projection storage | `IProjectionStorePort` | `read_self`/`write_self` |

---

## 3. Adapter Matrix (V0)

| # | Adapter | Port | File (proposed) | Notes |
| --- | --- | --- | --- | --- |
| 1 | `SQLiteProjectionStore` | `IProjectionStorePort` | `k1/selfmodel/adapters/sqlite_projection_store.py` | Tables: `self_projection`, `family_projection`, `constitution_projection`, `projection_sync_state`. WAL + `synchronous=NORMAL`, `busy_timeout=5000` (matches `LocalOutbox` convention). Uses `PRAGMA user_version` + simple migration chain (new convention; not retrofitted). Default path `~/.familyos/k1/selfmodel.db`. |
| 2 | `InMemoryProjectionStore` | `IProjectionStorePort` | `k1/selfmodel/adapters/memory_projection_store.py` | Test-only; mirrors SessionState's `InMemoryStorageAdapter`. |
| 3 | `Ed25519CredentialVerifier` | `ICredentialPort` | `k1/selfmodel/adapters/credential_verifier.py` | Verifies WebAuthn/passkey assertions and PIN hashes (Argon2id). Uses PyNaCl for Ed25519 (matches `bridge/core/signing.py` `Ed25519Signing`). |
| 4 | `BridgeAmendmentSyncAdapter` | (internal hook into `ConstitutionService`) | `k1/selfmodel/adapters/bridge_amendment_sync.py` | Submits signed `ConstitutionSnapshot` deltas via `IBridgeClient.submit_command("sync.delta", ...)`; subscribes SSE `k0.sync.complete.v1` for refresh. Falls back to `LocalOutbox` when offline (`SinkBridgeClient` does this transparently). |
| 5 | `ConciergePolicyGate` | (slots into `ToolDispatcher.dispatch`) | `k1/selfmodel/adapters/concierge_policy_gate.py` | Wraps `IPolicyPort.evaluate` as step 0 of `k1.concierge.tools.dispatcher.ToolDispatcher.dispatch`. Returns blocked `ToolResult` for `DENY`; raises HITL via existing protocol for `REQUIRE_CONFIRMATION`. |
| 6 | `GroundingCapsuleRenderer` | (slots into `DynamicPromptBuilder.build`) | `k1/selfmodel/adapters/grounding_capsule_renderer.py` | Builds the prompt-safe block injected after section rendering, before `system_prompt` concatenation. |
| 7 | `RecallCitationWrapper` | (wraps `recall_fn` in `ToolContext`) | `k1/selfmodel/adapters/recall_citation_wrapper.py` | Wraps the existing `ctx.recall_fn` so every `recall_memory` tool call returns `CitationPack` instead of raw `list[dict]`. |
| 8 | `BridgeRecallAdapter` (existing planned) | `IMemoryPort` | `k1/concierge/adapters/bridge_recall.py` (SIM-GAP-36) | Not owned by `k1.selfmodel`, but `RecallCitationWrapper` composes on top of it when it lands. |

### 3.1 Test adapters

Mirror the production matrix with in-memory equivalents (matches Concierge's 8-test-adapter pattern):

```text
InMemoryProjectionStore
StubCredentialVerifier            # accepts everything; tier-controlled by test
InMemoryAmendmentSync             # no Bridge; events captured
NullPolicyGate                    # always ALLOW; for non-policy tests
RecordingCapsuleRenderer          # captures emitted capsules for assertions
PassthroughCitationWrapper        # returns raw recall as 1-citation pack
```

---

## 4. Service Layer

Following Concierge's pattern (`KernelService` orchestrates ports/adapters into a `KernelRuntime`), `k1.selfmodel` exposes services that consume ports and produce typed snapshots.

### 4.1 Service inventory

| Service | File (proposed) | Inputs (ports) | Outputs |
| --- | --- | --- | --- |
| `SelfModelService` | `k1/selfmodel/service/self_model.py` | `IProjectionStorePort` | `K1SelfModelSnapshot` |
| `FamilyModelService` | `k1/selfmodel/service/family_model.py` | `IProjectionStorePort`, `ISelfFamilyPort` (peer reads) | `FamilySelfModelSnapshot` (derived view of F) |
| `ConstitutionService` | `k1/selfmodel/service/constitution.py` | `IProjectionStorePort`, `IConstitutionPort` | `ConstitutionSnapshot` (signed) |
| `AmendmentService` | `k1/selfmodel/service/amendment.py` | `IConstitutionPort`, `BridgeAmendmentSyncAdapter` | Lifecycle transitions DRAFT→PENDING→APPROVED→ACTIVE |
| `IdentitySessionManager` | `k1/selfmodel/service/identity_session.py` | `IIdentityPort`, `ICredentialPort` | Per-session token + tier with hard TTL |
| `SituationFrameComposer` | `k1/selfmodel/service/situation_composer.py` | All of the above | `SituationFrame` (the triple intersection) |
| `PolicyEvaluator` | `k1/selfmodel/service/policy_evaluator.py` | `ConstitutionService`, `SituationFrameComposer` | `PolicyVerdict` |
| `GroundingCapsuleBuilder` | `k1/selfmodel/service/capsule_builder.py` | `SituationFrameComposer` | `GroundingCapsule` (prompt-safe) |
| `CitationPackBuilder` | `k1/selfmodel/service/citation_builder.py` | (wraps recall results) | `CitationPack` |

### 4.2 Composition flow (per turn)

```text
Turn input arrives in Concierge FSM
        |
        v
ConciergeRuntime resolves session_token (via IIdentityPort)
        |
        v
SituationFrameComposer.compose(actor_id, T=now, D=device, kind=inferred)
   reads:
     SelfModelService.get(actor_id)              -- L1+L2+filtered L3
     FamilyModelService.get_view(actor_id)       -- F projected for actor
     ConstitutionService.get_active()            -- signed C
     IProjectionStorePort.freshness(...)         -- per-projection state
        |
        v
SituationFrame returned (actor, ProjectedSelf, RelationsSubset,
                         ApplicableRules, Capabilities, Visibility,
                         L4/L5 transient block, freshness)
        |
        v
GroundingCapsuleBuilder.build(SituationFrame) -> GroundingCapsule
        |
        v
DynamicPromptBuilder.build(mode, ss, capsule=...)
        |
        v
Front actor LLM call
        |
        v
LLM emits tool_call
        |
        v
ToolDispatcher.dispatch(tool_call)
   step 0 = ConciergePolicyGate -> IPolicyPort.evaluate(PolicyRequest)
        |
        v
   ALLOW            -> continue existing 6-step pipeline
   DENY             -> blocked ToolResult
   REQUIRE_*        -> HITL escalation via existing protocol
   DEFER_OFFLINE    -> queue + blocked ToolResult
```

### 4.3 Empty-Set Invariants in code

Each invariant from the whiteboard maps to a runtime assertion:

```text
E1. (S \ consent) ∩ F = ∅
    -> SelfModelService.get_for_other_viewer(actor, viewer) MUST filter
       through actor.consent before returning to FamilyModelService.
    -> Tested in: test_e1_no_unconsented_data_reaches_family

E2. (S \ C.visibility_rules) ∩ F = ∅
    -> SituationFrameComposer's projection step MUST consult
       C.visibility_rules; default-deny when no rule applies.
    -> Tested in: test_e2_default_deny_visibility

E3. K0_outbound ∩ BLACK = ∅
    -> BridgeAmendmentSyncAdapter and any selfmodel-emitted
       command MUST refuse payloads tagged BLACK.
       Enforced as a band check in the bridge submit path.
    -> Tested in: test_e3_black_never_leaves_k1

E4. C.amendments \ signed = ∅
    -> ConstitutionService.activate() MUST fail unless signature
       chain validates back to bootstrap signers.
    -> Tested in: test_e4_unsigned_amendment_rejected

E5. raw_S(other) ∩ ProjectedSelf(actor) = ∅
    -> SituationFrame.relations holds only ProjectedSelf instances;
       composer MUST NOT include raw S of other actors.
    -> Tested in: test_e5_no_raw_other_self_in_frame

E6. tool_authority \ SituationFrame.capabilities = ∅
    -> ConciergePolicyGate MUST return DENY when requested action
       is not in SituationFrame.capabilities.can_do.
    -> Tested in: test_e6_no_tool_outside_capabilities
```

These six tests are the **non-negotiable acceptance gate** for V0.

---

## 5. Connection Points to Existing K1 Components

Every kernel-side hand-off has a verified seam. File paths are workspace-relative.

### 5.1 Concierge — `k1.concierge`

#### 5.1.1 SessionState integration

- **MetaSection** — `k1/sessionstate/sections/meta.py`. Holds `SessionIdentity { session_id, user_id, device_id, privacy_band, is_anonymous, is_demo_mode }`.
  `k1.selfmodel` reads MetaSection on session start to seed `SelfModelService.get(actor_id)`.
- **PersonaSection** — `k1/sessionstate/sections/persona.py`. WARM tier, last-to-evict.
  `k1.selfmodel` reads `PersonaSection._preferences` for any pre-existing family hints during migration; long-term, family hints come from `FamilySelfModelSnapshot`.
- **PrivacyBand enum** — `k1/sessionstate/sections/meta.py:121`. `IntEnum { GREEN, AMBER, RED }`.
  `k1.selfmodel.contracts.PrivacyBand` re-exports this; **a mapping helper** converts to bridge string literals (`"GREEN"|"AMBER"|"RED"`) when constructing `CommandEnvelope.band`. BLACK is K1-local only and never reaches the bridge layer (E3).
- **New section registration** — Sections are tier-based Python modules, not enum entries. `k1.selfmodel` adds NO new SessionState section in V0 (Locked Decision 1: SelfModel is a service plus local projection store, not a SessionState section).
  If V1 needs typed sections (for prompt-token-budget reasons), the path is: create `k1/sessionstate/sections/self_model.py`, declare tier in `k1/sessionstate/tiers/`, add `SSReadConfig` entries in `k1/concierge/prompt/builder.py:SS_READ_CONFIGS` per `PromptMode`.
- **Single-writer discipline** — `IWriterPort` ABC at `k1/sessionstate/ports/writer.py`. `MutationRequest { section, operation, data, writer_id, priority, trace_id, expires_at_ms }`.
  `k1.selfmodel` registers `writer_id = "selfmodel:identity_session"` (and similar per-service ids) via `validate_writer()` at `KernelService.startup()`. The `DirectWriterAdapter` at `k1/sessionstate/adapters/direct_writer.py` enforces the authorized set.

#### 5.1.2 Prompt grounding

- **`DynamicPromptBuilder.build()`** — `k1/concierge/prompt/builder.py`.
  Insertion: after the `SS_READ_CONFIGS[mode]` loop renders SS sections to text blocks, **prepend** the `GroundingCapsuleRenderer.render(capsule) -> str` block before final `system_prompt` concatenation. Mode-agnostic; the capsule appears in every Front LLM call.
- **`SECTION_RENDERERS`** — same file. No new renderer needed in V0; the capsule is rendered by `GroundingCapsuleRenderer` and concatenated, not registered as a section renderer.

#### 5.1.3 Tool dispatch

- **`ToolDispatcher.dispatch()`** — `k1/concierge/tools/dispatcher.py`. Current pipeline is 6 steps (the file header still says "7"; that label is stale).
  `ConciergePolicyGate` is prepended as **step 0**:
  ```
  step 0  ConciergePolicyGate           -> IPolicyPort.evaluate
  step 1  Allowlist check                (existing)
  step 2  Budget check                   (existing)
  step 3  Schema validation              (existing)
  step 4  Safety band check              (existing)
  step 5  Dispatch to execute_tool       (existing)
  step 6  Record in call_history         (existing)
  ```
  Step 0 returns `(ALLOW, _)` to fall through, or terminates with a structured blocked `ToolResult`. No changes to existing steps; pure prepend.
- **`get_tool_allowlist(mode, affect_confidence, tier)`** — `k1/concierge/prompt/mode.py`. Returns per-mode allowlist.
  `k1.selfmodel` does **not** modify the allowlist function; it filters at execution time, not at schema-presentation time. UX hinting (hiding tools the actor can't use) is a V1 concern.
- **Tool schemas** — Front: `k1/concierge/tools/schemas_front.py`. Back: `k1/concierge/tools/schemas_back.py`. Registry: `TOOL_REGISTRY` populated by `@_register("...")` in `k1/concierge/tools/implementations.py`.
  V0 adds one read-only proving tool: `tool.read.family_context` (already specified in the whiteboard's E0 appendix). Implementation: `k1/concierge/tools/implementations.py` via `@_register("tool.read.family_context")`. Schema: added to `schemas_front.py` (front-visible).

#### 5.1.4 Memory recall

- **`IMemoryPort`** — `k1/concierge/ports.py`. `recall(query, selectors|None, max_results) -> list[dict]`.
- **`recall_memory` tool** — `execute_recall_memory(args, ctx)` in `k1/concierge/tools/implementations.py:794`. Schema in `schemas_front.py:352` (also imported by `schemas_back.py`, `actor="both"`).
- **`BridgeRecallAdapter`** — planned at `k1/concierge/adapters/bridge_recall.py` (SIM-GAP-36). `k1.selfmodel.RecallCitationWrapper` composes ON TOP of whatever `IMemoryPort` adapter is wired (POC `recall_fn` today, `BridgeRecallAdapter` later). The wrapping point is **`ctx.recall_fn`** in `ToolContext` — `RecallCitationWrapper` replaces this closure at session bootstrap so every `recall_memory` call returns a `CitationPack` per the V0 citation schema.

#### 5.1.5 Identity overlay (OPP-7)

- **`DynamicIdentityContext` / `IdentitySnapshot`** — `k1/concierge/identity/dynamic_identity.py`.
  These are **per-turn overlay** for tone/role/expertise. `k1.selfmodel` is **session-scoped substrate**. They coexist:
  ```
  K1SelfModel       (session-scoped, k1.selfmodel)        -> identity, authority, privacy
  IdentitySnapshot  (per-turn overlay, OPP-7)             -> tone, role framing
  PersonaSection    (per-session, k1.sessionstate)        -> communication style
  ```
  The overlay must NOT mutate `K1SelfModel` (Invariant I7). The composer reads the overlay only for the L4/L5 transient block of the SituationFrame.

#### 5.1.6 HITL / safety escalation

- **HITL types** — `k1/concierge/protocols/hitl.py`. `HILRequest`, `HILResponse`, `SafetyBand`.
- **Pipelines** — `k1/concierge/protocols/hitl_pipeline.py` (`detect_approval_required`, `approval_pipeline`).
- **Suspension protocol** — `k1/concierge/protocols/suspension.py`. Pauses Back actor, emits HITL_RELAY to Front FSM.
  When `IPolicyPort.evaluate` returns `REQUIRE_CONFIRMATION`, `ConciergePolicyGate` constructs a `HILRequest(kind="approval", capability_name=tool_name, context=policy_context, timeout_s=120)` and routes through the existing `approval_pipeline()`. No new approval surface is built; we reuse the protocol.

#### 5.1.7 Bootstrap / lifecycle

- **K1 bootstrap** — `k1/kernel/bootstrap.py`. Concierge shim re-exports at `k1/concierge/kernel/bootstrap.py`.
  `KernelService.startup()` constructs the global `k1.selfmodel` services (singletons or per-tenant). `KernelService.create_session(session_id)` constructs per-session `IdentitySessionManager` state and binds `selfmodel` references into `ConciergeRuntime` and the `ToolContext` passed to actors.
- **`SessionInstance`** gets a new `selfmodel: SelfModelHandle` field carrying the per-session service handle.
- **Lifecycle hooks** — Each service implements `startup() / shutdown() / health()` matching the `ILifecyclePort` shape from `k1/sessionstate/ports/lifecycle.py`. The K1 runner (`k1/kernel/runner.py`) calls these via the existing lifecycle aggregator.

### 5.2 K1 Bus — `k1.bus`

- **`IBus`** — `k1/bus/ports/bus.py:91-144`. `publish(envelope)`, `subscribe(pattern, handler) -> SubscriptionHandle`, `unsubscribe(handle)`.
- **`Envelope`** — `k1/bus/envelope/envelope.py`. Frozen dataclass; `topic, payload (bytes), priority, delivery_mode, payload_format, envelope_id, sequence, created_ns, cognitive_trace_id, session_id, parent_id`.
- **`BusFactory.create_local()`** — `k1/bus/factory.py:146`. `k1.selfmodel` consumes whichever `IBus` Concierge already wired; it does NOT instantiate a bus.
- **New topic prefix**: `k1.selfmodel.*` (currently absent). Topics V0 emits:
  ```
  k1.selfmodel.identity.session_started.v1
  k1.selfmodel.identity.session_ended.v1
  k1.selfmodel.identity.tier_promoted.v1
  k1.selfmodel.identity.tier_rejected.v1
  k1.selfmodel.constitution.amendment_pending.v1
  k1.selfmodel.constitution.amendment_active.v1
  k1.selfmodel.constitution.amendment_rejected.v1
  k1.selfmodel.constitution.conflict_detected.v1
  k1.selfmodel.tool.requires_confirmation.v1
  k1.selfmodel.tool.requires_identity.v1
  k1.selfmodel.tool.deferred_offline.v1
  k1.selfmodel.projection.freshness_changed.v1
  k1.selfmodel.suggestion.card_available.v1
  k1.selfmodel.situation.composed.v1            # debug-mode only; high volume
  ```
- **Topic registry** — `k1/bus/middleware/topic_validation.py:57` `TopicRegistry`. `k1.selfmodel.startup()` calls `registry.register_prefix("k1.selfmodel.")`.
- **Delivery mode** — Add a STRICT entry for `k1.selfmodel.constitution.*` and `k1.selfmodel.identity.*` in `k1/bus/timing/defaults.py` (constitution and identity events must preserve order). Other `k1.selfmodel.*` topics default to RELAXED.

### 5.3 Bridge — `bridge`

- **Client** — `bridge/client.py`. `IBridgeClient` Protocol; `SinkBridgeClient` (offline, queues to `LocalOutbox`); `HttpBridgeClient` (production, MS-3+).
- **Command submission** — `submit_command(topic, body, *, schema_uri=None, band=None, trace_id=None)` async. Routes through `EnvelopeBuilder.build()` → `HttpTransport.post_command()` → `POST /k0/command.submit` → `CommandResponse(receipt_id, commit_ts, ...)`.
- **Topic for constitution sync** — `sync.delta` (P07 CRDT). `BridgeAmendmentSyncAdapter` calls `submit_command("sync.delta", canonical_amendment_envelope, band="GREEN", schema_uri="schemas/k1.selfmodel.constitution.v1")`. Band is the bridge wire band (BLACK never reaches here per E3).
- **Local outbox** — `bridge/sync/local_outbox.py:79`. SQLite WAL, `outbox_queue` table. When K0 unreachable, `SinkBridgeClient` queues automatically; no special-case code needed in `k1.selfmodel`.
- **Signing** — `bridge/core/signing.py`. `Ed25519Signing(signing_key_bytes, key_id)` (line 106). Key material loading is the caller's responsibility (no key-store loader yet).
  `k1.selfmodel.AmendmentService` builds canonical JSON for the amendment, signs **before** handing to `submit_command`. The signature is included in the amendment body (bridge separately signs the wire envelope; double-signing is intentional — amendment signature is by guardian; envelope signature is by device).
  Key `key_id` format: `did:device:<device_id>#<key_rotation_marker>` (ADR-0050d).
- **SSE topics consumed**:
  ```
  k0.sync.complete.v1                  -> ConstitutionService refreshes projection,
                                          updates projection_sync_state, emits
                                          k1.selfmodel.constitution.amendment_active.v1
  ```
  Subscription: `IBridgeClient.subscribe(...)` returning `AsyncIterator[SSETraceEvent]`. Handler registered in `BridgeAmendmentSyncAdapter.startup()`.
- **Backpressure** — SSE event carries `backpressure { level: ok|throttle|shed, lag_ms, pending_events }`. `k1.selfmodel` SSE handler must respect `throttle` (debounce projection refresh) and `shed` (drop low-priority refresh; keep critical signature events).

### 5.4 Local SQLite

- **`SQLiteProjectionStore`** — new file `k1/selfmodel/adapters/sqlite_projection_store.py`. Default path `~/.familyos/k1/selfmodel.db` (matches `~/.familyos/k1/<component>.db` convention).
- **Tables** (mirror E0 spec in whiteboard appendix):
  ```
  self_projection                (PK self_id)
  family_projection              (PK family_space_id)
  constitution_projection        (PK constitution_id; immutable rows; version chain by parent_version)
  amendment_proposals            (PK amendment_id; states DRAFT..EXPIRED)
  amendment_signatures           (FK amendment_id; append-only)
  identity_sessions              (PK session_token; TTL-indexed)
  projection_sync_state          (PK projection_key)
  ```
- **PRAGMAs**: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `user_version=1`.
- **Migrations**: simple chain in `migrations/` directory inside the adapter; each migration bumps `user_version`. This introduces the `PRAGMA user_version` convention not yet used elsewhere; documented as the new K1 best practice.

### 5.5 Observability

- **Metrics** — Concierge pattern, NOT direct `prometheus_client`. `MetricsCollector` from `k1/concierge/obs/metrics.py` emits `MetricEnvelope` onto the bus; `MetricAggregator` subscribes.
  `k1.selfmodel` metrics (V0):
  ```
  selfmodel.situation_frame.build_ms             (histogram)  labels: actor_role, situation_kind
  selfmodel.policy.verdict_count                 (counter)    labels: decision, reason_code
  selfmodel.identity.tier_transition_count       (counter)    labels: from_tier, to_tier, outcome
  selfmodel.amendment.lifecycle_count            (counter)    labels: from_state, to_state
  selfmodel.amendment.signature_latency_ms       (histogram)  labels: amendment_kind
  selfmodel.projection.freshness_state           (gauge)      labels: projection_type, state
  selfmodel.citation.pack_size                   (histogram)  labels: source_layer
  selfmodel.invariant.violation_count            (counter)    labels: invariant_id (E1..E6)
                                                              # MUST stay at zero in production
  ```
- **Tracing** — `k1/bus/middleware/tracing.py` creates one OTel span per envelope automatically. `k1.selfmodel` adds custom spans inside `SituationFrameComposer.compose()` (via `opentelemetry.trace.get_tracer("k1.selfmodel.composer")`) with graceful degradation if OTel absent.
  Pass `cognitive_trace_id` on every published envelope so the bus middleware auto-correlates.

### 5.6 Contracts

- **K1 cross-component contracts** — `k1/contracts/` (existing).
  `k1.selfmodel` adds:
  ```
  k1/contracts/selfmodel/
    self_model.snapshot.v1.schema.json
    family_model.snapshot.v1.schema.json
    constitution.snapshot.v1.schema.json
    constitution.amendment.v1.schema.json
    identity.session.v1.schema.json
    policy.verdict.v1.schema.json
    grounding.capsule.v1.schema.json
    citation.pack.v1.schema.json
  ```
- **Cross-kernel contracts** — `contracts/` (top level). The signed `ConstitutionSnapshot` schema referenced by `submit_command(schema_uri=...)` lives here as `contracts/k1_selfmodel/constitution_snapshot.v1.json`.
- **Type style** — frozen dataclasses for runtime types (matches repo convention; no Pydantic). FlatBuffers reserved for high-volume hot-path types if needed in V1.

---

## 6. Public API Surface (Mapping to Whiteboard's Kernel API)

The whiteboard specifies the V0 kernel public API. This section binds each call to a specific port + service.

| Whiteboard call | Binds to |
| --- | --- |
| `list_eligible_profiles(device_context)` | `IIdentityPort.list_eligible_profiles` → `IdentitySessionManager` |
| `start_identity_session(profile_id, proof?)` | `IIdentityPort.start_session` → `IdentitySessionManager` (calls `ICredentialPort.verify` if proof provided) |
| `present_credential(session_token, credential)` | `IIdentityPort.present_credential` → `CredentialVerifier.verify` then `IdentitySessionManager.promote_tier` |
| `end_identity_session(session_token)` | `IIdentityPort.end_session` → `IdentitySessionManager` |
| `get_grounding_capsule(session_token)` | `ISituationFramePort.compose` + `GroundingCapsuleBuilder.build` |
| `get_household_rules_diff(c_id, va, vb)` | `IConstitutionPort.get_diff` → `ConstitutionService` |
| `get_pending_amendments(session_token)` | `IConstitutionPort.list_pending` → `AmendmentService` |
| `get_review_queue(session_token)` | `IConstitutionPort.list_pending` filtered to suggestions |
| `draft_amendment(session_token, body)` | `IConstitutionPort.propose` → `AmendmentService` (state DRAFT) |
| `submit_amendment(amendment_id)` | `IConstitutionPort.submit` → state PENDING; emits `k1.selfmodel.constitution.amendment_pending.v1` |
| `sign_amendment(amendment_id, signing_proof)` | `IConstitutionPort.sign` → `CredentialVerifier.verify(signing_proof)` then append signature; on quorum → APPROVED → `BridgeAmendmentSyncAdapter.submit_delta` |
| `decline_amendment(amendment_id, reason?)` | `IConstitutionPort.decline` → state REJECTED |
| `invoke_tool(session_token, tool_call)` | Existing Concierge tool path; `ConciergePolicyGate` runs as step 0 |
| `confirm_tool(pending_id, confirmation_proof)` | Existing Concierge HITL `approval_pipeline()` |
| `proceed_with_stale(pending_id, reason?)` | New `IPolicyPort.override_stale(pending_id, reason)` → re-evaluates with override flag; audit-logs |
| `subscribe_events(session_token, topics)` | Existing `IBus.subscribe` filtered to `k1.selfmodel.*` and `k1.constitution.*` |

The **transport** for these calls is not the kernel's concern. The K1 runtime exposes them as in-process callables; UI adapters wrap them onto whatever transport the platform requires (in-process binding, IPC, gRPC, WebSocket).

---

## 7. Lifecycle and Bootstrap

### 7.1 Module layout

```text
k1/selfmodel/
  ARCHITECTURE.md
  selfmodel.mmd                      # mermaid diagram (component view)
  __init__.py
  ports/
    identity.py                      # IIdentityPort + co-defined types
    credential.py                    # ICredentialPort
    constitution.py                  # IConstitutionPort
    selffamily.py                    # ISelfFamilyPort
    situation.py                     # ISituationFramePort
    policy.py                        # IPolicyPort
    projection_store.py              # IProjectionStorePort (ABC)
  adapters/
    sqlite_projection_store.py
    memory_projection_store.py
    credential_verifier.py
    bridge_amendment_sync.py
    concierge_policy_gate.py
    grounding_capsule_renderer.py
    recall_citation_wrapper.py
  contracts/
    self_model.py                    # K1SelfModelSnapshot, layer types
    family_model.py
    constitution.py                  # ConstitutionSnapshot, AmendmentProposal
    situation.py                     # SituationFrame, ProjectedSelf, ...
    policy.py                        # PolicyRequest, PolicyVerdict, RiskClass
    citation.py                      # Citation, CitationPack
    capsule.py                       # GroundingCapsule
    privacy.py                       # PrivacyBand re-export + bridge mapping
  service/
    self_model.py
    family_model.py
    constitution.py
    amendment.py
    identity_session.py
    situation_composer.py
    policy_evaluator.py
    capsule_builder.py
    citation_builder.py
  kernel/
    bootstrap.py                     # SelfModelServiceBundle constructor
    handle.py                        # SelfModelHandle (per-session)
  obs/
    metrics.py                       # selfmodel.* metric definitions
  events/
    topics.py                        # canonical k1.selfmodel.* topic strings + registry
    payloads.py                      # typed payloads for each topic
  migrations/                        # SQLite schema migrations (user_version chain)
    0001_initial.sql
  tests/
    unit/                            # one per service + invariant
    integration/                     # Concierge + Bus + Bridge stub
    invariants/                      # E1..E6 acceptance gate
```

### 7.2 Startup sequence

```text
k1.kernel.runner.main()
   ↓
KernelService.startup()
   ↓
   1. existing K1 components start (bus, sessionstate, model_hub, fabric, ...)
   2. SelfModelServiceBundle.startup(config)
        a. SQLiteProjectionStore.open(db_path)
              -> apply migrations (user_version chain)
        b. ConstitutionService.load_active() from projection store
              -> verify signature chain back to bootstrap signers
              -> if invalid, freeze in safe-mode (no amendments accepted; reads still work)
        c. register topic prefix "k1.selfmodel." with TopicRegistry
        d. add STRICT delivery mode for k1.selfmodel.identity.* and k1.selfmodel.constitution.*
        e. register IWriterPort writer_ids with DirectWriterAdapter:
              "selfmodel:identity_session", "selfmodel:amendment", "selfmodel:projection"
        f. BridgeAmendmentSyncAdapter.startup()
              -> drain LocalOutbox if K0 reachable
              -> subscribe SSE k0.sync.complete.v1
        g. emit k1.selfmodel.startup.complete.v1
   ↓
KernelService.create_session(session_id)
   ↓
   1. existing per-session setup (SessionState, Concierge runtime, ...)
   2. IdentitySessionManager.create_for_session(session_id, device_context)
        -> on personal device: derive actor from MetaSection.user_id
        -> on shared hub: tier=0; await UI start_identity_session call
   3. SituationFrameComposer.bind(session_id)
   4. install ConciergePolicyGate as step 0 in this session's ToolDispatcher
   5. install GroundingCapsuleRenderer hook in this session's DynamicPromptBuilder
   6. wrap ToolContext.recall_fn with RecallCitationWrapper
```

### 7.3 Shutdown

```text
KernelService.shutdown()
   ↓
   SelfModelServiceBundle.shutdown()
      a. flush outstanding writes via IWriterPort
      b. close SSE subscriptions
      c. drain LocalOutbox best-effort (timeout 5s)
      d. close SQLiteProjectionStore (checkpoint WAL)
      e. emit k1.selfmodel.shutdown.complete.v1
```

### 7.4 Health

`SelfModelServiceBundle.health() -> HealthStatus` reports:

```text
projection_store_open:        bool
constitution_active_version:  str | None
constitution_signature_ok:    bool
bridge_reachable:             bool
outbox_pending:               int
identity_sessions_active:     int
freshness_self:               fresh|stale|offline_local_only|conflict_pending
freshness_family:             ...
freshness_constitution:       ...
last_invariant_violation:     {invariant_id, ts_ms} | None
```

---

## 8. V0 Implementation Order

```text
M0  Scaffolding
    - k1/selfmodel/ module layout
    - empty ports + co-defined types
    - InMemoryProjectionStore + StubCredentialVerifier
    - test harness wiring

M1  SituationFrame composer (the core)
    - SelfModelService.get(actor) [from MetaSection seed only]
    - FamilyModelService.get_view(actor) [stub: single-member household]
    - ConstitutionService.get_active() [bootstrap default constitution]
    - SituationFrameComposer.compose(...)
    - tests for E1, E2, E5

M2  Policy evaluator + dispatcher gate
    - PolicyEvaluator.evaluate(PolicyRequest)
    - ConciergePolicyGate plugged into ToolDispatcher.step0
    - risk_class declaration on tool contracts (declare on existing tools as low|medium|high|safety_sensitive)
    - freshness × risk matrix implementation
    - tests for E6

M3  Identity sessions + credential verifier
    - IdentitySessionManager (in-memory) + Ed25519CredentialVerifier (PIN hash + WebAuthn)
    - SQLite persistence for identity_sessions table
    - hard TTL enforcement (independent of UI inactivity timer)
    - tests for tier transitions, TTL expiry

M4  Constitution service + amendment lifecycle
    - SQLiteProjectionStore for constitution_projection
    - AmendmentService DRAFT->ACTIVE state machine
    - signature chain validation back to bootstrap signers
    - conflict_pending detection (sibling parent_version)
    - tests for E4, conflict resolution

M5  Grounding capsule + citation wrapper
    - GroundingCapsuleBuilder + Renderer plugged into DynamicPromptBuilder
    - RecallCitationWrapper wraps ctx.recall_fn
    - normative citation schema enforced
    - tests for capsule contents, citation expansion via recall_memory

M6  Bridge sync (when SSE infra lands)
    - BridgeAmendmentSyncAdapter
    - LocalOutbox integration
    - k0.sync.complete.v1 handler
    - tests for offline queue + reconciliation

M7  Proving tool: tool.read.family_context
    - implementation in k1/concierge/tools/implementations.py
    - schema in schemas_front.py
    - end-to-end test: parent device, child device, shared unknown, offline stale
```

Each milestone is shippable; M1+M2+M5+M7 is the minimum viable proving wedge.

---

## 9. Test Strategy

Mirrors Concierge's 4-layer pattern (whiteboard "POC Testing Surface Direction"):

```text
Layer 1: Deterministic unit tests
   - one per service
   - one per port adapter
   - the six invariant tests (E1..E6) live here and are MANDATORY for V0 GA

Layer 2: Concierge integration tests (scripted)
   - ToolDispatcher step-0 gate behavior matrix
   - DynamicPromptBuilder capsule injection
   - HITL escalation hand-off
   - identity tier transitions on shared hub

Layer 3: poc/k1_poc exploratory
   - real LLM, real UI bootstrap
   - the 13 V0 situations (S1..S13) walked through
   - subjective UX for "helpful without overconfidence"

Layer 4: Production Concierge kernel integration
   - end-to-end with Bridge stub
   - sync.delta round-trip
   - SSE refresh
   - chaos: K0 offline, K0 conflict, projection corruption recovery
```

### 9.1 Acceptance gate (the six invariants)

```text
test_e1_no_unconsented_data_reaches_family
test_e2_default_deny_visibility
test_e3_black_never_leaves_k1
test_e4_unsigned_amendment_rejected
test_e5_no_raw_other_self_in_frame
test_e6_no_tool_outside_capabilities
```

These are blocking. CI fails the build on regression.

---

## 10. Open Implementation Questions

These are scoped, not blocking. Each has a default position; flagged for explicit decision before M1 lands.

1. **Bootstrap default constitution body** — V0 ships a minimal default constitution at first-run. Source: a YAML in `k1/selfmodel/contracts/bootstrap_constitution.v0.yaml` signed by a synthetic "system" key, immediately replaced by household's onboarding amendment. *Default position: yes, ship it; alternative is forcing onboarding before any K1 use, which breaks personal-device single-user mode.*

2. **Where the bootstrap signing keys come from** — ADR-0050d mentions device Ed25519 keys but no key-store loader exists in `bridge/`. *Default position: read from `~/.familyos/k1/keys/` (mode 0600), generated at first run via PyNaCl. Document the rotation story for V1.*

3. **Whether `SituationFrame.compose()` is cached per turn** — Composing on every tool call might be wasteful. *Default position: cache per `(session_id, turn_id)` with explicit invalidation on freshness change or identity tier change. Compose lazily on first `evaluate` request per turn.*

4. **`PrivacyBand` mapping to bridge band string** — `k1.selfmodel.contracts.privacy.privacy_band_to_bridge(band: PrivacyBand) -> str` with explicit `BLACK -> raise BlackBandLeakError` (defense in depth on top of E3).

5. **Per-tool `risk_class` declaration** — How is it added to existing tools without rewriting all schemas? *Default position: a registry `RISK_CLASS_BY_TOOL: dict[str, RiskClass]` in `k1/selfmodel/contracts/policy.py`, defaulting unknown tools to `low` with a startup warning. Tools can override by adding `risk_class: ...` to their YAML/dataclass schema.*

6. **Suggestion sources for the review queue** — Which component proposes constitution candidates from observed patterns? *Default position: `k1.learning` (existing component) emits `k1.selfmodel.suggestion.card_available.v1` and `AmendmentService` displays them; `k1.selfmodel` does not infer rules itself.*

7. **Multi-tenant isolation** — `SelfModelServiceBundle` per tenant or one shared with tenant-keyed projection store? *Default position: one bundle, projection store keyed by `tenant_id`. Avoids per-tenant lifecycle complexity in V0.*

---

## 11. Out of Scope for V0

These items are explicitly deferred to V1+ to keep V0 shippable:

- Cross-household intersection (Q8 deferred; only `S.external_household_refs` field reserved).
- `FamilySelf` as a first-class entity (Q2 deferred).
- Constitution self-amending governance (Q5: V0 is bootstrap-immutable; reset is the only escape).
- Voice biometric as authoritative proof (always advisory in V0).
- Hard delete of severed members (encrypt-shred only; future right-to-be-forgotten work).
- L3 pattern auto-promotion to durable rule (always parent-approved in V0).
- Pet/device-as-actor modeling (resources only in V0).
- Proactive workflow scheduling driven by SituationFrame (read-only proving wedge first).

---

## 12. Summary

`k1.selfmodel` is the **kernel-side compiler from algebra to runtime**:

```text
S, F, C   -[k1.selfmodel services]->   SituationFrame   -[Concierge]->   LLM + Tools
```

It exposes capabilities through 7 hexagonal ports (5 Protocol + 2 ABC), is wired into existing K1 seams (SessionState writer, Concierge prompt builder, ToolDispatcher step 0, IMemoryPort wrap, HITL protocol), follows the K1 component conventions (frozen-dataclass contracts, bus-native metrics, OTel tracing, SQLite WAL with versioned migrations), and enforces the six Empty-Set Invariants as blocking acceptance tests.

It does not render anything. It does not transport anything. It composes the SituationFrame and gates the dispatcher. That is the whole job.
