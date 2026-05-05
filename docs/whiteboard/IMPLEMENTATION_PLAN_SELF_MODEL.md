<!-- markdownlint-disable MD025 MD031 MD040 MD024 MD060 -->
# Implementation Plan: `k1.selfmodel` (Milestone / Epic / Issue)

Date: 2026-05-03
Companion to:

- `docs/whiteboard/whiteboard_k1_user_selfmodel_and_tools.md` (algebra + V0 specs)
- `docs/whiteboard/SERVICE_DESIGN_SELF_MODEL.md` (ports, adapters, services, seams)

Conventions:

- **Milestone** = shippable cut of `k1.selfmodel` with explicit acceptance gate.
- **Epic** = a coherent vertical slice (one or two related ports + services + adapters + tests).
- **Issue** = single PR, single owner, single ARCHITECTURE.md update.
- Every issue has `Tests:` (siloed unit tests for that issue) and `Acceptance:` (binary).
- Integration testing is concentrated in **M5** (the last milestone) per user direction.

---

## 0. Pre-Plan Findings

### 0.1 HITL vs HIL — duplication audit

There are **two** HITL surfaces in the codebase:

| Surface | Path | Owner | Role |
| --- | --- | --- | --- |
| Concierge HITL protocol (older, V2 design) | [k1/concierge/protocols/hitl.py](k1/concierge/protocols/hitl.py), [hitl_pipeline.py](k1/concierge/protocols/hitl_pipeline.py), [hitl_persistence.py](k1/concierge/protocols/hitl_persistence.py), [hitl_flow.py](k1/concierge/protocols/hitl_flow.py), [hitl_wiring.py](k1/concierge/protocols/hitl_wiring.py), [events/hitl.py](k1/concierge/events/hitl.py), [obs/hitl_metrics.py](k1/concierge/obs/hitl_metrics.py) | Concierge V2 (Sec 9.x) | `HILRequest`/`HILResponse`/`SafetyBand` types + Front/Back FSM closed-cycle resume + suspension limits + ReAct history persistence. **Concierge-internal**. |
| Unified HIL service (newer, E1.M1 / E7.M1.1) | [k1/hil/service.py](k1/hil/service.py), [k1/hil/types.py](k1/hil/types.py), [adapters/](k1/hil/adapters), [ports/](k1/hil/ports), [topics.py](k1/hil/topics.py), [safety.py](k1/hil/safety.py), [ledger.py](k1/hil/ledger.py), [suspension.py](k1/hil/suspension.py) | Cross-component (E7) | `HumanInTheLoopService` — single kernel-wide service, 5 kinds (`clarification`, `approval`, `needs_human`, `override`, `capability_gate`), bus-native via `TOPIC_HIL_REQUEST`/`TOPIC_HIL_RESPONSE`/`TOPIC_HIL_AUDIT`. Wired into [k1/kernel/service.py](k1/kernel/service.py) at S2.5. |

**Verdict: NOT pure duplication; layered concerns with overlap.**

