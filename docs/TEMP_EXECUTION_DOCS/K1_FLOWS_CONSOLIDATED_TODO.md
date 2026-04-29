# K1 Flows §1–§8 — Consolidated Action List

**Source:** [§1](K1_FLOWS_SECTION1_CURRENT.md) · [§2](K1_FLOWS_SECTION2_CURRENT.md) · [§3](K1_FLOWS_SECTION3_CURRENT.md) · [§4](K1_FLOWS_SECTION4_CURRENT.md) · [§5](K1_FLOWS_SECTION5_CURRENT.md) · [§6](K1_FLOWS_SECTION6_CURRENT.md) · [§7](K1_FLOWS_SECTION7_CURRENT.md) · [§8](K1_FLOWS_SECTION8_CURRENT.md)
**Coverage:** F01–F87 (87 of 154 flows audited)
**Date:** 2026-04-28

Legend: ✅ wired · ⚠️ partial · ❌ missing · 🔵 deprecated-by-design / aspirational · 🟣 K0-undeployed-blocked

---

## Headline scoreboard (F01–F87)

| Section | Flows | ✅ | ⚠️ | ❌ | 🔵 | 🟣 |
|---|---|---|---|---|---|---|
| §1 Front-LLM (F01–F10) | 10 | 1 | 8 | 1 | — | — |
| §2 UltraBERT (F11–F32) | 22 | 8 | 6 | 2 | 6 | — |
| §3 Tool Execution (F33–F42) | 10 | 2 | 5 | 3 | — | — |
| §4 Orchestrator (F43–F52) | 10 | 6 | 2 | 2 | — | — |
| §5 Planner (F53–F59) | 7 | 5 | 2 | 0 | — | — |
| §6 Sub-Agent Lifecycle (F60–F65) | 6 | 3 | 3 | 0 | — | — |
| §7 SessionState (F66–F77) | 12 | 2 | 8 | 2 | — | — |
| §8 K0 Bridge (F78–F87) | 10 | 0 | 2 | 6 | — | 2 |
| **Total** | **87** | **27** | **36** | **16** | **6** | **2** |

**31% wired · 41% partial · 18% missing · 7% deprecated-by-design · 2% K0-blocked**

---

## 🚨 Top blockers (do these first)