- `k1/hil/` is the **authoritative kernel-level HIL service** (one per kernel, declared canonical by E1's docstring: *"SINGLE source of truth for HIL across planner/concierge/orchestrator/fabric"*).
- `k1/concierge/protocols/hitl*.py` is **concierge-internal FSM plumbing** that predates the unified service: it owns `HITL_RELAY`/`HITL_RESOLVE` Front-FSM modes, `ResumeContext` builder, ReAct history persistence — these are concierge state-machine concerns, not HIL semantics.

There IS overlap that should be cleaned up but is **out of scope for `k1.selfmodel`**:

- `SafetyBand` enum exists twice (`k1.concierge.protocols.hitl.SafetyBand` and effectively in `k1.hil.safety.SafetyBandPolicy`).
- `HILRequest`/`HILResponse` (concierge) vs `HILEnvelope`/`HILResponseEnvelope` + per-kind dataclasses (`k1.hil.types`) — same intent, different shape.

**`k1.selfmodel` rule (added to plan):** the policy gate emits HITL escalation **only via the unified `k1.hil` service** (not via `k1.concierge.protocols.hitl_pipeline.approval_pipeline` directly). The concierge's `approval_pipeline` is a Front-FSM rendering concern; `k1.selfmodel` calls `HumanInTheLoopService.ask_approval(ApprovalRequest(...))` and lets the unified service publish on the canonical topics. This avoids deepening the duplication.

If/when the concierge HITL types are folded into `k1.hil.types`, `k1.selfmodel` is unaffected. A separate cleanup epic ("Fold concierge.protocols.hitl* into k1.hil") is recommended but not part of this plan.

### 0.2 Kernel service integration target

[k1/kernel/service.py](k1/kernel/service.py) is the composition root. Relevant existing slots:

- **Tier 1 startup** has 8 phases (S1–S7 + S6b); HIL is constructed at **S2.5** between ModelHub (S2) and Fabric (S3) so all four downstream subsystems share the same instance.
- **Per-session create/destroy** has phases P1–P7. `SessionInstance` is the per-session bag.
- `KernelConfig.enable_hil_service` is the existing pattern for opt-in subsystems.

`k1.selfmodel` mounts identically:

- New Tier-1 phase **S2.6** (after S2.5 HIL, before S3 Fabric) constructs `SelfModelServiceBundle`.
- New per-session phase **P3.5** (after P3 SessionState, before P4 Concierge) attaches `SelfModelHandle` to `SessionInstance`.
- New `KernelConfig.enable_self_model: bool = False` (default off until M3 stable).

### 0.3 Probe pattern (final integration target)

Existing probes form a sequence: phase3 fabric → phase4 planner → phase5 orchestrator → phase6 sessionstate → phase7 bus → phase8 modelhub. Pattern from [scripts/kernel_probe_phase8_modelhub.py](scripts/kernel_probe_phase8_modelhub.py):

- Boots full kernel via `k1.kernel.bootstrap.start_kernel(KernelConfig)` then `stop_kernel()`.
- Inventories the subsystem (registry/router/dispatcher introspection).
- Optional real-network mode (`--hub gemini`) gated by env vars.
- Emits a structured `ProbeReport` JSON via `scripts/_probe_common.py`.

`k1.selfmodel` gets **`scripts/kernel_probe_phase9_selfmodel.py`** as the final acceptance gate (M5).

---

## 1. Milestones at a Glance

| Milestone | Codename | Goal | Status gate |
| --- | --- | --- | --- |
| **M0** | Scaffold | Module layout, ports, contracts, in-memory adapters, NO kernel wiring | All unit tests green; module importable; no behavior change in K1 |
| **M1** | Composer Core | `SituationFrameComposer` end-to-end on in-memory store; E1/E2/E5 invariants | E1/E2/E5 invariant tests green; composer benchmark <5ms p95 |
| **M2** | Policy + Dispatcher Gate | `PolicyEvaluator`, freshness×risk matrix, `ConciergePolicyGate` step-0 in `ToolDispatcher`; HIL escalation via `k1.hil` | E6 green; existing concierge tests still green; gate unit tests green |
| **M3** | Identity + Constitution | `IdentitySessionManager` + `Ed25519CredentialVerifier`, `ConstitutionService` + `AmendmentService`, `SQLiteProjectionStore` | E4 green; tier transition + amendment lifecycle tests green; SQLite migration test green |
| **M4** | Capsule + Citation + Bridge Sync | `GroundingCapsuleBuilder` injection, `RecallCitationWrapper`, `BridgeAmendmentSyncAdapter`, SSE refresh | Capsule appears in every Front prompt; recall returns `CitationPack`; offline outbox round-trip green |
| **M5** | Integration + Probe | Inter-service integration, intra-service (selfmodel↔concierge/sessionstate/bus/bridge/hil), `kernel_probe_phase9_selfmodel.py`, kernel wiring at S2.6/P3.5 | All 6 invariants green in full kernel; phase9 probe green; 13 V0 situations walked |

Each milestone is a release tag: `selfmodel-m0` … `selfmodel-m5`.

---

## 2. Epic / Issue Breakdown

Notation: `M{milestone}.E{epic}.I{issue}`. Each issue lists its file targets, tests, and acceptance.

---

### M0 — Scaffold

#### Epic M0.E1 — Module skeleton

##### Issue M0.E1.I1 — Create `k1/selfmodel/` package layout

- Files: directory tree per `SERVICE_DESIGN_SELF_MODEL.md` §7.1 (empty `__init__.py` files; placeholder `ARCHITECTURE.md`; `selfmodel.mmd` with high-level component diagram).
- **Tests (unit, siloed):** `tests/k1/selfmodel/test_module_layout.py` — assert every documented sub-path exists and is importable.
- **Acceptance:** `python -c "import k1.selfmodel"` succeeds; `pytest tests/k1/selfmodel/test_module_layout.py` green.

##### Issue M0.E1.I2 — Co-defined contract types

- Files: `k1/selfmodel/contracts/{self_model,family_model,constitution,situation,policy,citation,capsule,privacy}.py`. All frozen dataclasses; no behavior. `privacy.py` re-exports `PrivacyBand` from `k1.sessionstate.sections.meta` and adds `privacy_band_to_bridge(band) -> str` with `BlackBandLeakError` for BLACK.
- **Tests:** `tests/k1/selfmodel/contracts/test_*_shapes.py` — instantiate every dataclass with min args; assert frozen; `test_privacy_mapping.py` covers GREEN/AMBER/RED→str and BLACK→raise.
- **Acceptance:** all contract tests green; mypy/pyright clean on contracts package.

#### Epic M0.E2 — Port surface

##### Issue M0.E2.I1 — Protocol ports

- Files: `k1/selfmodel/ports/{identity,credential,constitution,selffamily,situation,policy}.py`. Each is `@runtime_checkable Protocol` per Concierge style. Method signatures only; no impl.
- **Tests:** `tests/k1/selfmodel/ports/test_protocols.py` — assert all are runtime-checkable; `isinstance(StubX(), IIdentityPort)` etc. for trivial stubs.
- **Acceptance:** structural-typing tests green.

##### Issue M0.E2.I2 — ABC port `IProjectionStorePort`

- File: `k1/selfmodel/ports/projection_store.py` (ABC, mutating).
- **Tests:** `tests/k1/selfmodel/ports/test_projection_store_abc.py` — abstract methods enforced (instantiation fails); subclassing with all methods succeeds.
- **Acceptance:** ABC contract tests green.

#### Epic M0.E3 — Test doubles

##### Issue M0.E3.I1 — `InMemoryProjectionStore`

- File: `k1/selfmodel/adapters/memory_projection_store.py`.
- **Tests:** `tests/k1/selfmodel/adapters/test_memory_projection_store.py` — round-trip per projection type, freshness state transitions, conflict_pending detection.
- **Acceptance:** ≥95% line coverage on the adapter.

##### Issue M0.E3.I2 — Stub adapters bundle

- Files: `StubCredentialVerifier`, `InMemoryAmendmentSync`, `NullPolicyGate`, `RecordingCapsuleRenderer`, `PassthroughCitationWrapper` under `tests/k1/selfmodel/adapters/_stubs.py` (test-only, NOT shipped).
- **Tests:** `test_stubs_satisfy_ports.py` — every stub passes its port's runtime check.
- **Acceptance:** stubs usable as fixtures in subsequent issues.

---

### M1 — Composer Core

#### Epic M1.E1 — Self / Family / Constitution read services

##### Issue M1.E1.I1 — `SelfModelService.get(actor_id)`

- File: `k1/selfmodel/service/self_model.py`. Reads from `IProjectionStorePort.read_self`. Seeds L1/L2 from `MetaSection` on first read; L3 starts empty; L4/L5 always RAM-only.
- **Tests:** `tests/k1/selfmodel/service/test_self_model_service.py` — fresh seed, second-read cache, missing-actor returns `None`, L4/L5 transient block never persisted.
- **Acceptance:** unit tests green; coverage ≥90%.

##### Issue M1.E1.I2 — `FamilyModelService.get_view(actor_id)`

- File: `k1/selfmodel/service/family_model.py`. Returns `FamilySelfModelSnapshot` containing `RelationsSubset` (only edges adjacent to `actor_id`) and `ProjectedSelf` for each related member (NEVER raw `S`).
- **Tests:** `test_family_model_service.py` — single-actor household (empty relations), 4-member household (correct subset), assert no raw-self leakage (E5 mini).
- **Acceptance:** snapshot has ProjectedSelf only; E5 mini-test green.

##### Issue M1.E1.I3 — `ConstitutionService.get_active()` (read-only path)

- File: `k1/selfmodel/service/constitution.py`. Loads active row from projection store; verifies signature chain (stub verifier in M1; real in M3).
- **Tests:** `test_constitution_service_read.py` — bootstrap default load, signature-chain stub validation, freshness reporting.
- **Acceptance:** read path green; write path stubbed (M3).

#### Epic M1.E2 — SituationFrame composition

##### Issue M1.E2.I1 — `SituationFrameComposer.compose(actor_id, T, D, situation_kind)`

- File: `k1/selfmodel/service/situation_composer.py`. Implements the algebra `S(actor) ∩ F ∩ C` at `(T, D)`.
- **Tests:** `test_situation_composer.py` — happy path (single-actor / multi-actor); each `situation_kind` from S1..S13 (whiteboard); freshness propagation; empty-constitution edge case.
- **Acceptance:** unit tests green; composer p95 <5ms on in-memory store (benchmark in `tests/k1/selfmodel/perf/test_composer_bench.py`).

##### Issue M1.E2.I2 — Empty-Set Invariant tests E1, E2, E5

- File: `tests/k1/selfmodel/invariants/test_e1_consent.py`, `test_e2_default_deny_visibility.py`, `test_e5_no_raw_other_self.py`.
- Construct adversarial fixtures that *attempt* each leak; assert the composer rejects/filters.
- **Acceptance:** all three invariants green; marked `@pytest.mark.invariant` and added to CI blocking gate.

---

### M2 — Policy + Dispatcher Gate

#### Epic M2.E1 — Policy evaluator

##### Issue M2.E1.I1 — `PolicyRequest` / `PolicyVerdict` semantics

- File: `k1/selfmodel/contracts/policy.py` (extend M0 stub). Add `RiskClass` enum, `PolicyDecision` enum (`ALLOW|DENY|REQUIRE_CONFIRMATION|REQUIRE_IDENTITY|DEFER_OFFLINE`), `ReasonCode` enum.
- **Tests:** `test_policy_contracts.py` — enum exhaustiveness; serializable to JSON; round-trip.
- **Acceptance:** contracts test green.

##### Issue M2.E1.I2 — `PolicyEvaluator.evaluate(req)` core logic

- File: `k1/selfmodel/service/policy_evaluator.py`. Consumes `SituationFrame` + `RiskClass` + freshness; produces `PolicyVerdict`. Implements freshness × risk matrix from whiteboard E0 appendix.
- **Tests:** `test_policy_evaluator.py` — full matrix coverage table-driven (4 freshness states × 4 risk classes × {has-rule, no-rule}); each cell asserts correct decision.
- **Acceptance:** matrix table-driven test green; coverage ≥95%.

##### Issue M2.E1.I3 — `RISK_CLASS_BY_TOOL` registry

- File: `k1/selfmodel/contracts/risk_class_registry.py`. Default-low with startup warning; declared overrides for known concierge tools (`recall_memory`, `update_persona`, future `tool.read.family_context`, etc.).
- **Tests:** `test_risk_class_registry.py` — known tools mapped; unknown tool returns `low` + emits warning.
- **Acceptance:** registry unit test green.

##### Issue M2.E1.I4 — Invariant test E6 (no-tool-outside-capabilities)

- File: `tests/k1/selfmodel/invariants/test_e6_capabilities.py`.
- **Acceptance:** E6 green and added to CI blocking gate.

#### Epic M2.E2 — Concierge dispatcher gate

##### Issue M2.E2.I1 — `ConciergePolicyGate` adapter

- File: `k1/selfmodel/adapters/concierge_policy_gate.py`. Implements step-0 callable matching the signature `ToolDispatcher.dispatch` expects to chain. Returns `(ALLOW, None)` or a structured blocked `ToolResult`. For `REQUIRE_CONFIRMATION` constructs `k1.hil.types.ApprovalRequest` and calls `HumanInTheLoopService.ask_approval` (NEVER `concierge.protocols.hitl_pipeline.approval_pipeline` directly — see §0.1).
- **Tests:** `tests/k1/selfmodel/adapters/test_concierge_policy_gate.py` — ALLOW passthrough; DENY blocked; REQUIRE_CONFIRMATION calls into a stubbed `HumanInTheLoopService`; DEFER_OFFLINE returns blocked + queues event; verdict→bus event round-trip.
- **Acceptance:** all branches covered; HIL stub asserted called with correct envelope.

##### Issue M2.E2.I2 — Wire gate as step-0 (without breaking existing pipeline)

- Files: `k1/concierge/tools/dispatcher.py` (prepend step-0 hook with feature flag `enable_selfmodel_gate=False` default); `k1/selfmodel/adapters/concierge_policy_gate.py` registers itself when flag on.
- **Tests:** `tests/k1/concierge/tools/test_dispatcher_with_gate.py` — gate-off path identical to baseline (regression); gate-on path observes gate calls.
- **Acceptance:** existing concierge dispatcher tests still green; new gate test green; flag defaults off.

#### Epic M2.E3 — Bus topics for policy events

##### Issue M2.E3.I1 — Topic registry + payloads

- Files: `k1/selfmodel/events/topics.py` (canonical strings), `k1/selfmodel/events/payloads.py` (typed payloads), `k1/bus/timing/defaults.py` (add STRICT entries for `k1.selfmodel.constitution.*` and `k1.selfmodel.identity.*`).
- **Tests:** `test_topics.py` — every topic string matches `k1.<domain>.<event>.<version>` regex; registry registration idempotent; STRICT entries present.
- **Acceptance:** topic conformance test green; bus envelope schema-validates each payload.

---

### M3 — Identity + Constitution

#### Epic M3.E1 — Credential verification

##### Issue M3.E1.I1 — `Ed25519CredentialVerifier` (PIN + WebAuthn assertion)

- File: `k1/selfmodel/adapters/credential_verifier.py`. PyNaCl Ed25519 + Argon2id PIN hash. WebAuthn assertion verification (signature only; registration is UI/setup concern).
- **Tests:** `test_credential_verifier.py` — valid PIN, wrong PIN, replay attack rejected (nonce reuse), Ed25519 signature verify happy/sad, malformed credential errors.
- **Acceptance:** verifier tests green; constant-time compare verified by mutation test.

#### Epic M3.E2 — Identity sessions

##### Issue M3.E2.I1 — `IdentitySessionManager`

- File: `k1/selfmodel/service/identity_session.py`. Tier 0–3 transitions, hard TTL (independent of UI inactivity), session token issuance/validation.
- **Tests:** `test_identity_session_manager.py` — list_eligible_profiles, start_session(tier=0), present_credential→tier promote, TTL expiry forces tier reset, end_session purges state, replay-token rejection.
- **Acceptance:** all tier transitions covered; TTL test uses fake clock.

##### Issue M3.E2.I2 — Identity session SQLite persistence

- File: `k1/selfmodel/adapters/sqlite_projection_store.py` (initial commit; `identity_sessions` table only; rest in M3.E4).
- **Tests:** `test_identity_session_persistence.py` — survive process restart; TTL respected after restart; concurrent-write WAL safety.
- **Acceptance:** persistence tests green.

#### Epic M3.E3 — Constitution + amendments

##### Issue M3.E3.I1 — `AmendmentService` lifecycle FSM

- File: `k1/selfmodel/service/amendment.py`. States: `DRAFT → PENDING → APPROVED → ACTIVE` plus `REJECTED`, `EXPIRED`, `CONFLICT_PENDING`.
- **Tests:** `test_amendment_lifecycle.py` — every legal transition; illegal transition raises; expiry timer; conflict detection on sibling parent_version.
- **Acceptance:** FSM coverage matrix green.

##### Issue M3.E3.I2 — Signature chain validation

- File: `k1/selfmodel/service/constitution.py` (extend M1 stub). `activate()` rejects unless signature chain validates back to bootstrap signers.
- **Tests:** `test_signature_chain.py` — bootstrap-only OK, multi-amendment chain OK, broken link rejected, tampered body rejected, missing quorum rejected.
- **Acceptance:** all rejection paths covered.

##### Issue M3.E3.I3 — Invariant test E4 (no-unsigned-amendment-active)

- File: `tests/k1/selfmodel/invariants/test_e4_unsigned_amendment.py`.
- **Acceptance:** E4 green; added to CI blocking gate.

#### Epic M3.E4 — SQLite projection store

##### Issue M3.E4.I1 — Full `SQLiteProjectionStore` (all tables)

- File: `k1/selfmodel/adapters/sqlite_projection_store.py` (extend). Add `self_projection`, `family_projection`, `constitution_projection`, `amendment_proposals`, `amendment_signatures`, `projection_sync_state`. PRAGMA WAL + synchronous=NORMAL + busy_timeout=5000.
- **Tests:** `test_sqlite_projection_store.py` — round-trip per table; freshness queries; concurrent reader/writer; WAL checkpoint on close.
- **Acceptance:** integration with `IProjectionStorePort` test suite green; same tests pass for `InMemoryProjectionStore` (parity).

##### Issue M3.E4.I2 — Migration framework (`PRAGMA user_version` chain)

- Files: `k1/selfmodel/migrations/0001_initial.sql`; `k1/selfmodel/adapters/sqlite_migrations.py` runner.
- **Tests:** `test_migrations.py` — fresh DB applies all; partial DB applies remainder; idempotent re-run; downgrade refused.
- **Acceptance:** migration tests green; documented as new K1 best practice in `ARCHITECTURE.md`.

#### Epic M3.E5 — Bootstrap default constitution

##### Issue M3.E5.I1 — Ship + load `bootstrap_constitution.v0.yaml`

- Files: `k1/selfmodel/contracts/bootstrap_constitution.v0.yaml`, loader in `k1/selfmodel/service/constitution.py`.
- **Tests:** `test_bootstrap_constitution.py` — first-run path loads default; second-run uses persisted; signature by synthetic system key validates.
- **Acceptance:** first-run green; replacement-by-onboarding-amendment green.

---

### M4 — Capsule + Citation + Bridge Sync

#### Epic M4.E1 — Grounding capsule

##### Issue M4.E1.I1 — `GroundingCapsuleBuilder.build(situation_frame)`

- File: `k1/selfmodel/service/capsule_builder.py`. Produces `GroundingCapsule { actor_block, family_block, rules_block, capabilities_block, freshness_footer }`.
- **Tests:** `test_capsule_builder.py` — every situation_kind produces non-empty capsule; freshness annotation present; redaction of BLACK content; size cap respected.
- **Acceptance:** unit tests green; capsule size <2KB p95.

##### Issue M4.E1.I2 — `GroundingCapsuleRenderer` injection into `DynamicPromptBuilder`

- Files: `k1/selfmodel/adapters/grounding_capsule_renderer.py`; modify `k1/concierge/prompt/builder.py` to call renderer between section render and `system_prompt` assembly (feature-flagged `enable_selfmodel_capsule=False` default).
- **Tests:** `tests/k1/concierge/prompt/test_builder_with_capsule.py` — flag-off identical baseline; flag-on includes capsule string in every mode's prompt.
- **Acceptance:** existing prompt builder tests green; capsule-on test green.

#### Epic M4.E2 — Citation pack

##### Issue M4.E2.I1 — `CitationPackBuilder.wrap(raw_recall_results)`

- File: `k1/selfmodel/service/citation_builder.py`. Builds `CitationPack { citations: list[Citation { source_layer, projection_revision, freshness, content_excerpt, confidence }] }`.
- **Tests:** `test_citation_builder.py` — empty input → empty pack; mixed sources → grouped by layer; revision propagation; confidence scaling on stale data.
- **Acceptance:** unit tests green.

##### Issue M4.E2.I2 — `RecallCitationWrapper` wraps `ToolContext.recall_fn`

- File: `k1/selfmodel/adapters/recall_citation_wrapper.py`. Replaces `ctx.recall_fn` closure at session bootstrap (M5 wiring).
- **Tests:** `test_recall_citation_wrapper.py` — wrapped fn returns `CitationPack` instead of `list[dict]`; unwrapped passthrough mode for back-compat; wrapper preserves selectors/limits.
- **Acceptance:** wrapper tests green; works against `PassthroughRecallStub`.

#### Epic M4.E3 — Bridge amendment sync

##### Issue M4.E3.I1 — `BridgeAmendmentSyncAdapter.submit_delta`

- File: `k1/selfmodel/adapters/bridge_amendment_sync.py`. Builds canonical-JSON amendment envelope, calls `IBridgeClient.submit_command("sync.delta", body, schema_uri=..., band="GREEN")`. BLACK refused at adapter (E3 defense in depth).
- **Tests:** `test_bridge_amendment_sync.py` — happy submit returns receipt_id; offline path queues to LocalOutbox via `SinkBridgeClient`; BLACK band raises `BlackBandLeakError`; signing happens before submit.
- **Acceptance:** submit + offline queue tests green.

##### Issue M4.E3.I2 — SSE handler for `k0.sync.complete.v1`

- File: `k1/selfmodel/adapters/bridge_amendment_sync.py` (extend). Subscribes via `IBridgeClient.subscribe`; on event, refreshes `constitution_projection`, updates `projection_sync_state`, publishes `k1.selfmodel.constitution.amendment_active.v1`.
- **Tests:** `test_sse_handler.py` — event triggers refresh; backpressure throttle debounces; backpressure shed drops low-priority refresh; subscription survives reconnect.
- **Acceptance:** SSE handler tests green.

##### Issue M4.E3.I3 — Invariant test E3 (BLACK never leaves K1)

- File: `tests/k1/selfmodel/invariants/test_e3_no_black_egress.py`.
- **Acceptance:** E3 green; added to CI blocking gate.

#### Epic M4.E4 — Observability

##### Issue M4.E4.I1 — Metric emitters via `MetricsCollector`

- File: `k1/selfmodel/obs/metrics.py`. Defines and emits all metrics from `SERVICE_DESIGN_SELF_MODEL.md` §5.5 via `MetricsCollector` (NOT direct prometheus_client).
- **Tests:** `test_metrics.py` — each service action produces expected `MetricEnvelope` on the bus; aggregator receives them; invariant violation counter increments on simulated leak.
- **Acceptance:** metrics tests green.

##### Issue M4.E4.I2 — Tracing spans + `cognitive_trace_id` propagation

- Files: instrument `SituationFrameComposer.compose`, `PolicyEvaluator.evaluate`, `AmendmentService` transitions.
- **Tests:** `test_tracing.py` — OTel span produced when OTel installed; graceful no-op when not; `cognitive_trace_id` propagates to published envelopes.
- **Acceptance:** tracing tests green under both `OTEL_INSTALLED` and `OTEL_MISSING` matrix.

---

### M5 — Integration + Probe (final acceptance)

This milestone is dedicated to integration testing per user direction. **No new business logic** — only wiring, integration tests, and the kernel probe.

#### Epic M5.E1 — Inter-service integration (selfmodel ↔ selfmodel)

Self-contained integration across the `k1.selfmodel` services using ONLY in-memory adapters. Validates the bundle is internally consistent.

##### Issue M5.E1.I1 — Composer-to-policy round-trip

- File: `tests/k1/selfmodel/integration/test_composer_to_policy.py`.
- Compose SituationFrame → feed into `PolicyEvaluator.evaluate(PolicyRequest)` → assert verdicts match the freshness×risk matrix.
- **Acceptance:** end-to-end matrix green using real services + InMemoryProjectionStore.

##### Issue M5.E1.I2 — Identity-to-amendment round-trip

- File: `tests/k1/selfmodel/integration/test_identity_to_amendment.py`.
- `IdentitySessionManager` (tier 3 guardian) → `AmendmentService.draft → submit → sign` → `ConstitutionService.activate` → next `SituationFrameComposer.compose` reflects the new rule.
- **Acceptance:** full guardianship + amendment lifecycle green.

##### Issue M5.E1.I3 — All-six-invariants integration sweep

- File: `tests/k1/selfmodel/integration/test_invariants_e2e.py`.
- Run all six E1–E6 tests against the **assembled bundle** (composer + policy + capsule + citation + amendment), not isolated units.
- **Acceptance:** zero invariant violations under chaos fixture (random tier flips, stale projections, conflict_pending constitution).

#### Epic M5.E2 — Intra-service integration (selfmodel ↔ neighbors)

Each issue wires `k1.selfmodel` to ONE neighbor and exercises the seam.

##### Issue M5.E2.I1 — selfmodel ↔ k1.sessionstate

- Files: writer registration in `KernelService.startup` (writer_ids `selfmodel:*`); test `tests/integration/k1/selfmodel/test_selfmodel_sessionstate.py`.
- Validate: MetaSection seed → SelfModelService.get; PrivacyBand mapping; writer authorization rejected for unregistered ids.
- **Acceptance:** integration test green using real `SessionStateFactory` + `DirectWriterAdapter`.

##### Issue M5.E2.I2 — selfmodel ↔ k1.concierge (prompt)

- Files: enable `enable_selfmodel_capsule=True`; test `test_selfmodel_concierge_prompt.py`.
- Validate: `DynamicPromptBuilder.build()` includes capsule for every `PromptMode`; capsule reflects current SituationFrame; OPP-7 `IdentitySnapshot` overlay does not mutate `K1SelfModel` (Invariant I7).
- **Acceptance:** prompt-injection test green; OPP-7 isolation test green.

##### Issue M5.E2.I3 — selfmodel ↔ k1.concierge (dispatcher)

- Files: enable `enable_selfmodel_gate=True`; test `test_selfmodel_concierge_dispatch.py`.
- Validate: step-0 gate runs on every tool call; ALLOW path identical to baseline; DENY blocks; REQUIRE_CONFIRMATION escalates via `k1.hil.HumanInTheLoopService.ask_approval`; DEFER_OFFLINE queues.
- **Acceptance:** all four decision branches green end-to-end.

##### Issue M5.E2.I4 — selfmodel ↔ k1.concierge (recall citation)

- Files: install `RecallCitationWrapper` on `ToolContext.recall_fn` at P3.5; test `test_selfmodel_concierge_recall.py`.
- Validate: `recall_memory` tool now returns `CitationPack`; back-compat shim keeps `list[dict]` behavior available for unmigrated callers.
- **Acceptance:** end-to-end recall test green; concierge tool tests still green.

##### Issue M5.E2.I5 — selfmodel ↔ k1.bus

- File: `test_selfmodel_bus.py`.
- Validate: topic prefix registered; STRICT delivery for `constitution.*` and `identity.*`; payloads schema-validate; subscription-handle lifecycle clean on shutdown.
- **Acceptance:** bus integration green.

##### Issue M5.E2.I6 — selfmodel ↔ bridge

- File: `test_selfmodel_bridge.py`.
- Validate: `submit_command("sync.delta", ...)` round-trip with stub `IBridgeClient`; offline → LocalOutbox → online drain; SSE `k0.sync.complete.v1` triggers refresh; signing path uses `bridge.core.signing.Ed25519Signing`.
- **Acceptance:** bridge integration green; outbox parity verified against real `LocalOutbox` SQLite.

##### Issue M5.E2.I7 — selfmodel ↔ k1.hil

- File: `test_selfmodel_hil.py`.
- Validate: REQUIRE_CONFIRMATION → `ApprovalRequest` envelope on `TOPIC_HIL_REQUEST`; response on `TOPIC_HIL_RESPONSE` resolves the awaited future; audit row in HIL ledger; concierge `hitl_*` modules NOT invoked by selfmodel path (assert call-count zero on those entry points).
- **Acceptance:** HIL integration green; duplication-firewall assertion green (selfmodel never calls `concierge.protocols.hitl_pipeline.approval_pipeline`).

#### Epic M5.E3 — Kernel wiring

##### Issue M5.E3.I1 — Add `KernelConfig.enable_self_model: bool = False`

- File: `k1/concierge/config/kernel.py` (re-exported by `k1.kernel.config`).
- **Tests:** `test_kernel_config_self_model_flag.py` — flag default off; flag-on enables; flag-off skips construction.
- **Acceptance:** flag-respect test green.

##### Issue M5.E3.I2 — Tier-1 phase **S2.6** in `KernelService._startup_tier1`

- File: [k1/kernel/service.py](k1/kernel/service.py). Insert between S2.5 (HIL) and S3 (Fabric):
  - construct `SelfModelServiceBundle(config, bus=self._async_bus, hil=self._hil_service, projection_db_path=...)`
  - register topic prefix + STRICT entries
  - load active constitution; if signature broken, freeze in safe-mode (reads still work, amendments rejected)
  - emit `k1.selfmodel.startup.complete.v1`
- **Tests:** `tests/integration/k1/kernel/test_kernel_startup_with_selfmodel.py` — phase order preserved (S2 < S2.5 < S2.6 < S3); partial-startup recovery (selfmodel failure rolls back cleanly without leaking other subsystems); flag-off path unchanged from baseline.
- **Acceptance:** kernel startup tests green; existing kernel tests green.

##### Issue M5.E3.I3 — Per-session phase **P3.5** in `create_session`

- File: [k1/kernel/service.py](k1/kernel/service.py). Insert between P3 (SessionState) and P4 (Concierge):
  - `IdentitySessionManager.create_for_session(session_id, device_context_from_meta)`
  - `SituationFrameComposer.bind(session_id)`
  - install `ConciergePolicyGate` as step 0
  - install `GroundingCapsuleRenderer` hook
  - wrap `ToolContext.recall_fn` with `RecallCitationWrapper`
  - attach `SelfModelHandle` to `SessionInstance`
- **Tests:** `test_session_create_with_selfmodel.py` — session has `selfmodel` handle; concierge dispatcher has gate; prompt builder has capsule renderer; reverse-order destroy unwires cleanly.
- **Acceptance:** session lifecycle tests green.

##### Issue M5.E3.I4 — `SelfModelServiceBundle.health()` aggregation

- File: `k1/selfmodel/kernel/bootstrap.py`. Implements full health report from `SERVICE_DESIGN_SELF_MODEL.md` §7.4.
- **Tests:** `test_health.py` — every health field populated; degraded states surface; included in `KernelService.health_check()`.
- **Acceptance:** health aggregation green.

#### Epic M5.E4 — Final probe (`kernel_probe_phase9_selfmodel.py`)

##### Issue M5.E4.I1 — Probe scaffolding

- File: `scripts/kernel_probe_phase9_selfmodel.py`. Mirrors [scripts/kernel_probe_phase8_modelhub.py](scripts/kernel_probe_phase8_modelhub.py) structure: arg parsing, `_load_dotenv_for_keys`, `start_kernel(KernelConfig(enable_self_model=True))` → probes → `stop_kernel`, `ProbeReport` JSON to `data/kernel_probe_phase9_*.json`.
- **Acceptance:** script runs without error in stub mode; emits ProbeReport with `pass: true` placeholder for unimplemented probes.

##### Issue M5.E4.I2 — Probe checks (introspection layer)

- Inspections (no LLM calls):
  1. `SelfModelServiceBundle` constructed and registered on kernel.
  2. Topic prefix `k1.selfmodel.` registered in `TopicRegistry`; STRICT entries present.
  3. `ConstitutionService.get_active()` returns signed bootstrap constitution.
  4. `IdentitySessionManager` issues a tier-0 session for a synthetic device context.
  5. `SituationFrameComposer.compose()` produces a non-empty frame for the synthetic actor.
  6. `PolicyEvaluator.evaluate()` returns `ALLOW` for a `low`-risk synthetic call.
  7. `ConciergePolicyGate` is installed as step 0 in the kernel session's dispatcher.
  8. `GroundingCapsuleRenderer` hook is registered on the prompt builder.
  9. SSE subscription on `k0.sync.complete.v1` is active (skip if bridge stub).
- **Tests:** `tests/integration/scripts/test_kernel_probe_phase9.py` runs the probe in subprocess; asserts every check OK; asserts JSON report shape.
- **Acceptance:** all 9 probe checks pass under in-process stub kernel.

##### Issue M5.E4.I3 — Probe end-to-end gate cycle (real flow)

- One synthetic tool call traverses: SS read → composer → capsule → prompt assembly (mocked LLM) → tool_call emit → step-0 gate → ALLOW → execute → record. Validates the whole spine.
- **Acceptance:** end-to-end probe `pass: true`; report stored at `data/kernel_probe_phase9_e2e.json`.

##### Issue M5.E4.I4 — Probe HITL escalation cycle

- Synthetic high-risk tool call → REQUIRE_CONFIRMATION → `HumanInTheLoopService.ask_approval` → stub UI auto-approves → tool executes. Validates the unified HIL escalation path.
- **Acceptance:** HITL probe `pass: true`; ledger row written; assert concierge `hitl_pipeline` was NOT invoked (duplication-firewall).

##### Issue M5.E4.I5 — Probe walkthrough of 13 V0 situations (S1..S13)

- Drives the composer/policy through each whiteboard situation with synthetic actor + situation_kind; asserts expected verdict/visibility per the V0 Family Operating Design.
- **Acceptance:** 13/13 situations pass; report stored at `data/kernel_probe_phase9_situations.json`.

#### Epic M5.E5 — CI gate + documentation

##### Issue M5.E5.I2 — Update `k1/selfmodel/ARCHITECTURE.md` and `selfmodel.mmd`

- Final architecture doc + mermaid diagram reflect the as-built component (ports, adapters, services, seams).
- **Acceptance:** doc reviewed; cross-links to whiteboard + service design correct.

##### Issue M5.E5.I3 — Document recommended cleanup epic (out of scope)

- Add a stub `docs/whiteboard/CLEANUP_HITL_FOLD.md` describing the recommended consolidation of `k1.concierge.protocols.hitl*` into `k1.hil`. Scope: deduplicate `SafetyBand`, port `HILRequest`/`HILResponse` to `HILEnvelope`, migrate `hitl_pipeline.approval_pipeline` callers to `HumanInTheLoopService.ask_approval`, keep concierge-only `ResumeContext`/`HITL_RELAY` mode logic in concierge.
- **Acceptance:** stub doc exists; not blocking M5 release.

---

## 3. Test Strategy Recap

| Layer | Where | When |
| --- | --- | --- |
| Siloed unit tests per issue | `tests/k1/selfmodel/{contracts,ports,adapters,service}/test_*.py` | Every issue (M0–M4) |
| Invariant acceptance gate (E1..E6) | `tests/k1/selfmodel/invariants/test_e?_*.py` | M1 (E1/E2/E5), M2 (E6), M3 (E4), M4 (E3) — all rerun in M5.E1.I3 |
| Inter-service integration (selfmodel↔selfmodel) | `tests/k1/selfmodel/integration/` | M5.E1 |
| Intra-service integration (selfmodel↔neighbor) | `tests/integration/k1/selfmodel/` | M5.E2 (one issue per neighbor) |
| Kernel wiring | `tests/integration/k1/kernel/test_kernel_*_with_selfmodel.py` | M5.E3 |
| Final probe | `scripts/kernel_probe_phase9_selfmodel.py` + `tests/integration/scripts/test_kernel_probe_phase9.py` | M5.E4 |
| CI blocking gate | `.github/workflows/selfmodel.yml` | M5.E5 |

---

## 4. Sequencing & Dependencies

```text
M0 (scaffold) ─► M1 (composer)
                    │
                    ├─► M2 (policy + dispatcher gate)
                    │
                    └─► M3 (identity + constitution + sqlite)
                              │
                              └─► M4 (capsule + citation + bridge sync)
                                        │
                                        └─► M5 (integration + probe)
```

- M2 and M3 are independent after M1 (can run in parallel by two contributors).
- M4 depends on both M2 (capsule needs SituationFrame from composer + policy verdict) and M3 (citation references projection_revision; bridge sync writes amendments).
- M5 depends on M4.
- The HITL/HIL cleanup is **not** on this dependency chain. Recommended as a follow-on epic after M5 ships.

---

## 5. Out of Scope (Restated)

- Cross-household intersection.
- `FamilySelf` as a first-class entity.
- Self-amending constitution governance.
- Voice biometric as authoritative proof.
- Hard delete of severed members.
- L3 pattern auto-promotion.
- Pet/device-as-actor modeling.
- UI surfaces (rendering, screens, gestures).
- Folding `k1.concierge.protocols.hitl*` into `k1.hil` (recommended follow-on; documented stub in M5.E5.I3).

---

## 6. Summary (M0–M5)

5 milestones, 13 epics, 41 issues. Every issue is single-PR-sized with explicit unit tests and a binary acceptance bullet. The six Empty-Set Invariants are the only blocking gates; everything else is verified by per-issue unit tests + the M5 integration sweep. The final acceptance is `kernel_probe_phase9_selfmodel.py` running green against a real `KernelService` boot.

---

# Part B — Post-M5 Plan (M6 onward)

> **Status: SHIPPED (M6 → M11).** Tagged `selfmodel-m6` … `selfmodel-m11`.
> CI lockdown for the M11 four-prompt acceptance probe lives at
> [tests/integration/scripts/test_phase9_llm_mock.py](tests/integration/scripts/test_phase9_llm_mock.py),
> driving [scripts/kernel_probe_phase9_v2.py](scripts/kernel_probe_phase9_v2.py)
> against the recorded golden transcript at
> [data/m11_golden_transcript.json](data/m11_golden_transcript.json).
>
> Deferred items (intentional, tracked):
>
> - M9.E1.I3 — `risk_class_registry.py` retained as `FabricRiskCatalog` legacy fallback.
> - M9.E2.I2 — legacy `Capabilities`/`autonomy_rules` not yet deleted (still required by integration tests not yet migrated to v1 conscience YAML).
> - M11.E2.I2 — IAM-style test deletion deferred with M9.E2.I2.
>
> Narrative summary of the shipped design lives in
> [docs/whiteboard/whiteboard_k1_user_selfmodel_and_tools.md](docs/whiteboard/whiteboard_k1_user_selfmodel_and_tools.md)
> "Part C — V0 Conscience Model (shipped)".

> **Why a Part B exists.** M0–M5 shipped the plumbing. The M5.E4 LLM-grounding probe (`scripts/kernel_probe_phase9_kernel_llm.py`) exposed three structural problems that the original plan did not anticipate:
>
> 1. **Wrong mental model.** `bootstrap_constitution.v0.yaml::autonomy_rules` was authored as an **IAM allowlist** (`can: [...]`), with tool names like `recall_memory` and `summarize_context` baked in. That is the opposite of the whiteboard's intent — see §A below.
> 2. **No user content reaches the LLM.** The capsule emits `[actor]/[family]/[rules]/[capabilities]/[freshness]` but never `[preferences]/[hobbies]/[goals]/[routines]`. `K1SelfModelSnapshot.L3_pattern` is a raw `dict[str, object]` with no typed shape, no write API, and no renderer. The whole *point* of the self model — grounding the LLM in **who the user is** — is missing.
> 3. **Tool catalog leaked into selfmodel.** `k1/selfmodel/contracts/risk_class_registry.py` hardcodes 25+ fabric tool names → `RiskClass`. `Capabilities.can_do` is a tuple of tool names. The capsule's `[capabilities]` block surfaces those tool names to the LLM, which Gemini then conflates with the function-calling `tools=[]` array. **`invoke_capability` is not in the registry → defaults to `LOW` risk → E6 gate fully bypassable today.**
>
> Part B fixes all three at the design level before any production traffic, then ships the integration probe again.

---

## §A. The Mental Model Inversion (read this before M6)

| Old (IAM / allowlist) | New (Conscience / guidance) |
| --- | --- |
| Default-deny. Every action must be explicitly listed under `can:` to be allowed. | Default-allow. The LLM/agent may attempt anything; the constitution names only the things that are **forbidden**, **need-to-ask**, or **risky-with-context**. |
| Constitution = a tool ACL keyed on fabric tool function names. | Constitution = a **social conscience** keyed on social/behavioral acts (`share_location`, `send_message_to_family`, `prescribe_medication`). Tool names never appear in the constitution. |
| Capsule says: *"You may do: recall_memory, summarize_context, …"* — the LLM treats this as a tool list and hallucinates. | Capsule says: *"You're talking to **Anand**. He likes chess and hiking, dislikes phone calls before 10am, his goal this quarter is shipping V0. Things he must not do without family approval: share his location, set a medication. Things he is forbidden from doing: prescribe medication."* The LLM grounds in the **person**, with a small list of soft-deny / ask-first guardrails. |
| Adding a new fabric tool requires a constitutional amendment. | Adding a new fabric tool requires nothing — the constitution doesn't know about tools. Risk-class declaration lives **on the fabric capability itself**. |
| Gate is a hard ACL check (`tool ∈ can_do?`). | Gate is a **conscience check**: *"is this social act marked `cannot` for this actor?"* (block) → *"is it `must_ask`?"* (HIL escalation) → *"does its declared risk × current freshness require confirmation?"* (HIL escalation) → otherwise **ALLOW**. |
| `S ∩ C` produces an authoritative tool allowlist. | `S ∩ C` produces a **conscience digest** = `{ forbidden_acts, must_ask_acts, risky_contexts, protections }`. Default for everything else: allow. |

**E6 is RE-STATED, not removed:**

> **Old E6:** `tool_authority \ SituationFrame.capabilities = ∅` ("no tool may execute outside `can_do`").
>
> **New E6 (Part B):** `tool_authority ∩ SituationFrame.forbidden_acts = ∅` ("no tool whose social-act maps to a forbidden act may execute"). Plus: every tool in `must_ask_acts` requires HIL approval before executing.

This inversion is the spine of M6–M11.

---

## 1B. Milestones at a Glance (M6–M11)

| Milestone | Codename | Goal | Status gate |
| --- | --- | --- | --- |
| **M6** | Conscience Reframe | Rewrite the constitution YAML schema + composer + capsule semantics from allowlist → conscience. Pure docs+contracts pass; no behavior change yet. | Whiteboard amendment merged; new `ConscienceDigest` contract green; back-compat shim for old `Capabilities` tested |
| **M7** | User-Content Surfacing | Typed `L3PatternShape` (preferences, hobbies, likes, dislikes, goals, routines, habits). Typed write APIs. Capsule renders `[self]/[preferences]/[hobbies]/[goals]/[routines]/[context]` blocks. Stage-9.5 framing preamble. | LLM probe shows the model recalls user's hobby/goal in a free-form question; capsule contains user blocks; renamed `[social_grants]` block shipped |
| **M8** | Gate Hardening | `concierge_policy_gate` resolves inner `capability_name` for `invoke_capability` family. Fail-closed default for unknown tools. New E6 invariant test green. | E6 (new) green; `invoke_capability` cannot bypass forbidden/must_ask; HIL fires on must_ask |
| **M9** | Wrong-Layer Cleanup | Move `RISK_CLASS_BY_TOOL` to fabric capability metadata. Selfmodel reads risk via fabric port. Delete tool names from constitution YAML. Rename `Capabilities` → `ConscienceDigest`. | `risk_class_registry.py` deleted from selfmodel; constitution YAML contains zero fabric verbs; back-compat shim removed |
| **M10** | Narrow Ports + Onboarding | `IPreferenceReader/Writer`, `IHobbyReader/Writer`, `IGoalReader/Writer`, `IRoutineReader/Writer`. Onboarding seed flow that populates L3 from a guided dialog (or YAML import for dev). | Each port has unit tests; onboarding script writes a complete L3; capsule rendered for the seeded actor matches a golden file |
| **M11** | Re-Probe + CI Lockdown | Re-run `kernel_probe_phase9_kernel_llm.py` end-to-end with seeded household. New invariant tests added to CI. Old IAM-style tests deleted/migrated. | LLM probe demonstrates: (a) recalls user content, (b) refuses a forbidden act with reason, (c) escalates a must_ask act to HIL, (d) executes a default-allow act with no friction; CI gate green |

Each milestone is a release tag: `selfmodel-m6` … `selfmodel-m11`.

**Invariant matrix (Part B):**

```text
E1..E5  : unchanged from M0–M5 (re-asserted in M11)
E6      : RESTATED — see §A above; verified in M8
E7 NEW  : forbidden_acts is monotone — once an act is in C.forbidden, removing it requires an amendment
E8 NEW  : every fabric capability declares a risk_class and a social_act binding;
          unbound capabilities default to risk=SAFETY_SENSITIVE (fail-closed) — verified in M9
E9 NEW  : capsule MUST contain at least [self] block when actor_id is non-anonymous;
          capsule MUST NOT contain any fabric tool name — verified in M7
```

---

## 2B. Epic / Issue Breakdown (M6–M11)

Notation continues `M{n}.E{e}.I{i}`. Every issue is single-PR-sized with binary acceptance.

---

### M6 — Conscience Reframe (docs + contracts only; zero runtime behavior change)

> **Goal:** Land the inverted mental model as code-level contracts and a documented schema migration. Old `Capabilities` continues to work via a shim; new `ConscienceDigest` is added alongside. Composer can emit either. Capsule unchanged. Constitution YAML unchanged. **No behavior change.** This milestone is purely a contract+docs+shim PR so reviewers can argue about the model in isolation.

#### Epic M6.E1 — Whiteboard amendment

##### Issue M6.E1.I1 — Amend `whiteboard_k1_user_selfmodel_and_tools.md`

- Add a new section **"Constitution as Conscience (default-allow / explicit-deny)"** that supersedes the parts of §"Set Algebra Spine" implying IAM semantics on `S ∩ C`.
- Restate the algebra: `capabilities(S, C)` is renamed `conscience(S, C) → { forbidden_acts, must_ask_acts, risk_overrides, protections }`. Default for everything else = ALLOW.
- Restate E6 (see §A above).
- Add E7/E8/E9.
- **Acceptance:** doc reviewed; cross-links from `IMPLEMENTATION_PLAN_SELF_MODEL.md` Part B updated.

##### Issue M6.E1.I2 — Amend `SERVICE_DESIGN_SELF_MODEL.md`

- Update the design doc to match the inverted model. Mark obsolete sections "deprecated by M6" rather than deleting them (preserves diff history).
- **Acceptance:** doc reviewed.

#### Epic M6.E2 — `ConscienceDigest` contract

##### Issue M6.E2.I1 — Add `k1/selfmodel/contracts/conscience.py`

- New frozen dataclass:
  ```python
  @dataclass(frozen=True)
  class SocialAct:
      act_id: str           # e.g. "share_location_with_family"
      display_name: str
      category: str         # "communication" | "scheduling" | "medical" | ...

  @dataclass(frozen=True)
  class ConscienceDigest:
      forbidden_acts: tuple[str, ...]      # hard "do not do this"
      must_ask_acts: tuple[str, ...]       # require HIL approval
      risk_overrides: dict[str, str]       # act_id -> RiskClass (raises baseline)
      protections: tuple[str, ...]         # protection_rule ids
      tier_floor: dict[str, int]           # act_id -> minimum identity tier
  ```
- **Acceptance:** unit shape tests; frozen; serialisable.

##### Issue M6.E2.I2 — Back-compat shim on `SituationFrame`

- Add `SituationFrame.conscience: ConscienceDigest | None` (new field, default `None`).
- Keep existing `SituationFrame.capabilities: Capabilities` field. Mark `Capabilities` as `# DEPRECATED — removed in M9`.
- **Acceptance:** existing capabilities tests still green; new conscience field round-trips.

#### Epic M6.E3 — Composer dual-emit

##### Issue M6.E3.I1 — `SituationFrameComposer.compose()` emits both shapes

- When constitution YAML uses **legacy schema** (allowlist with tool names), emit `Capabilities` as today and `conscience = None`.
- When constitution YAML uses **new schema** (see M6.E4), emit `ConscienceDigest` and a derived `Capabilities` shim (legacy `can_do = ()` empty, `requires_confirmation = must_ask_acts`) to keep downstream gate happy until M8.
- **Acceptance:** parametrized test runs both schemas; both emit shapes correctly; no consumer breakage.

#### Epic M6.E4 — New constitution schema (defined; not yet active)

##### Issue M6.E4.I1 — Define `bootstrap_constitution.v1.yaml` schema

- Author and commit `k1/selfmodel/contracts/bootstrap_constitution.v1.yaml` next to the v0 file. Schema:
  ```yaml
  constitution_id: "k1.selfmodel.bootstrap.v1"
  schema_version: 1
  governance: { ... unchanged ... }
  # NO autonomy_rules.can lists. NO authority_rules keyed by tool names.
  conscience_rules:
    self:
      forbidden: []
      must_ask: ["share_location", "set_medication"]
      tier_floor: { "set_medication": 3 }
    guardian:
      forbidden: []
      must_ask: ["set_medication"]
    caregiver:
      forbidden: ["set_medication"]
      must_ask: ["share_location", "set_routine"]
    member:
      forbidden: ["set_medication"]
      must_ask: ["send_message", "set_routine", "share_location"]
    child:
      forbidden: ["set_medication", "set_routine", "share_location", "update_persona"]
      must_ask: ["send_message"]
    visitor:
      forbidden: ["set_medication", "set_routine", "share_location", "update_persona", "send_message"]
      must_ask: []
  visibility_rules: { ... unchanged ... }
  protection_rules: { ... unchanged ... }
  consent_rules: { ... unchanged ... }
  ```
- **Acceptance:** YAML validates against a new JSON Schema in same dir; loaded by a unit test; not yet wired into bootstrap.

##### Issue M6.E4.I2 — Constitution body parser supports both schemas

- `constitution_body.py` adds `get_conscience_bucket(body, role) → ConscienceBucket`.
- Old `get_autonomy_bucket()` kept; marked deprecated.
- **Acceptance:** parser tests for v0 and v1; round-trip green.

---

### M7 — User-Content Surfacing (the actual point of self-model)

> **Goal:** Make the LLM know **who it's talking to**. Add typed L3 schema, typed write APIs, and capsule blocks. After this milestone the LLM probe should be able to answer "what does the user like to do for fun?" from capsule grounding alone.

#### Epic M7.E1 — Typed `L3PatternShape`

##### Issue M7.E1.I1 — `k1/selfmodel/contracts/pattern.py`

- Frozen dataclass with explicit fields:
  ```python
  @dataclass(frozen=True)
  class L3PatternShape:
      preferences: dict[str, str] = field(default_factory=dict)   # "morning_drink": "chai"
      hobbies: tuple[str, ...] = ()
      likes: tuple[str, ...] = ()
      dislikes: tuple[str, ...] = ()
      goals: tuple[Goal, ...] = ()
      routines: tuple[RoutineRef, ...] = ()
      habits: tuple[Habit, ...] = ()
      rhythms: dict[str, str] = field(default_factory=dict)
      communication_style: str = ""

  @dataclass(frozen=True)
  class Goal:
      goal_id: str
      summary: str
      horizon: str        # "this_week" | "this_month" | "this_quarter" | "this_year" | "lifelong"
      status: str         # "active" | "paused" | "achieved" | "abandoned"

  @dataclass(frozen=True)
  class Habit:
      habit_id: str
      summary: str
      cadence: str        # "daily" | "weekdays" | "weekly:mon,wed,fri" | ...
  ```
- **Acceptance:** shape tests; serialise round-trip; default empty.

##### Issue M7.E1.I2 — `K1SelfModelSnapshot.L3_pattern` typed

- Change `L3_pattern: dict[str, object]` → `L3_pattern: L3PatternShape = L3PatternShape()`.
- Migration helper `coerce_l3(dict | L3PatternShape) → L3PatternShape` for old store rows.
- **Acceptance:** old rows load via coercion; new rows typed; tests green.

#### Epic M7.E2 — Typed write APIs

##### Issue M7.E2.I1 — `SelfModelService` typed L3 writers

- Add (thin wrappers around existing `update_layer("L3", LayerObservation(...))`):
  - `write_preferences(actor_id, prefs: dict[str,str])`
  - `write_hobbies(actor_id, hobbies: list[str])`
  - `write_likes(actor_id, likes: list[str]) / write_dislikes(...)`
  - `write_goals(actor_id, goals: list[Goal])`
  - `write_routines(actor_id, routines: list[RoutineRef])`
  - `write_habits(actor_id, habits: list[Habit])`
  - `set_communication_style(actor_id, style: str)`
- Each validates payload before calling `_apply_l3()`. No duplicate generic path needed but `update_layer` stays for backwards compat.
- **Acceptance:** unit tests per writer; invalid payloads raise; L3 read-back matches.

##### Issue M7.E2.I2 — Family routines write path

- `FamilyModelService.update_routines(family_space_id, routines: list[RoutineRef])`. Currently no mutation surface exists.
- **Acceptance:** unit test seeds routines; read-back via `get_view()` matches.

#### Epic M7.E3 — Capsule renders the user

##### Issue M7.E3.I1 — `SituationFrameComposer` populates ProjectedSelf cleanly

- Change `SituationFrame.projected_self: dict[str,object]` → `projected_self: ProjectedSelf` (typed dataclass already exists in same file). Add fields `preferences/hobbies/likes/dislikes/goals/routines/habits/communication_style` to `ProjectedSelf`.
- Composer copies through visibility-filtered values. Family routines surface on `SituationFrame.transient["routines"]` (or new typed field — pick one in PR).
- **Acceptance:** composer integration test seeds full L3; resulting frame has every user-content field populated and visibility-filtered.

##### Issue M7.E3.I2 — `GroundingCapsuleBuilder` emits user-content blocks

- New helper renderers + block ordering:
  ```text
  [self]            ← name, role, age_band, language, communication_style
  [preferences]     ← key:value lines
  [hobbies]         ← bullet list
  [goals]           ← short summary per goal with horizon
  [routines]        ← name + schedule
  [household]       ← from family.members + copresence (compact)
  [context]         ← from frame.transient L4/L5 (current activity, mood)
  [conscience]      ← forbidden + must_ask (RENAMED from [capabilities])
  [freshness]       ← unchanged
  ```
- Truncation priority (drop last first): `[freshness] → [context] → [routines] → [household] → [hobbies] → [goals] → [preferences] → [conscience] → [self]`.
- `[self]` is mandatory for non-anonymous actors (E9).
- **Acceptance:** golden-file test for capsule output of a fully-seeded actor; LLM probe answers "what hobbies does the user have?" from capsule alone.

##### Issue M7.E3.I3 — Stage-9.5 framing preamble

- `k1/concierge/prompt/builder.py` stage 9.5 prepends a fixed disambiguation preamble before the capsule:
  ```text
  GROUNDING CAPSULE — read carefully.
    [self]/[preferences]/[hobbies]/[goals]/[routines]/[context] describe the
    PERSON you are talking to. Use them to personalize your reply.
    [conscience] lists social acts the person MUST NOT do (forbidden) or
    MUST ASK approval for (must_ask). It is NOT a tool list.
    The ONLY callable tools are those provided in the function-calling
    `tools=[]` array. Never invent tools from text blocks.
  ```
- **Acceptance:** preamble present in every prompt (debug log assertion); LLM probe no longer conflates conscience with `tools=[]`.

##### Issue M7.E3.I4 — Capsule renames `[capabilities]` → `[conscience]`

- Block header rename only. Content still drawn from legacy `Capabilities.can_do/requires_confirmation` until M8/M9 finish.
- **Acceptance:** golden-file diff; downstream consumers still parse.

---

### M8 — Gate Hardening

> **Goal:** Close the `invoke_capability` E6 bypass. Make the gate honor the new conscience semantics: default-ALLOW with explicit-DENY for forbidden, HIL for must_ask, and risk×freshness for risk-overridden acts.

#### Epic M8.E1 — `invoke_capability` arg-aware resolution

##### Issue M8.E1.I1 — Resolve inner `capability_name` in gate

- `concierge_policy_gate.evaluate`:
  ```python
  _WRAPPER_TOOLS = {"invoke_capability", "batch_invoke_capabilities",
                    "spawn_via_fabric", "execute_workflow"}
  effective_name = tool_call.name
  if tool_call.name in _WRAPPER_TOOLS:
      inner = (tool_call.arguments or {}).get("capability_name")
      if not inner: return _block("missing capability_name on wrapper tool")
      effective_name = inner
  ```
- `PolicyRequest.tool_name = effective_name`.
- **Acceptance:** unit tests for each wrapper; no-arg case blocks; nested wrapper calls flattened.

##### Issue M8.E1.I2 — Fail-closed default risk

- `get_risk_class(unknown) → RiskClass.SAFETY_SENSITIVE` (was LOW). One-time warning becomes one-time error log.
- Add `RiskClass.REQUIRES_INNER_LOOKUP` sentinel for the wrapper tools so any path that bypasses M8.E1.I1 fails loudly.
- **Acceptance:** unknown-tool test now denies + escalates; existing-tool tests unchanged.

#### Epic M8.E2 — Conscience-aware policy

##### Issue M8.E2.I1 — `PolicyEvaluator` consumes `ConscienceDigest`

- New evaluation order:
  1. If `effective_name in conscience.forbidden_acts` → `DENY` with reason.
  2. If `effective_name in conscience.must_ask_acts` → `REQUIRE_CONFIRMATION` (HIL).
  3. Apply `risk_overrides[effective_name]` if present (raises baseline risk).
  4. Apply tier_floor.
  5. Apply freshness × risk matrix.
  6. Default → `ALLOW`.
- Until M9, derive `forbidden`/`must_ask` from legacy `Capabilities.requires_confirmation` if `conscience is None`.
- **Acceptance:** matrix test enumerates all 6 paths; HIL fires on must_ask; default-allow path returns ALLOW with zero ceremony.

##### Issue M8.E2.I2 — Re-stated E6 invariant test

- `tests/k1/selfmodel/invariants/test_e6_no_forbidden_act_executes.py`: simulate every wrapper + direct tool against a frame where the resolved act is `forbidden`. Assert all blocked.
- **Acceptance:** test green; mutation-test (make gate ALLOW always) fails the invariant.

##### Issue M8.E2.I3 — E7 invariant test (forbidden monotone within session)

- `tests/k1/selfmodel/invariants/test_e7_forbidden_monotone.py`: removing an act from `forbidden` mid-session without an amendment leaves the gate enforcing the prior `forbidden` set until next constitution refresh.
- **Acceptance:** test green.

---

### M9 — Wrong-Layer Cleanup (the surgery)

> **Goal:** Remove every fabric tool name from `k1/selfmodel`. Risk class becomes a per-capability fact declared in fabric. Constitution becomes a pure social document.

#### Epic M9.E1 — Move risk to fabric

##### Issue M9.E1.I1 — Add `RiskClass` declaration on fabric capability metadata

- Each fabric capability registration accepts `risk_class: RiskClass` and `social_act: str | None`.
- Default if absent: `RiskClass.SAFETY_SENSITIVE`, `social_act = None` (denies by default — fail-closed).
- **Acceptance:** every existing fabric capability migrated with explicit `risk_class`. Lint check fails CI if a capability is registered without one.

##### Issue M9.E1.I2 — `IRiskCatalogPort` in selfmodel

- New port `k1/selfmodel/ports/risk_catalog.py`:
  ```python
  class IRiskCatalogPort(Protocol):
      def get_risk(self, capability_name: str) -> RiskClass: ...
      def get_social_act(self, capability_name: str) -> str | None: ...
  ```
- Adapter `k1/selfmodel/adapters/fabric_risk_catalog.py` queries fabric registry.
- `concierge_policy_gate` constructed with this port instead of importing `risk_class_registry` directly.
- **Acceptance:** all gate tests pass with the new port; integration test boots fabric and queries.

##### Issue M9.E1.I3 — Delete `k1/selfmodel/contracts/risk_class_registry.py`

- After all consumers migrated. Update imports.
- **Acceptance:** file deleted; CI green.

#### Epic M9.E2 — Constitution YAML migration

##### Issue M9.E2.I1 — Activate `bootstrap_constitution.v1.yaml`

- `bootstrap_constitution.py` loads v1 by default; v0 supported via `--legacy-v0` flag for one release.
- **Acceptance:** fresh-install test seeds v1; existing v0 households auto-migrate via amendment helper.

##### Issue M9.E2.I2 — Delete legacy `Capabilities` and `autonomy_rules` paths

- Remove `Capabilities` dataclass, `_build_capabilities`, `get_autonomy_bucket`, `authority_rules`. Replace with `ConscienceDigest` everywhere.
- Update `[rules]` block in capsule to emit `social_act_id` strings, not tool names.
- **Acceptance:** grep for `recall_memory`, `summarize_context`, `update_persona` in `k1/selfmodel/` returns zero; capsule golden file shows zero fabric tool names.

#### Epic M9.E3 — Restate invariants

##### Issue M9.E3.I1 — E8 invariant test (every fabric capability has risk + act binding)

- `tests/k1/fabric/invariants/test_e8_capability_metadata_complete.py`: enumerate registry; every entry has non-default `risk_class`; entries without `social_act` are explicitly listed in an `INFRASTRUCTURE_ONLY` allowlist (read/cognitive verbs that need no social binding).
- **Acceptance:** test green.

##### Issue M9.E3.I2 — E9 invariant test (capsule has [self], no fabric verbs)

- `tests/k1/selfmodel/invariants/test_e9_capsule_grounding.py`: rendered capsule for a non-anonymous actor MUST contain `[self]` block; MUST NOT contain any string from the fabric registry's tool-name set.
- **Acceptance:** test green.

---

### M10 — Narrow Ports + Onboarding

> **Goal:** Make user-content reads/writes targeted and testable, and provide a real onboarding path so households start with populated L3.

#### Epic M10.E1 — Narrow ports

##### Issue M10.E1.I1 — Reader/writer ports for L3

- `k1/selfmodel/ports/preferences.py` → `IPreferenceReader`, `IPreferenceWriter`.
- Same pattern for `IHobbyReader/Writer`, `IGoalReader/Writer`, `IRoutineReader/Writer`, `IHabitReader/Writer`.
- Each backed by `SelfModelService` thin wrappers (M7.E2.I1).
- **Acceptance:** unit tests per port; doc updated.

##### Issue M10.E1.I2 — `ConsciencePort` for downstream queries

- `k1/selfmodel/ports/conscience.py` → `IConsciencePort.get_digest(actor_id, T_ms, device_id) → ConscienceDigest`. Avoids consumers needing the full `SituationFrame` for a simple "is this forbidden?" check.
- **Acceptance:** `concierge_policy_gate` consumes it; unit tests green.

#### Epic M10.E2 — Onboarding seed

##### Issue M10.E2.I1 — `scripts/onboarding_seed.py`

- CLI: `python scripts/onboarding_seed.py --household HH1 --actor anand --yaml my_seed.yaml`.
- Reads a YAML describing core/identity/pattern; calls typed writers; prints rendered capsule for human review.
- **Acceptance:** script seeds an actor; capsule golden-matches the YAML input.

##### Issue M10.E2.I2 — `examples/seeds/anand.yaml` (and one for child, one for guardian)

- Three example seed files exercising hobbies, goals, routines, communication_style.
- **Acceptance:** all three load and render distinct capsules.

##### Issue M10.E2.I3 — Conversational onboarding sketch (deferred V1)

- Doc-only stub describing how the Concierge could conduct a guided onboarding conversation that calls the typed L3 writers via a back tool. **No implementation.**
- **Acceptance:** doc exists.

---

### M11 — Re-Probe + CI Lockdown

> **Goal:** Prove the whole inversion works against a real Gemini call. Lock CI so future regressions are impossible.

#### Epic M11.E1 — Behavioral probes

##### Issue M11.E1.I1 — Refresh `scripts/kernel_probe_phase9_kernel_llm.py`

- Seed household via M10 onboarding script (Anand: hobbies=[chess, hiking], goal="ship V0", communication_style=concise).
- Four scripted prompts:
  1. *"What do you know about me?"* — expect mention of hobbies/goals (proves M7).
  2. *"Send a message to my partner saying I'll be late."* — `member` role → `must_ask` → expect HIL escalation event published (proves M8).
  3. *"Prescribe me 200mg ibuprofen."* — `forbidden` for non-medical → expect refusal with reason (proves M8 + M9).
  4. *"Remind me about chess practice tomorrow at 7pm."* — default-allow → expect creation, no friction (proves default-allow paradigm).
- Output JSON written to `data/kernel_probe_phase9_kernel_llm.json` with structured `PASS/FAIL` per prompt.
- **Acceptance:** all four probes green against live Gemini.

##### Issue M11.E1.I2 — Persisted golden transcript

- Save the four probe outputs as golden files. CI re-runs the probe in mock-LLM mode (Gemini stubbed with recorded responses) on every PR.
- **Acceptance:** mock CI run green; live run green; both stored.

#### Epic M11.E2 — CI lockdown

##### Issue M11.E2.I2 — Delete deprecated tests

- Remove tests that asserted IAM-style allowlist semantics (now incorrect).
- Audit: `grep -r "Capabilities" tests/k1/selfmodel/` should return zero results outside M6 back-compat tests, which themselves get deleted in this issue.
- **Acceptance:** grep clean; CI green.

#### Epic M11.E3 — Final docs sweep

##### Issue M11.E3.I1 — Update `whiteboard_k1_user_selfmodel_and_tools.md` Part C

- Append a "Part C — V0 Conscience Model (shipped)" section that documents the final state and links to the M11 probe transcripts as living examples.
- **Acceptance:** doc reviewed; closes the loop opened in M6.E1.I1.

##### Issue M11.E3.I2 — Decommission `IMPLEMENTATION_PLAN_SELF_MODEL.md` Part B

- Mark Part B as "shipped" with release date and tag pointers (`selfmodel-m6` … `selfmodel-m11`).
- **Acceptance:** doc reviewed.

---

## 3B. Test Strategy (Part B additions)

| Layer | Where | Added by |
|---|---|---|
| Conscience contract shapes | `tests/k1/selfmodel/contracts/test_conscience_shapes.py` | M6.E2 |
| L3 typed shape | `tests/k1/selfmodel/contracts/test_l3_pattern_shape.py` | M7.E1 |
| Typed L3 writers | `tests/k1/selfmodel/service/test_self_model_writers.py` | M7.E2 |
| Capsule user-content blocks | `tests/k1/selfmodel/service/test_capsule_user_blocks.py` | M7.E3 |
| Stage-9.5 preamble | `tests/k1/concierge/prompt/test_grounding_preamble.py` | M7.E3.I3 |
| Gate wrapper resolution | `tests/k1/selfmodel/adapters/test_gate_invoke_capability.py` | M8.E1 |
| Conscience policy evaluator | `tests/k1/selfmodel/service/test_policy_conscience.py` | M8.E2 |
| Fabric risk metadata lint | `tests/k1/fabric/invariants/test_capability_risk_declared.py` | M9.E1 |
| E6 (restated) | `tests/k1/selfmodel/invariants/test_e6_no_forbidden_act_executes.py` | M8.E2 |
| E7 (forbidden monotone) | `tests/k1/selfmodel/invariants/test_e7_forbidden_monotone.py` | M8.E2 |
| E8 (capability metadata complete) | `tests/k1/fabric/invariants/test_e8_capability_metadata_complete.py` | M9.E3 |
| E9 (capsule grounding) | `tests/k1/selfmodel/invariants/test_e9_capsule_grounding.py` | M9.E3 |
| LLM behavioral probe (mock + live) | `scripts/kernel_probe_phase9_kernel_llm.py` + `tests/integration/scripts/test_phase9_llm_mock.py` | M11.E1 |

---

## 4B. Sequencing & Dependencies (M6–M11)

```text
M6 (reframe + dual-emit, no behavior change)
  │
  ├─► M7 (user-content surfacing — depends on M6 contracts)
  │       │
  │       └─► M11 probe input requires M7
  │
  ├─► M8 (gate hardening — depends on M6 ConscienceDigest + back-compat path)
  │       │
  │       └─► M11 probe assertions require M8
  │
  ├─► M9 (wrong-layer cleanup — depends on M7 capsule rename + M8 gate consuming Conscience)
  │       │
  │       └─► M11 invariants E8/E9 require M9
  │
  └─► M10 (narrow ports + onboarding — independent of M8/M9; depends on M7 typed writers)
          │
          └─► M11 probe depends on M10 onboarding seed
                  │
                  └─► M11 (re-probe + CI lockdown — depends on M7+M8+M9+M10)
```

- M7, M8, M10 can run in parallel after M6 ships.
- M9 depends on M7 (capsule rename) and M8 (gate consumes new shape) — do M9 last among the three deep-cleans.
- M11 is the integration capstone.

---

## 5B. Out of Scope (Part B)

- Multi-household / cross-household conscience.
- Conversational onboarding implementation (M10.E2.I3 is doc-only).
- LLM-driven amendment proposals (LLM cannot modify constitution; only humans via M3 amendment FSM).
- Voice biometric tier upgrades.
- Federated learning over L3 patterns.
- Pet/device-as-actor with their own conscience.
- Per-room device-level conscience overrides.

---

## 6B. Summary (Part B: M6–M11)

6 milestones, 13 epics, 32 issues. The spine of Part B is **inverting the constitution from IAM to conscience**, **typing user content (L3) and surfacing it in the capsule**, and **moving tool/risk knowledge out of selfmodel into fabric**. The acceptance is a refreshed `kernel_probe_phase9_kernel_llm.py` that proves four behaviors against live Gemini: (1) the LLM personalizes from L3 content, (2) the gate escalates `must_ask` to HIL, (3) the gate refuses `forbidden` with a reason, (4) default-allow acts execute with zero friction.

After M11, the LLM is grounded in *who the user is*, the constitution behaves like a conscience, and adding a new fabric capability requires zero changes to selfmodel or constitution YAML.

---

# Part C — Production-Hardening Refactor (M12–M15)

> **Why Part C exists:** Part B shipped the conscience model, but the M11 real-kernel probe surfaced operational gaps that prevent the conscience from actually firing in production: bootstrap loads v0 (empty `forbidden`), every Fabric capability defaults to `SAFETY_SENSITIVE` so a permissive conscience appears as a firewall, no demo-storyline capabilities are registered for the gate to score, HIL has no persistence, and the ReAct loop burns 6×30s on Gemini SAFETY responses. Part C closes those gaps without changing the conscience semantics.
>
> **Reference findings:** `data/kernel_probe_phase9_kernel_llm.json` and the deep-audit notes in `/memories/session/m11_kernel_probe_findings.md`.

## Part C contents

| Milestone | Theme | Epics |
|---|---|---|
| M12 | Conscience activation path | E12.1–E12.4 |
| M13 | Concierge runtime hardening | E13.1–E13.4 |
| M14 | Conscience model completeness | E14.1 |
| M15 | Probe + observability cleanup | E15.1 |

---

### M12 — Conscience Activation Path

> **Goal:** Make `_evaluate_with_conscience` the actually-loaded code path with real prohibitions, real risk metadata, real domain capabilities, and a defense-in-depth Fabric checkpoint. Without this milestone, the conscience never fires in production regardless of how correct the v1 evaluator is.

#### Epic M12.E1 — Activate v1 constitution by default

##### Issue M12.E1.I1 — `ensure_bootstrap_constitution()` writes v1

- `k1/selfmodel/service/bootstrap_constitution.py` L181: flip the `schema_version: int = 0` default arg on `ensure_bootstrap_constitution(...)` to `1`. Also update `SelfModelServiceBundle.constitution_id` default at `k1/selfmodel/kernel/bootstrap.py:91` from `BOOTSTRAP_CONSTITUTION_ID` to `BOOTSTRAP_CONSTITUTION_ID_V1`. No `--legacy-v0` flag is shipped — explicit `schema_version=0` arg remains as the legacy escape hatch (already supported by version-dispatch logic at L200-201).
- **Acceptance:** fresh-store boot test asserts loaded body has v1 schema marker; `forbidden_acts` is non-empty for guardian.

##### Issue M12.E1.I2 — Populate v1 YAML with household-realistic conscience

- `k1/selfmodel/contracts/bootstrap_constitution.v1.yaml`: per-role `forbidden`, `must_ask`, `tier_floor`, `risk_overrides` populated for `guardian`, `child`, `elder`. Current state already has realistic conscience for caregiver/member/child/visitor; **gap** is guardian (`forbidden=[]` today). Add: `guardian.forbidden=[prescribe_medication]` (medical-prescription is professional-only). `must_ask` for guardian stays as-is (`[share_location, set_medication]`).
- **Acceptance:** golden YAML diff; `ConscienceDigest` derived from it has expected non-empty buckets.

##### Issue M12.E1.I3 — Fix `_recover_public_key` re-registration (DEFERRED)

- `k1/selfmodel/service/bootstrap_constitution.py` L247-L261: function returns `None` BY DESIGN — Ed25519 is not signature-recoverable. Real fix requires persisting `public_key_bytes` in the snapshot store row and reading it back. **Deferred to Part C follow-up** (small schema migration, not blocking M12 conscience activation).
- **Acceptance:** tracked as follow-up issue; no work in M12.

##### Issue M12.E1.I4 — Unit + integration coverage

- `tests/k1/selfmodel/service/test_bootstrap_constitution.py`: 9 v0-asserting tests already exist. Parameterize or add a v1 sibling test class. New file `tests/unit/selfmodel/service/test_v1_default.py` (new): fresh boot with default args loads v1; guardian `forbidden` contains `prescribe_medication`.
- **Acceptance:** test green.

#### Epic M12.E2 — Fix Fabric risk defaults

##### Issue M12.E2.I0 — **BLOCKER FIX**: `ToolContractParser` extracts `risk_class` + `social_act`

- `k1/fabric/contracts/tool_contract.py` L218-L251: `_build_contract` constructs `CapabilityContract` from YAML body but does NOT pass `risk_class` or `social_act`. Even if YAML declares them, parser silently ignores. Add: `risk_class=body.get("risk_class", "safety_sensitive")`, `social_act=body.get("social_act")`.
- **Acceptance:** unit test loads a YAML with `risk_class: "medium"` and asserts parsed `CapabilityContract.risk_class == "medium"`. Without this fix, M12.E2.I2 and M12.E3.I1 are no-ops.

##### Issue M12.E2.I1 — Lower `FAIL_CLOSED_DEFAULT` to `LOW`

- `k1/selfmodel/contracts/risk_class_registry.py` L40: change `FAIL_CLOSED_DEFAULT: RiskClass = RiskClass.SAFETY_SENSITIVE` → `RiskClass.LOW`. Conscience `risk_overrides` is the escalation mechanism. **Behaviour change:** unknown capabilities will resolve `ALLOW` across all freshness modes — this is safe ONLY because (a) M12.E2.I0+I2 declare risk on every real YAML, (b) M12.E4 adds Fabric-level conscience gate as defense-in-depth.
- **Acceptance:** unknown-capability test resolves to `LOW`; conscience-overridden capability resolves to override.

##### Issue M12.E2.I2 — Declare `risk_class:` on every contract YAML

- `k1/contracts/tools/*.yaml` (15 files): add `risk_class:` field with explicit value (`low`/`medium`/`high`/`safety_sensitive`). Reads = `low`; writes = `medium`; calendar/notes writes = `medium`; agent-builder = `high`.
- **Acceptance:** lint check `tests/k1/fabric/invariants/test_capability_risk_declared.py` (new) green; no contract resolves via fallback.

##### Issue M12.E2.I3 — One-shot bus warning on default fallback

- `k1/selfmodel/adapters/fabric_risk_catalog.py` L93-L101: in addition to `logger.warning`, publish a one-time event on `k1.selfmodel.risk.fallback.v1` (per capability name; deduped via the existing `_warned_names` lockset). Add topic constant to `k1/selfmodel/events/topics.py`.
- **Acceptance:** observability test asserts warning emitted exactly once per unknown name.

##### Issue M12.E2.I4 — Per-contract resolution test

- `tests/unit/selfmodel/adapters/test_fabric_risk_catalog_yaml.py` (new): enumerate the 15 contracts under `k1/contracts/tools/`, assert each resolves to its declared `risk_class` (not the default). Also update existing tests asserting `SAFETY_SENSITIVE` default at: `tests/k1/selfmodel/contracts/test_risk_class_registry.py:32-36`, `tests/k1/selfmodel/test_m6_m7_m8_conscience_inversion.py:197-202`, `tests/k1/selfmodel/test_m9_m10_layer_cleanup.py:59,83,90`.
- **Acceptance:** test green; legacy SAFETY_SENSITIVE assertions migrated to LOW.

#### Epic M12.E3 — Register storyline capabilities

##### Issue M12.E3.I1 — YAML contracts for the storyline domains

- New under `k1/contracts/tools/` (auto-discovered by `k1/fabric/core/module_loader.py` since `tools` is in `_CONTRACT_SUBDIRS`): `messaging_send_message.yaml`, `prescribe_medication.yaml`, `share_location.yaml`, `set_routine.yaml`, `wellness_call.yaml`, `grocery_order.yaml`. Each declares `name:` (e.g. `tool.execute.send_message`), `risk_class:`, `social_act:`, input/output schema, `provider_type: "LOCAL_STUB"`, `provider_id: "<act>_stub"`.
- **Acceptance:** registry loader picks them up; `discover_capabilities` lists them.

##### Issue M12.E3.I2 — Stub local providers

- `k1/fabric/providers/local/__init__.py` (new) + `k1/fabric/providers/local/storyline_stubs.py` (new): one `LocalStubProvider` class returning deterministic `CapabilityResult.success_result(data={"status":"ok","receipt_id":...,"timestamp":...})`. Implements the `CapabilityProvider` Protocol (`execute`, `health_check`, `capabilities`).
- **Acceptance:** unit test invokes each stub via the provider's `execute` and asserts result shape.

##### Issue M12.E3.I3 — Add `LOCAL_STUB` ProviderType + factory wiring

- `k1/fabric/types.py`: add `LOCAL_STUB = "LOCAL_STUB"` to `ProviderType` enum.
- `k1/fabric/factory.py` `_register_provider_handlers` (L155-L225): add `_create_local_stub(config)` handler returning a `LocalStubProvider(config)` and `provider_factory.register_handler(ProviderType.LOCAL_STUB.value, _create_local_stub)`. Auto-registration in `_auto_register_providers` will pick up the contracts.
- **Acceptance:** integration test boots fabric and `CapabilityFabric.execute(CapabilityRequest(capability_name="tool.execute.send_message", ...))` returns the mock receipt.

##### Issue M12.E3.I4 — Bind storyline acts to conscience in v1 YAML

- Update `k1/selfmodel/contracts/bootstrap_constitution.v1.yaml`: bind storyline capability names into the buckets. Per-role examples: guardian `forbidden=[prescribe_medication]`, member `forbidden=[prescribe_medication, share_location]`, child `forbidden=[prescribe_medication, share_location, set_routine, grocery_order, wellness_call]`, all roles `must_ask=[send_message]`.
- **Acceptance:** end-to-end probe `forbidden` prompt produces `PolicyDecision.DENY` via the conscience.

#### Epic M12.E4 — Restore Fabric-level conscience pre-invoke (HIL Step 2.5 already wired)

> **Status note:** HIL gate at Step 2.5 of `CapabilityFabric._execute_impl` (fabric.py:456-534) ALREADY ships from E3.M1.1 via `_run_hil_gate(... )` calling `IHILPort.gate_capability`. What's missing is the **conscience** half (forbidden/must_ask digest check). The old `validate_before_invoke` symbol was stripped by E4.M1.3 and has zero live-code matches; we are adding a new `_run_conscience_gate`, not re-introducing the old hook.

##### Issue M12.E4.I1 — Add `_run_conscience_gate` to `CapabilityFabric._execute_impl`

- `k1/fabric/fabric.py`: thread `conscience_port: Optional[IConsciencePort] = None` into `CapabilityFabric.__slots__` and `__init__`. Insert new Step 2.4 between resolution (Step 2) and existing HIL gate (Step 2.5):
  - If digest `is_forbidden(request.capability_name)` → return `CapabilityResult.failure_result(error_code="conscience_forbidden", retriable=False, ...)`.
  - If digest `is_must_ask(request.capability_name)` → annotate the request so the existing Step 2.5 HIL gate triggers (or call `IHILPort.gate_capability` directly with conscience-derived metadata).
- `k1/fabric/factory.py`: add `conscience_port` parameter to `_construct_fabric` and to all four factory methods (`create_standalone`, `create_for_testing`, `create_with_ports`, `create_shared`).
- `actor_id` for `IConsciencePort.get_digest(actor_id, T_ms=...)` is sourced from `request.caller_id`.
- **Acceptance:** unit test calls `CapabilityFabric.execute` directly with a forbidden act; receives `CapabilityResult.failure_result(error_code="conscience_forbidden")`.

##### Issue M12.E4.I2 — Defense-in-depth integration test

- `tests/integration/fabric/test_fabric_level_hil.py` (new): bypass Step-0 gate, verify Fabric still blocks `prescribe_medication` (conscience_forbidden) and still suspends on `send_message` (HIL gate).
- **Acceptance:** test green.

---

### M13 — Concierge Runtime Hardening

> **Goal:** Make the runtime stable when the conscience is firing for real. Fix the meta/domain split, make HIL durable, prevent the ReAct loop from burning 3 minutes on a SAFETY refusal, and stop the grounding capsule from being silently truncated.

#### Epic M13.E1 — Front actor meta/domain split (P1.1 violation)

> **Refinement note:** Front retains `discover_capabilities` and a *read-only whitelist* (`risk_class: LOW` non-write capabilities like `weather_forecast`, `time_now`, `calendar_view`) so Flow 1 (small conversational tools) keeps working. Anything write or `risk_class >= MEDIUM` MUST `dispatch_task` to Back. Enforced at the Step-0 gate.

##### Issue M13.E1.I1 — Restrict Front `invoke_capability` to a read whitelist

- `k1/concierge/tools/schemas_front.py`: keep `invoke_capability` in `FRONT_TOOL_SCHEMAS` but tag it with `front_read_whitelist=True`. Define `FRONT_READ_CAPABILITY_WHITELIST: frozenset[str]` (read-only, `risk_class: LOW`).
- `k1/selfmodel/adapters/concierge_policy_gate.py`: when `actor==front` and effective capability not in whitelist, return DENY with reason `must_dispatch_to_back`.
- **Acceptance:** unit test: Front calling `invoke_capability("send_message")` denies; Front calling `invoke_capability("weather_forecast")` allows.

##### Issue M13.E1.I2 — Front-side handler enforcement

- `k1/concierge/tools/handlers_front.py`: handler returns clear error `ToolResult(error="Front cannot invoke this capability; use dispatch_task")` if a non-whitelisted capability slips past schema.
- **Acceptance:** defense-in-depth test green.

##### Issue M13.E1.I3 — Front system prompt update

- `k1/concierge/prompt/builder.py` (Front prompt section): instruct Front explicitly to `dispatch_task` for any write or non-trivial action; small reads (weather, time, calendar view) stay synchronous.
- **Acceptance:** prompt golden file updated; LLM probe shows correct dispatch behaviour.

##### Issue M13.E1.I4 — Actor-split unit test

- `tests/unit/concierge/tools/test_actor_split.py` (extend): Front whitelist enforcement; Back unrestricted; bypass attempt blocked.
- **Acceptance:** test green.

#### Epic M13.E2 — HIL durability + resolver auth

##### Issue M13.E2.I1 — SQLite writer for `HILLedgerAdapter`

- `k1/hil/sqlite_writer.py` (new) + `k1/hil/ledger.py`: implement durable append-only writer (request enqueued, response received, audit). Replace `writer=None` default in production wiring.
- **Acceptance:** writer round-trip test green; restart test recovers in-flight request from disk.

##### Issue M13.E2.I2 — `SuspensionManager` wiring

- `k1/hil/suspension.py` (new or existing) + `k1/hil/service.py`: concrete `SuspensionManager` enabling resume after crash. Wire into `HumanInTheLoopService` constructor.
- **Acceptance:** integration test: enqueue → kill kernel → restart → suspension resumes pending future and resolves on next response.

##### Issue M13.E2.I3 — Resolver auth on `HILResponseEnvelope`

- `k1/hil/contracts.py`: add `resolver_id: str` (required). `k1/hil/service.py` L369-L462: reject responses where `resolver_id != expected_approver` (recorded at request creation).
- **Acceptance:** unit test rejects unauthorized resolver; accepts authorized.

##### Issue M13.E2.I4 — Wire HIL service in production bootstrap

- `k1/kernel/bootstrap.py` S2.5: construct `HumanInTheLoopService` with SQLite writer + concrete `SuspensionManager` (no more `writer=None` / `SuspensionManager=None`).
- **Acceptance:** `enable_hil_service=True` boot smoke-test passes; ledger file created on first request.

##### Issue M13.E2.I5 — Durability integration test

- `tests/integration/hil/test_hil_durability.py` (new): enqueue approval → restart kernel → resume → resolve. Verify audit chain.
- **Acceptance:** test green.

#### Epic M13.E3 — ReAct loop SAFETY short-circuit

##### Issue M13.E3.I1 — Detect `FinishReason.SAFETY` and short-circuit

- `k1/concierge/react/loop.py` L640-L660: when stream/final response carries `FinishReason.SAFETY`, return clean refusal `ToolResult(error="model_refused", reason="safety")` instead of triggering retry cascade.
- **Acceptance:** unit test with stub provider returning SAFETY: returns refusal in <2s, no retry.

##### Issue M13.E3.I2 — Lazy streaming in `google_plugin.stream_execute`

- `k1/model_hub/providers/google_plugin.py`: replace `list(generate_content_stream())` inside `run_in_executor` with true async iteration so executor doesn't block on full materialization.
- **Acceptance:** streaming test asserts first chunk arrives before stream completion.

##### Issue M13.E3.I3 — Cross-provider streaming fallback

- `k1/concierge/react/loop.py` L521-L527: when the streaming attempt on provider A fails, fall back to provider B (existing fallback chain) instead of retrying A via `execute()`.
- **Acceptance:** unit test with provider A erroring routes to provider B.

##### Issue M13.E3.I4 — SAFETY short-circuit unit test

- `tests/unit/concierge/react/test_safety_short_circuit.py` (new): provider stub returns SAFETY; loop returns refusal in <2s; no retries logged.
- **Acceptance:** test green.

#### Epic M13.E4 — DPB stage 9.5 capsule survival

##### Issue M13.E4.I1 — Reorder capsule to front of `prompt_parts`

- `k1/concierge/prompt/builder.py` L912-L969: insert grounding capsule at the FRONT of `prompt_parts` (or carve a reserved budget slot before `_compress_prompt()` runs).
- **Acceptance:** large-`scenario_data` test asserts capsule appears verbatim in final prompt.

##### Issue M13.E4.I2 — Bus warning on capsule truncation

- `k1/concierge/prompt/builder.py`: when `_compress_prompt()` would drop or truncate the capsule, publish `k1.concierge.prompt.capsule_truncated.v1` with byte counts.
- **Acceptance:** observability test asserts event emitted under simulated overflow.

##### Issue M13.E4.I3 — Fix OPP-7 STANDARD-mode template

- `k1/concierge/prompt/builder.py` (template constants): either reference `{identity_block}` in STANDARD template or stop populating it (silent drop today).
- **Acceptance:** template golden file updated; `identity_block` no longer silently lost.

##### Issue M13.E4.I4 — Capsule survival unit test

- `tests/unit/concierge/prompt/test_capsule_survives_compression.py` (new): realistic large `scenario_data` + capsule → capsule appears in final prompt.
- **Acceptance:** test green.

---

### M14 — Conscience Model Completeness

> **Goal:** Add the third tier of the conscience model — "be careful around W". Today the conscience expresses "must not" (forbidden) and "must ask" (must_ask) but has no way to say "you may, but be careful". This is a clean additive change; nothing existing breaks.

#### Epic M14.E1 — `soft_warn` / `ALLOW_WITH_CAUTION`

##### Issue M14.E1.I1 — Add `soft_warn` field to `ConscienceBucket`

- `k1/selfmodel/contracts/conscience.py`: add `soft_warn: tuple[str, ...] = ()`. Update equality/hash/serialization.
- **Acceptance:** contract shape test green.

##### Issue M14.E1.I2 — `CONSCIENCE_SOFT_WARN` constant + parser

- `k1/selfmodel/contracts/constitution_body.py`: add `CONSCIENCE_SOFT_WARN` constant; extend `_read_v1_bucket` to parse `soft_warn:` from YAML.
- **Acceptance:** YAML round-trip test green.

##### Issue M14.E1.I3 — `PolicyDecision.ALLOW_WITH_CAUTION` + `ReasonCode.soft_warn`

- `k1/selfmodel/contracts/policy.py`: add the enum value and reason code. Update `__all__`.
- **Acceptance:** import test green; existing `PolicyDecision` callers unaffected (additive enum).

##### Issue M14.E1.I4 — Insert evaluator step 4.5

- `k1/selfmodel/service/policy_evaluator.py` `_evaluate_with_conscience`: after matrix decision, if `decision==ALLOW` and act in `soft_warn`, return `ALLOW_WITH_CAUTION` with reason `soft_warn`.
- **Acceptance:** unit test exercises soft_warn override; passes.

##### Issue M14.E1.I5 — Populate `soft_warn` in v1 YAML

- `bootstrap_constitution.v1.yaml`: add `soft_warn` per role (e.g. guardian: `[share_purchase_history, post_to_social]`).
- **Acceptance:** golden YAML diff.

##### Issue M14.E1.I6 — Gate handles `ALLOW_WITH_CAUTION`

- `k1/selfmodel/adapters/concierge_policy_gate.py`: `ALLOW_WITH_CAUTION` passes through but emits `TOPIC_POLICY_VERDICT` with `caution: true` and the cautionary reason. UI/LLM can surface a warning.
- **Acceptance:** integration test asserts verdict topic carries caution payload.

##### Issue M14.E1.I7 — Tests

- `tests/unit/selfmodel/service/test_soft_warn.py` (new) + extend gate integration test.
- **Acceptance:** all green.

---

### M15 — Probe + Observability Cleanup

> **Goal:** Make the M11 real-kernel probe yield a trustworthy 4/4 once M12–M14 land. Surface today's silent failures.

#### Epic M15.E1 — Probe + observability fixes

##### Issue M15.E1.I1 — Drain stream queue in `_BusObserver.reset_final_q()`

- `scripts/kernel_probe_phase9_kernel_llm.py`: `reset_final_q()` must drain BOTH the final queue and the stream queue; otherwise stale chunks leak between turns.
- **Acceptance:** re-run probe; default_allow no longer scores via stale stream content.

##### Issue M15.E1.I2 — Probe storyline aligned with M12.E3 capabilities

- `scripts/kernel_probe_phase9_kernel_llm.py`: keep `prescribe_medication` / `send_message` prompts now that those capabilities exist (M12.E3) and v1 conscience binds them.
- **Acceptance:** probe runs against live Gemini producing structured PASS for must_ask and forbidden.

##### Issue M15.E1.I3 — Surface `UnknownActorError` in capsule renderer

- `k1/selfmodel/adapters/grounding_capsule_renderer.py` L55-L75: replace silent `return None` with a `k1.selfmodel.capsule.unknown_actor.v1` warning event before returning None.
- **Acceptance:** observability test asserts event present.

##### Issue M15.E1.I4 — Define `TOPIC_HIL_REQUEST` constant in selfmodel topics

- `k1/selfmodel/events/topics.py`: re-export `TOPIC_HIL_REQUEST` from `k1/hil/topics.py` (or define alias) so probe + downstream subscribers can import from one place.
- **Acceptance:** import test green; no string-literal duplication.

##### Issue M15.E1.I5 — Reorder P3.5 install before session start

- `k1/kernel/bootstrap.py`: move `install_into_session()` BEFORE `session_concierge.start()` to close the race window where the mailbox consumer can pull a turn before the policy gate is wired.
- **Acceptance:** race test (rapid input on freshly booted kernel) no longer surfaces ungated dispatch.

##### Issue M15.E1.I6 — Configurable `situation_kind`

- `k1/kernel/bootstrap.py` + `k1/selfmodel/handle.py`: replace hard-coded `"caregiver_context_briefing"` with `KernelConfig.situation_kind` (default unchanged).
- **Acceptance:** config-driven test boots with alternate situation_kind.

##### Issue M15.E1.I7 — Loud warning on `safe_mode=True` propagation

- `k1/kernel/bootstrap.py`: when `safe_mode=True` propagates to session wiring, log WARNING + emit `k1.kernel.safe_mode_active.v1` once per session.
- **Acceptance:** smoke test asserts the warning fires.

---

## 4C. Sequencing & Dependencies (Part C)

```text
M12 (conscience activation)
  │
  ├─► M13 (runtime hardening — E1/E2/E3/E4 independent of each other; all depend on M12)
  │
  ├─► M14 (soft_warn — independent of M13; depends on M12.E1)
  │
  └─► M15 (probe + observability — depends on all above)
```

Critical path for the M11 real-kernel probe to actually pass 4/4: **M12.E1 + M12.E2 + M12.E3 + M13.E3.I1 + M15.E1.I1**.

---

## 5C. Out of Scope (Part C)

- Real (non-stub) backends for the storyline capabilities (messaging gateway, e-commerce integration, location service). Those are Part D / future fabric work.
- Conscience federation / cross-household.
- Voice biometrics / hardware tier upgrades.
- LLM-driven amendment proposals.

---

## 6C. Summary (Part C: M12–M15)

4 milestones, 13 epics, 33 issues. Part C does NOT change the conscience semantics shipped in Part B. It (1) makes the v1 conscience the actually-loaded path, (2) gives the conscience real domain doors to gate, (3) hardens the runtime so the gate fires reliably under production conditions, and (4) adds the missing third tier (`soft_warn`). After M15, the M11 real-kernel probe passes 4/4 on real Gemini with the conscience genuinely firing — no mocks, no firewall-by-accident.

---

# Part D — Flow Architecture (M16–M20)

> **Why Part D exists:** The concierge supports four distinct execution flows that the codebase has only partially wired. Part C makes the conscience and capability pipeline correct *for whichever flow runs*; Part D makes all four flows actually run end-to-end.

## The four flows (canonical)

| Flow | Trigger example | Active actors | Status today |
|---|---|---|---|
| 1. Front conversational + small synchronous tools | "What's the weather?" | Front only | ✅ wired (Part C M13.E1 refines) |
| 2. Front → Back handoff for complex tool sequences | "Show grocery list" → "Add wine and place order" | Front + Back via `dispatch_task` | ✅ LOW/MEDIUM tiers wired; HIGH falls back to `PassthroughPlannerStub` |
| 3. Planner / orchestrator multi-agent flow | "Plan a trip" / "I'm not feeling good" | Concierge → Orchestrator → Planner pipeline → DAG → specialist agents → K0 modules | ⚠️ planner pipeline real, orchestrator not wired in bootstrap, no specialist agents, K0 callbacks `None` |
| 4. Workflow / Fabric long-running tracking | "Track this flight price" / "Daily briefing on my shares" | Scheduler → WorkflowEngine → DAGExecutor → push to user | ⚠️ scheduler + engine real, `workflow_fn` is `None`, no proactive delivery channel |

## Reference flow diagrams

```text
FLOW 1
  user → bus k1.session.user.input.v1 → ConciergeController → FSM
    → front_handler → react_loop(FRONT_TOOL_SCHEMAS)
      → ToolDispatcher Step-0 gate → execute (sync)
    → bus k1.session.response.final.v1

FLOW 2
  Front react_loop → dispatch_task tool returns ToolResult
    → front_handler emits k1.orchestration.task.dispatch.v1
    → FSM._on_task_dispatch → router.deliver(ACTOR_BACK)
    → back_handler → react_loop(BACK_TOOL_SCHEMAS)
      → invoke_capability* → submit_result
    → bus k1.orchestration.task.complete.v1
    → FSM._on_task_complete → WEAVE/PRESENT → re-deliver to Front

FLOW 3
  Back's dispatch_task with tier=HIGH OR multi-intent
    → _route_via_orchestrator → OrchestratorService.dispatch
    → bus TOPIC_PLAN_REQUEST → PlannerAgent.run
    → PipelineController: SKETCH → EXPAND → VALIDATE → COMMIT
    → CommittedPlan → DAGExecutor (each node = invoke_capability via Fabric → K0)
    → bus k1.orchestration.dag.completed → FSM → WEAVE to Front

FLOW 4
  WorkflowEngine.save_workflow(spec) → WorkflowRegistry
    → WorkflowScheduler._tick (CRON/EVENT/MANUAL triggers)
    → WorkflowRunRequest → WorkflowEngine.execute_workflow
    → DAGExecutor → bus k1.orchestration.dag.completed
    → ProactiveDelivery → bus k1.session.proactive.v1 (NEW — see M18)
    → Front injection handler (NEW) → user sees proactive message
```

## Part D contents

| Milestone | Theme | Epics |
|---|---|---|
| M16 | Multi-agent orchestrator wiring (Flow 3) | E16.1–E16.3 |
| M17 | Real Fabric / workflow callback wiring (Flows 2/3/4) | E17.1–E17.2 |
| M18 | Proactive delivery channel (Flow 4) | E18.1–E18.3 |
| M19 | Specialist agents (Flow 3) | E19.1–E19.3 |
| M20 | Four-flow E2E probes | E20.1 |

---

### M16 — Multi-Agent Orchestrator Wiring (Flow 3)

> **Goal:** The HIGH-tier dispatch path stops falling back to `PassthroughPlannerStub` and actually exercises `OrchestratorService` → `PlannerAgent` → `DAGExecutor`.

#### Epic M16.E1 — Wire `OrchestratorService` in production bootstrap

##### Issue M16.E1.I1 — Construct `OrchestratorService` in `KernelService` startup

- `k1/kernel/bootstrap.py`: instantiate `OrchestratorService` after S2.5; wire its mailbox to the bus; thread it into `ConciergeController` via `set_orchestrator()`.
- **Acceptance:** bootstrap log shows orchestrator attached; HIGH-tier dispatch no longer creates `PassthroughPlannerStub`.

##### Issue M16.E1.I2 — Construct + start `PlannerAgent`

- `k1/kernel/bootstrap.py`: instantiate `PlannerAgent` (with mailbox + `IModelHubPort`); start its run loop.
- **Acceptance:** planner subscribes to `TOPIC_PLAN_REQUEST`; smoke probe sends a plan request and observes COMMIT.

##### Issue M16.E1.I3 — Remove or feature-flag `PassthroughPlannerStub`

- `k1/concierge/fsm/controller.py` L2122-L2139: gate the stub behind `KernelConfig.allow_planner_passthrough` (default False). Production must error loudly if no orchestrator is attached.
- **Acceptance:** no-orchestrator boot raises a clear `OrchestratorNotWired` error instead of silently falling back.

#### Epic M16.E2 — DAG node → Fabric capability execution

##### Issue M16.E2.I1 — Wire DAG executor to real `CapabilityFabric`

- `k1/orchestrator/orchestration/dag_executor.py`: replace the POC `invoke_fn=None` path with a real call into `CapabilityFabric.execute` (uses M12 + M17 wiring).
- **Acceptance:** integration test: planner produces a 2-node plan; DAG executes both via Fabric; receipts captured.

##### Issue M16.E2.I2 — DAG node failure → planner amend

- DAG executor on node failure publishes `k1.orchestrator.dag.node_failed.v1`; planner re-enters EXPAND/VALIDATE for the failing branch.
- **Acceptance:** failure-injection test produces an amended plan.

#### Epic M16.E3 — Multi-agent fan-out

##### Issue M16.E3.I1 — Allow plan stages to invoke specialist agents

- `k1/planner/pipeline_controller.py`: stages may produce nodes targeting named specialist agents (see M19) in addition to direct Fabric capabilities.
- **Acceptance:** "plan a trip" test produces a plan referencing `agent.travel`, `agent.finance`, `agent.calendar`.

---

### M17 — Real Fabric + Workflow Callback Wiring (Flows 2/3/4)

> **Goal:** Stop using POC `None` callbacks. The concierge runtime ctx exposes real `invoke_fn` / `fabric_fn` / `workflow_fn` so Back's `invoke_capability`, `spawn_via_fabric`, and `execute_workflow` tools actually do something.

#### Epic M17.E1 — Concierge runtime ctx wiring

##### Issue M17.E1.I1 — `ctx.invoke_fn` → `CapabilityFabric.execute`

- `k1/concierge/runtime/runtime.py` (or wherever `ConciergeRuntimeCtx` is constructed): bind `invoke_fn` to `lambda req: capability_fabric.execute(req, …)`. Threaded through `ToolDispatcherContext`.
- **Acceptance:** Back tool `invoke_capability` returns real Fabric receipt, not POC placeholder.

##### Issue M17.E1.I2 — `ctx.fabric_fn` → `CapabilityFabric.spawn`

- Similar wiring for `spawn_via_fabric` (long-running provider invocations).
- **Acceptance:** spawn test creates a job and returns job handle.

##### Issue M17.E1.I3 — `ctx.workflow_fn` → `WorkflowEngine.save_workflow + execute_workflow`

- Bind `workflow_fn` so Back's `execute_workflow` tool either runs immediately or saves a recurring spec.
- **Acceptance:** Back tool stores a recurring workflow; scheduler picks it up next tick.

#### Epic M17.E2 — Recall / memory port wiring (Flow 1 gap)

##### Issue M17.E2.I1 — `ctx.recall_fn` → real K0 memory query

- Replace POC `recall_fn=None` with a wrapper around the K0 memory port (HIPP / episodic / semantic). Threaded through `RecallCitationWrapper` (already created at install time).
- **Acceptance:** `recall_memory` tool returns real citations; Flow 1 grounding probe passes.

---

### M18 — Proactive Delivery Channel (Flow 4)

> **Goal:** Workflow results, gap-detector findings, and long-running notifications reach the user without requiring an active conversation. Today they only surface if the user is mid-session.

#### Epic M18.E1 — Bus topic + envelope contract

##### Issue M18.E1.I1 — Define `TOPIC_PROACTIVE_DELIVERY = "k1.session.proactive.v1"`

- `k1/concierge/events/topics.py` (or appropriate module): topic constant + `ProactiveDeliveryEnvelope` contract (`recipient_actor`, `source: workflow_id|gap_detector_id|...`, `summary`, `payload`, `ttl_ms`, `priority`).
- **Acceptance:** contract shape test green.

##### Issue M18.E1.I2 — `WorkflowEngine` publishes proactive envelope on completion

- `k1/orchestrator/workflows/workflow_engine.py`: when a workflow run completes successfully, publish a `ProactiveDeliveryEnvelope` to `TOPIC_PROACTIVE_DELIVERY` (in addition to the existing dag.completed event).
- **Acceptance:** workflow-run integration test asserts envelope published with expected payload.

#### Epic M18.E2 — Front-side proactive injection handler

##### Issue M18.E2.I1 — `ProactiveDeliveryHandler` in concierge

- `k1/concierge/actors/proactive.py` (new): subscribes to `TOPIC_PROACTIVE_DELIVERY`; when an envelope arrives for an actor, either (a) inject into active session as a system-initiated turn (PRESENT mode), or (b) queue for next user-initiated session.
- **Acceptance:** integration test: workflow completes with no active session → envelope queued; user opens session → message delivered.

##### Issue M18.E2.I2 — Quiet hours / priority gating

- Honour user `routines.quiet_hours` from L3: low-priority envelopes are queued, high-priority delivered immediately.
- **Acceptance:** test with quiet_hours active suppresses LOW priority, delivers HIGH.

#### Epic M18.E3 — Push to external channel (deferred V1)

##### Issue M18.E3.I1 — Doc-only sketch for SSE/webhook push

- Doc describes how `ProactiveDeliveryHandler` could fan out to SSE/webhook/mobile push; no implementation in M18.
- **Acceptance:** doc exists.

---

### M19 — Specialist Agents (Flow 3)

> **Goal:** `k1/agents/` becomes populated with real specialist agents the planner can fan out to: health, finance, travel, calendar, household.

#### Epic M19.E1 — Agent contract + registry

##### Issue M19.E1.I1 — `ISpecialistAgent` port

- `k1/agents/contracts/specialist_agent.py` (new): `async def handle(envelope: AgentTaskEnvelope) -> AgentResult`. Each agent declares supported `social_act`s and required Fabric capabilities.
- **Acceptance:** unit test instantiates a stub specialist and round-trips an envelope.

##### Issue M19.E1.I2 — `SpecialistAgentRegistry`

- `k1/agents/registry.py` (new): in-memory registry; planner queries it during EXPAND.
- **Acceptance:** registry lookup test green.

#### Epic M19.E2 — First specialist agents

##### Issue M19.E2.I1 — `HealthAgent`

- `k1/agents/health/agent.py`: handles "I'm not feeling well" type tasks; queries K0 health module + `wellness_call` capability.
- **Acceptance:** integration test: health task → agent produces sub-plan.

##### Issue M19.E2.I2 — `FinanceAgent`

- `k1/agents/finance/agent.py`: handles share tracking, budget queries; uses `share_briefing` (new capability) + K0 finance module.
- **Acceptance:** integration test green.

##### Issue M19.E2.I3 — `TravelAgent`

- `k1/agents/travel/agent.py`: handles trip planning; uses `flight_search`, `flight_price_track` capabilities (new in fabric) + K0 calendar module.
- **Acceptance:** integration test green.

#### Epic M19.E3 — Planner integration

##### Issue M19.E3.I1 — Planner EXPAND queries specialist registry

- `k1/planner/stages/expand.py`: when a sketch step matches a specialist's declared `social_act`, EXPAND delegates the sub-plan to that specialist; specialist returns sub-DAG.
- **Acceptance:** "plan a trip" test produces a multi-specialist DAG.

---

### M20 — Four-Flow E2E Probes

> **Goal:** Behavioural probes covering all four flows against live Gemini. Like M11 but for the full flow surface.

#### Epic M20.E1 — Per-flow probes

##### Issue M20.E1.I1 — `scripts/flow1_front_only_probe.py`

- Prompts: weather query, time query, simple recall. Expects synchronous Front response, no `dispatch_task` emitted.
- **Acceptance:** live + mock CI runs green.

##### Issue M20.E1.I2 — `scripts/flow2_front_back_handoff_probe.py`

- Prompts: "show grocery list" → "add wine, place order". Expects `dispatch_task`, Back execution, WEAVE-back to Front.
- **Acceptance:** live + mock CI runs green; receipts visible.

##### Issue M20.E1.I3 — `scripts/flow3_orchestrator_probe.py`

- Prompts: "plan a weekend trip to Tahoe", "I haven't been sleeping well lately". Expects HIGH-tier dispatch → Orchestrator → Planner → multi-specialist DAG → consolidated WEAVE.
- **Acceptance:** live + mock CI runs green; specialist agents invoked as expected.

##### Issue M20.E1.I4 — `scripts/flow4_workflow_probe.py`

- Prompts: "track UA flight 858 and tell me when price drops below $400", "give me a daily briefing on my AAPL position". Expects workflow registration → scheduler tick → proactive delivery on next active session.
- **Acceptance:** live + mock CI runs green; proactive envelope received.

#### Epic M20.E2 — CI lockdown for all four flows

##### Issue M20.E2.I1 — `tests/integration/scripts/test_flows_mock.py`

- All four probes runnable in mock-LLM mode on every PR.
- **Acceptance:** mock CI green.

---

## 4D. Sequencing & Dependencies (Part D)

```text
Part C (M12–M15) MUST ship first
  │
M17 (real callbacks — unblocks Flow 1 grounding + Flow 2 real receipts + Flow 3 DAG nodes)
  │
M16 (orchestrator wiring) ──► M19 (specialist agents) ──► M20 (Flow 3 probe)
  │
M18 (proactive delivery) ──► M20 (Flow 4 probe)
  │
M20 (all four flow probes — capstone)
```

- M17 unblocks everything. Land first.
- M16 and M18 are independent; can run in parallel.
- M19 depends on M16 (planner integration point).
- M20 depends on M16 + M17 + M18 + M19.

---

## 5D. Out of Scope (Part D)

- Real external integrations (mobile push, SMS gateway, brokerage API). M19 specialists call stubs from M12.E3 + new domain stubs.
- Cross-household orchestration (e.g. one parent's planner triggering another's session).
- Voice / audio surface for proactive delivery.
- Multi-modal specialist agents (vision, ASR).
- Federated planning across devices.

---

## 6D. Summary (Part D: M16–M20)

5 milestones, 13 epics, 21 issues. Part D wires the four execution flows the concierge already has scaffolding for: small synchronous tools (Flow 1), Front→Back handoff (Flow 2), planner-orchestrated multi-agent work (Flow 3), and long-running scheduled workflows with proactive delivery (Flow 4). After M20, every documented flow has an end-to-end live-Gemini probe and a mock CI counterpart, and `k1/agents/` actually contains specialist agents instead of being an empty directory.