1. **MS-3 K0 deployment** — gates F39/F40/F41 (§3), F56 (§5), F78/F79/F80/F81/F84/F85/F86/F87 (§8). Single biggest unblocker in the audit. (10+ flows)
2. **Wire `bus.subscribe("k1.agent.*.delta.v1", aggregator.collect)`** in concierge boot — entire delta-write path silently dead. Affects §6 F64/F65 and §7 F69. ([k1/concierge/factory.py#L644](../../k1/concierge/factory.py#L644))
3. **Replace `PassthroughPlannerStub`** in `controller.py#L2114` with real `PlannerAgent.mailbox` enqueue — single change unblocks all of §5 (F53–F58 end-to-end). Also fixes §1 F06.
4. **Implement `SectionDataAdapter`** + inject as `section_provider` into `EvictionEngine` (`audit-J` TODO at [manager.py#L545](../../k1/sessionstate/manager.py#L545)) — unblocks §7 F70, F71, F77 simultaneously.
5. **Wire `UltraBERTPhase1Pipeline` as default** when adapter healthy — unblocks F01/F02/F07 (§1) and F11–F19/F29 (§2).
6. **Implement `HttpTransport` + outbox drain** in `SinkBridgeClient` (currently forces OFFLINE on init) — required before any §8 flow can actually deliver to K0 even after MS-3.
7. **P3 demolition cleanup** (§2 F22) — delete `set/get_complexity_tier` shims, `_fsm_overlay` schema, `complexity_tier` param, `FRONT_TIER_ALLOWLISTS`, PoC demos. Removes 6 deprecated-by-design flows from the surface area.

---

## P0 — Critical path (do immediately)

| # | Action | Section | Touches | Anchor |
|---|---|---|---|---|
| 1 | **MS-3 K0 deployment** (`/k0/query.recall`, WAL, FAISS, P02/P03/P05) | §3, §5, §8 | F39, F40, F41, F56, F78, F79, F80, F81 | existing roadmap |
| 2 | Implement `HttpTransport` + outbox drain loop in `SinkBridgeClient` | §8 | F78, F79 | [bridge/client.py#L188](../../bridge/client.py#L188) |
| 3 | Wire `bus.subscribe("k1.agent.*.delta.v1", aggregator.collect)` in `_construct_concierge` Step 10 | §6, §7 | F64, F65, F69 | [k1/concierge/factory.py#L644](../../k1/concierge/factory.py#L644) |
| 4 | Implement `SectionDataAdapter` against `HotTier`/`WarmTier`, inject as `section_provider` into `EvictionEngine` | §7 | F70, F71, F77 | [k1/sessionstate/manager.py#L545](../../k1/sessionstate/manager.py#L545) |
| 5 | Wire `UltraBERTPhase1Pipeline` as default when adapter healthy | §1, §2 | F01, F02, F07, F11–F19, F22, F29 | [ultrabert_phase1.py#L29](../../k1/concierge/fsm/ultrabert_phase1.py#L29) |
| 6 | Replace `PassthroughPlannerStub` in `_route_via_orchestrator()` (HIGH path) with real `PlannerAgent.mailbox` enqueue | §1, §5 | F06, F53–F58 | [k1/concierge/fsm/controller.py#L2114](../../k1/concierge/fsm/controller.py#L2114) |
| 7 | Finish P3 demolition: delete `set/get_complexity_tier` shims + `_fsm_overlay` schema; drop `complexity_tier` param from `IdentitySnapshot.compute`; delete `FRONT_TIER_ALLOWLISTS`; clean PoC demos | §2 | F22, tooling | [control.py#L364,L770](../../k1/sessionstate/sections/control.py#L364) · [ultrabert_phase1.py#L259](../../k1/concierge/fsm/ultrabert_phase1.py#L259) |

---

## P1 — High-priority (next sprint)

| # | Action | Section | Touches | Anchor |
|---|---|---|---|---|
| 1 | Inject `AutoDiscoveryMCPTransport` (or any concrete `IMCPTransport`) at `KernelService._startup_tier1` Fabric construction | §3 | F34 | [k1/kernel/service.py#L1420](../../k1/kernel/service.py#L1420) · [fabric/factory.py#L368](../../k1/fabric/factory.py#L368) |
| 2 | Decide WASM strategy: ship real `wasmtime` runtime OR rename port to remove "Sandbox" misnomer | §3 | F36 | [k1/fabric/providers/wasm_provider.py](../../k1/fabric/providers/wasm_provider.py) |
| 3 | Implement `_compensate()` body — call `_step_runner.compensate()` or fabric undo, emit `ORCH_SAGA_COMPENSATING`, add at least one test | §4 | F46 | [dag_executor.py#L1142](../../k1/orchestrator/orchestration/dag_executor.py#L1142) |
| 4 | Populate `DAGExecutor.guards` with timeout + max-retries guards (M3) | §4 | F45, F51 | [dag_executor.py#L325](../../k1/orchestrator/orchestration/dag_executor.py#L325) |
| 5 | Verify `LLMGatewayAdapter` (V2) actually engages when `model_mode="hub"` (not silently falling back to `TestLLMAdapter`) | §5 | F53, F54, F55 | [k1/planner/adapters/llm_gateway_adapter.py#L9](../../k1/planner/adapters/llm_gateway_adapter.py#L9) |
| 6 | Add kernel smoke test exercising HIGH-tier prompt end-to-end through real planner pipeline (post-P0 #6) | §5 | F53–F58 | new |
| 7 | Wire periodic `pool.sweep()` background task in `KernelService._startup_*` so idle agents actually evict | §6 | F62 | [k1/fabric/providers/agent_provider.py](../../k1/fabric/providers/agent_provider.py) |
| 8 | Hook `AgentPool.drain_all()` into `KernelService` shutdown sequence | §6 | F63 | [k1/fabric/factory.py#L179](../../k1/fabric/factory.py#L179) |
| 9 | Wire `_preflight_fn`, `_write_fn`, `_evict_fn` into `DeltaApplicator` at kernel level (currently all `None`) | §7 | F69, F70, F76 | [k1/kernel/service.py#L1364](../../k1/kernel/service.py#L1364) |
| 10 | Hook `set_emergency_mode(True)` from `_trigger_eviction_if_needed()` when pressure breaches EMERGENCY; add exit path post-eviction | §7 | F74 | [k1/sessionstate/manager.py#L1063](../../k1/sessionstate/manager.py#L1063) |
| 11 | Wire `enforce_writer(section, role)` into `MutationGuard.preflight()` or `DirectWriterAdapter` — role matrix unenforced | §7 | F66 | [k1/concierge/delta/writer_registry.py#L123](../../k1/concierge/delta/writer_registry.py#L123) |
| 12 | Replace `SinkBridgeClient.subscribe()` empty iterator with real K0 SSE subscriber | §8 | F82 | [bridge/client.py#L220](../../bridge/client.py#L220) |
| 13 | Implement `k1/sse/` — `SSEEventHandler`, K0 SSE consumer, EventBus dispatch in `KernelService` | §8 | F82 | new (`k1/sse/__init__.py` empty) |
| 14 | Add `K0SessionCheckpointAdapter` + invoke from `StandaloneLifecycle` checkpoint timer; mirror `LocalColdArchive` writes to bridge | §8 | F84 | new |
| 15 | Emit `clarification.detected` from Front when LLM calls `update_clarifications` | §1, §2 | F02, F26 | [transition_table.py#L78](../../k1/concierge/fsm/transition_table.py#L78) |
| 16 | Loud-fail (or auto-construct stub Orchestrator) when `_orchestrator is None` in MED tier | §1 | F05 | [controller.py#L2171](../../k1/concierge/fsm/controller.py#L2171) |

---

## P2 — Medium-priority (build OR amend doc)

| # | Action | Section | Touches | Anchor |
|---|---|---|---|---|
| 1 | Decide F12/F13/F17: upgrade UltraBERT wheel to expose `intent_scores`/`domains[]`/typed relations OR delete dead multi-label code paths | §2 | F12, F13, F17, F20 | [ultrabert_adapter.py#L244](../../k1/concierge/fsm/ultrabert_adapter.py#L244) |
| 2 | Add `safety_confidence` and `sentiment_confidence` fields to `Phase1Result` (currently silently dropped) | §2 | F14, F18 | [ultrabert_adapter.py#L236](../../k1/concierge/fsm/ultrabert_adapter.py#L236) |
| 3 | Decide F30: change doc OR add `beliefs_active.add_entity()` call in `_write_phase1_to_ss` | §2 | F30 | [controller.py#L1700](../../k1/concierge/fsm/controller.py#L1700) · [beliefs_active.py#L415](../../k1/sessionstate/sections/beliefs_active.py#L415) |
| 4 | Once F39/F41 return real data: introduce `ContextBudgeter` (token-aware, recency+relevance) before LLM message assembly | §3 | F38, F42 | [react/loop.py#L950](../../k1/concierge/react/loop.py#L950) |
| 5 | Swap `SinkBridgeClient` for `KernelQueryPort` (HTTP) when K0 endpoint ships | §3 | F35, F39 | [k1/kernel/service.py#L1003](../../k1/kernel/service.py#L1003) |
| 6 | Decide F48 LLM-validator: build `SolutionValidator` (LLM+rule hybrid) OR amend doc to drop LLM leg | §4 | F48 | [k1/structure.md#L93](../../k1/structure.md#L93) |
| 7 | Decide F43/F44 multi-agent: build announcement/bid/scoring OR amend doc to drop and call out single-agent direct-dispatch | §4 | F43, F44 | [orchestrator_service.py#L1288](../../k1/orchestrator/orchestration/orchestrator_service.py#L1288) |
| 8 | Decide F59 strategy: build active DAG supervisor (poll/heartbeat) OR amend doc to "reactive on suspension only" | §5 | F59 | new |
| 9 | Wait on K0 MS-3 P05 for F56; add outbox consumer monitoring to detect unbounded growth | §5, §8 | F56 | new |
| 10 | Implement Epic 4.4 mailbox creation in `AgentFactory` Step 2 (replace `mailbox=None`) | §6 | F60 | planned |
| 11 | Decide F64/F65 strategy: dedicated `clarification` delta type + section, OR amend doc to "sub-agent output funnels into `history_active`" | §6 | F64, F65 | new |
| 12 | Add in-flight request guard in `Agent.drain()` to wait for pending `execute()` calls | §6 | F63 | new |
| 13 | Decide F73 (`EmergencySummarizer`): build LLM-compression class OR amend doc to "emergency = blocking only" | §7 | F73 | new |
| 14 | Decide F75 (`PriorityShedder`): implement using `MutationPriority` enum OR amend doc + remove enum | §7 | F75 | [k1/sessionstate/guard.py](../../k1/sessionstate/guard.py) |
| 15 | Wire or delete `ReconstructionSLA` — fully implemented but bypassed by `manager.restore()` | §7 | F72 | [k1/sessionstate/reconstruction.py#L130](../../k1/sessionstate/reconstruction.py#L130) |
| 16 | Reconcile budget: doc 95KB ↔ code 104KB; pick one, update both | §7 | F73, F77, doc | [k1/sessionstate/config.py#L31](../../k1/sessionstate/config.py#L31) |
| 17 | Build `k1/proactive/` — `ProactiveDecisionEngine`, `ProactiveAgentSpawner`, `ProactiveTriggerManager`, budget gate (depends on F82) | §8 | F83 | new (directory absent) |
| 18 | Implement `k1/retention/` — `RetentionPolicyEngine`, expiry scheduler, K0 scan + delete loop (depends on F84) | §8 | F85 | new (`__init__.py` empty) |
| 19 | Implement `UserDeletionHandler` (soft-delete API + bridge marker submission) | §8 | F86 | new |
| 20 | Port preliminary-ack from `poc/concierge_fsm_poc` into production FSM | §1 | F10 | [poc/concierge_fsm_poc/tests/test_loop.py#L316](../../poc/concierge_fsm_poc/tests/test_loop.py#L316) |

---

## P3 — Low-priority / cleanup / doc-rename

| # | Action | Section | Touches |
|---|---|---|---|
| 1 | Update K1_FLOWS.md to rename components to match code OR mark aspirational (whole doc) | §1 | doc |
| 2 | Decide whether `response.stream` and `user.ack` are real future work or doc artifacts | §1 | F08, F09 |
| 3 | Update K1_FLOWS.md §2 to mark F22–F28 deprecated-by-design; drop named-class fictions | §2 | doc |
| 4 | Update K1_FLOWS.md §3 to mark `ContextStager`/`TOOL_RESULT_BUFFER`/`WAL_DRIVER`/`VectorIndex`/`IEmbeddingPort`/`CAPABILITY_CONTEXT_BUILDER` as "not yet built" | §3 | doc |
| 5 | Confirm or wire `k1.capability.completed.v1` event emission inside `CapabilityFabric.execute()` | §3 | F37 |
| 6 | Delete `k1/scheduler/` and `k1/supervision/` empty stubs OR move workflow code there to match doc | §4 | structure |
| 7 | Rename in K1_FLOWS.md: `ConstraintManager` → `ConstraintResolver`, `ExecutionDAG` → `CommittedPlan` | §4 | doc |
| 8 | Add `PROACTIVE` trigger type if AI-initiated workflow runs needed; otherwise drop from doc | §4 | F50 |
| 9 | Document orchestrator → concierge HIL handoff path explicitly (delta_port HIL → FSM suspension) | §4 | F49 |
| 10 | Update K1_FLOWS.md §5 names: `PlannerAgent.sketch()` → `SketchService`, `PlanValidator` → `ValidateService`, `PlannerHIL` → planner-side `HILCoordinator`, "AMBER/RED" → `safety_band_min != GREEN`, "K0 P05" → outbox + event-bus | §5 | doc |
| 11 | Resolve `HILCoordinator` naming collision: rename to `PlannerHILCoordinator` / `ConciergeHILCoordinator` | §5 | F57, F58, F59 |
| 12 | Document `PlannerAgent` is Tier-1 shared with `asyncio.Lock` (single concurrent plan) | §5 | docs |
| 13 | Delete misleading `k1/agents/` stub directory OR move `agent_provider.py` content there | §6 | structure |
| 14 | Emit `k1.agent.*.lifecycle.v1` bus events on every state transition | §6 | F61, F62, F63 |
| 15 | Rename K1_FLOWS.md: `AgentLifecycleFSM` → inline `Agent` FSM, `DrainController` → `AgentPool.drain_all()`, `AggregationWindow` → `DeltaAggregator`, `SingleWriter` → `enforce_writer()` + `WriterRole`, `PENDING_CLARIFICATIONS` → `clarifications` | §6 | doc |
| 16 | Implement real model preload in `Agent.warm_up()` (currently pass-through) | §6 | F61 |
| 17 | Add periodic background eviction trigger (idle sessions don't shed) | §7 | F77 |
| 18 | Add per-section lazy COLD→HOT rehydration on read miss | §7 | F72 |
| 19 | Add copy-on-read or proper `RWLock` for HOT sections | §7 | F67 |
| 20 | Add JSON schema validation for write payloads in `MutationGuard.preflight()` | §7 | F76 |
| 21 | Rename K1_FLOWS.md per §7 drift cluster: `SingleWriter`/`RWLock`/`AggregationWindow`/`TieringManager`/`ColdStore`/`ReadOnlyGuard` | §7 | doc |
| 22 | Implement grace-period recovery handler + K0 restoration path (depends on F84+F86) | §8 | F87 |
| 23 | Implement `LearningExtractorAgent` (P06 routing) OR remove from doc | §8 | F78 |
| 24 | Decide if Concierge `DeltaAggregator` should forward to K0 P02; add K0 forwarding or update doc | §8 | F79 |
| 25 | Rename K1_FLOWS.md per §8 drift cluster; add explicit "K0 undeployed (MS-3)" callout to §8 header | §8 | doc |

---

## ❌ Missing / 🔵 deprecated / 🟣 K0-blocked — full inventory

### ❌ Missing (16 flows)

| F# | Section | Name | Build-or-drop? |
|---|---|---|---|
| F10 | §1 | Preliminary Ack Generation | port from PoC OR drop |
| F26 | §2 | Tiny Sanity Arbiter Validation | build `TinySanityArbiter` + `TRIGGER_CLARIFICATION_DETECTED` emit |
| F30 | §2 | NER → BELIEFS_ACTIVE | wire `add_entity()` OR amend doc |
| F40 | §3 | WAL Driver Query | K0-side build (P02 store) |
| F41 | §3 | Vector Semantic Search | build `IEmbeddingPort` + `VectorIndex` |
| F42 | §3 | Context Budget Application | build `ContextBudgeter` |
| F43 | §4 | Task Announcement & Bidding | build OR drop |
| F44 | §4 | Multi-Criteria Scoring & Selection | build OR drop |
| F73 | §7 | Emergency Summarization | build `EmergencySummarizer` OR drop |
| F75 | §7 | Emergency Priority Shedding | build `PriorityShedder` OR drop enum |
| F82 | §8 | K0 SSE → K1 EventBus | build K1 SSE consumer |
| F83 | §8 | SSE → Proactive Subsystem | build entire `k1/proactive/` |
| F84 | §8 | Session Checkpoint → K0 | build `K0SessionCheckpointAdapter` |
| F85 | §8 | Retention Expiry → Deletion | build `k1/retention/` |
| F86 | §8 | User Deletion → Soft Delete | build `UserDeletionHandler` |
| F87 | §8 | Grace Period Recovery | build (depends on F84+F86) |

### 🔵 Deprecated-by-design (6 flows, all §2)

All resolved by P3 demolition cleanup (P0 #7) + doc update:

| F# | Name |
|---|---|
| F22 | Complexity Classification |
| F23 | Hypothesis Generation |
| F24 | Contract & Signal Gap Detection |
| F25 | Context Inference |
| F27 | Uncertainty Estimation |
| F28 | Entropy-Min Question Planning |

### 🟣 K0-undeployed-blocked (2 flows, both §8)

| F# | Name |
|---|---|
| F80 | K0 P02 Episodic Pipeline |
| F81 | K0 P03 Consolidation |

---

## Cross-cutting themes (recurring across sections)

1. **Wiring seams, not missing components** — the dominant pattern in §4–§7 is that classes are real and constructed but not wired (`bus.subscribe`, `section_provider`, `_evict_fn`, `_preflight_fn`, `enforce_writer`, `set_emergency_mode`, `pool.sweep()`, `drain_all()`, `_compensate()` body, `mailbox=None`).
2. **K0 undeployment is the largest single bottleneck** — 10+ flows blocked across §3/§5/§8.
3. **Stub callbacks `=None`** at kernel wiring is a recurring anti-pattern: `DeltaApplicator` (3× None), `EvictionEngine.section_provider=None`, `DAGExecutor.guards=[]`, `mailbox=None`.
4. **Naming drift** between K1_FLOWS.md and code is pervasive — every section has a rename cluster. Single doc-cleanup pass would close ~10 P3 items.
5. **Two `HILCoordinator` classes** (planner-side + concierge-side) — naming collision needs resolution.
6. **Two `DeltaAggregator` classes** (MW-internal + Concierge-internal) — neither forwards to K0; one isn't subscribed to the bus.
7. **Empty `__init__.py` scaffolds**: `k1/sse/`, `k1/retention/`, plus missing `k1/proactive/` directory entirely.
8. **Decision-required items** (build OR amend doc) cluster in P2: F12/F13/F17 (UltraBERT wheel), F30 (NER), F43/F44 (multi-agent), F48 (LLM validator), F59 (DAG supervisor), F64/F65 (clarification deltas), F73 (summarizer), F75 (priority shedder), F79 (Concierge→K0).

---

## Suggested execution order

**Sprint 1 (unblock everything):**

- P0 #1 (MS-3 K0 deployment — likely parallel infra workstream)
- P0 #2 (HttpTransport + outbox drain) — pairs with #1
- P0 #3 (`bus.subscribe` for delta aggregator) — single-line fix, highest ROI
- P0 #4 (`SectionDataAdapter` for EvictionEngine) — unblocks 3 flows
- P0 #6 (replace `PassthroughPlannerStub`) — unblocks all of §5

**Sprint 2 (wire the seams):**

- P0 #5 (UltraBERT default)
- P0 #7 (P3 demolition cleanup)
- All P1 items (16 actions)

**Sprint 3 (decisions + new builds):**

- All P2 items — most are build-or-amend-doc decisions; resolve in design review then either implement or update K1_FLOWS.md

**Sprint 4 (cleanup):**

- All P3 items — doc renames + structural cleanup

---

## Outstanding sections (not yet audited)

| Section | Flows | Status |
|---|---|---|
| §9 Proactive (F88–F94) | 7 | Expected ❌ across the board (F83 found `k1/proactive/` missing) |
| §10 Fabric (F95–F103) | 9 | TBD |
| §11 Model Gateway (F104–F111) | 8 | TBD |
| §12 Experience (F112–F119) | 8 | TBD |
| §13 Rhythm (F120–F127) | 8 | TBD |
| §14 Module Loader (F128–F131) | 4 | TBD |
| §15 Event Bus (F132–F137) | 6 | TBD |
| §16 HIL (F138–F141) | 4 | TBD |
| §17 Observability (F142–F144) | 3 | TBD |
| §18 LLM Control Plane (F145–F154) | 10 | TBD |
| **Remaining** | **67** | — |
