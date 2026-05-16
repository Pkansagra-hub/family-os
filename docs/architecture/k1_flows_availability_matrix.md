# K1_FLOWS.md — Live-Kernel Availability Matrix (F01–F154)

> **Purpose.** [architecture_diagrams/k1/K1_FLOWS.md](architecture_diagrams/k1/K1_FLOWS.md) is the **vision** doc — 154 numbered flows
> drafted before development. This file enumerates which of those flows are
> actually exercisable on the **current** K1 kernel (hermetic Recipe-A boot
> per [live_kernel_wiring_test_procedure.md](live_kernel_wiring_test_procedure.md)), grounded entirely
> in [kernel_tracing_plan.md](kernel_tracing_plan.md) — no fresh code dig.
>
> **Status legend.**
>
> - ✅ **AVAILABLE** — Wired end-to-end; a Recipe-A live test can drive the
>   flow and assert all listed envelopes. Eligible for live-wiring SOP today.
> - � **PSEUDO-K0-AVAILABLE** — End-to-end via Recipe-C (K1 → Bridge →
>   pseudo-K0). Production K0 not yet wired, but the wire-level contract
>   round-trips today through [scripts/pseudo_k0/](scripts/pseudo_k0/).
> - 🟡 **PARTIAL** — Happy path runs but a documented GAP corrupts, silences,
>   or stubs part of it. Eligible for live test as an `xfail(strict=True)`
>   negative-wire probe.
> - 🔴 **BLOCKED** — A specific tracing-plan blocker prevents end-to-end
>   execution. Live test will fail until the blocker clears; must NOT be
>   marked as "live verified" yet.
> - ⚫ **NOT-IMPLEMENTED** — Code path is a stub, empty module, or simply
>   absent from the kernel. The vision flow has no current target to test.
> - ⚪ **LLM-COVERED** — Vision assumed a dedicated classifier model
>   (UltraBERT); the model was **intentionally removed** (1 GB RAM cost) and
>   the capability is now delegated to the LLM via `ModelHubPOCBridge` /
>   `IModelGatewayPort`. The flow is conceptually covered but not via the
>   originally-imagined dedicated head.
>
> **Method.** Every row cites a tracing-plan issue (`I…` / `ISSUE-…` / `OPEN §…`
> / `GAP-…`). If the tracing plan does not mention the flow at all, that itself
> is evidence of ⚫ (not implemented) and is marked `(not in plan)`.
>
> **2026-05-13 re-triage.** Two architectural decisions invalidate prior
> "BLOCKED" labels: **(a)** UltraBERT removed by design — F11–F23 reclassified
> from 🔴/⚫ to ⚪ LLM-COVERED; **(b)** Bridge MS-2.5 + MS-3a shipped — the
> previous "OPEN §5 / Bridge offline" blocker dissolves into LIVE / SINK /
> OFFLINE modes selectable at S4, with pseudo-K0 as the live integration
> target.

---

## Aggregate counts

| Status | Count | Share |
|---|---:|---:|
| ✅ AVAILABLE (hermetic Recipe-A) | 48 | 31 % |
| 🟢 PSEUDO-K0-AVAILABLE (Recipe-C) | 9 | 6 % |
| 🟡 PARTIAL | 33 | 21 % |
| 🔴 BLOCKED | 16 | 10 % |
| ⚫ NOT-IMPLEMENTED | 35 | 23 % |
| ⚪ LLM-COVERED (UltraBERT removed) | 13 | 8 % |
| **Total** | **154** | 100 % |

**Reality check.** With UltraBERT removed and Bridge active, **57 % of the
vision (✅ + 🟢 + ⚪ = 70 flows) is live-testable today**, **21 % runs with
documented silent-degradation GAPs (🟡)**, and only **10 % is hard-BLOCKED**
(mainly Agent path I3.4.5 and a few cross-cutting issues). The remaining
23 % is genuinely unbuilt (M6 stubs + vision-only engines).

---

## Section 1 — Main Conversation Loop (F01–F10)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F01 | User Input → ACKING | ✅ | E1.7 / I1.7.1 (UltraBERT removed; LLM-backed Phase-1 via ModelHub is production path) |
| F02 | Uncertainty Check & Clarification | ✅ | E1.6 + E1.8; LLM-driven Phase-1 produces real uncertainty score |
| F03 | Interrupt Handling | ✅ | E1.3 / I1.3.4 ConversationArbiter |
| F04 | LOW Tier Fast Path | ✅ | E1.1, E1.5 (LOW iter budget=6) |
| F05 | MEDIUM Tier Reasoning | ✅ | E1.5 MED + M4 E4.3 `_dispatch_medium` |
| F06 | HIGH Tier Planning | 🔴 | **I1.5.1 (Finding N6)** — K1 Orchestrator not wired on HIGH path; envelopes silently dropped |
| F07 | CRISIS Tier Safety Protocol | 🟡 | I1.7.4 + I6.11.H5 (`MockStateReadAdapter` in prod → safety gate always passes upstream); LLM-derived safety_band correct |
| F08 | LOW Tier Response Delivery | ✅ | E1.9 / I1.9.1 (WeavePolicy fallback) |
| F09 | MED/HIGH Tier Response Delivery | 🟡 | MED OK; HIGH inherits F06 (BLOCKED) |
| F10 | Preliminary Ack Generation | ✅ | E1.7 LLM-backed ack-LLM call |

## Section 2 — Phase-1 Classification (F11–F28)

> **2026-05-13 reclassification.** UltraBERT was a 1 GB multi-head BERT
> classifier intentionally removed from K1 to cut RAM. Every "UltraBERT
> head" is now delegated to the **LLM via ModelHub** (`IModelGatewayPort`).
> The vision's dedicated classifier flows are therefore ⚪ **LLM-COVERED**
> — conceptually present, but executed by the LLM call path, not by a
> standalone classifier model. See [kernel_tracing_plan.md §E1.7](kernel_tracing_plan.md).

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F11 | UltraBERT Core Forward Pass (22 ms) | ⚪ | I1.7.1 — model removed by design; LLM gateway covers classification |
| F12 | Intent Classification (Multi-Label) | ⚪ | LLM via ModelHub |
| F13 | Ingress/Domain Classification | ⚪ | LLM via ModelHub |
| F14 | Safety Band Classification | ⚪ | LLM via ModelHub; downstream gate I1.7.4 still active |
| F15 | Emotion Detection | ⚪ | LLM via ModelHub |
| F16 | NER Entity Extraction | ⚪ | LLM via ModelHub |
| F17 | Relations Extraction | ⚪ | LLM via ModelHub |
| F18 | Sentiment Analysis | ⚪ | LLM via ModelHub |
| F19 | Crisis Detection & Safety Override | ⚪ | LLM via ModelHub + I1.7.4 gate |
| F20 | Multi-Intent Scoring | ⚪ | LLM via ModelHub |
| F21 | Cross-Domain Detection | ⚪ | LLM via ModelHub |
| F22 | Complexity Classification | ⚪ | LLM via ModelHub feeds `complexity_router` |
| F23 | Hypothesis Generation | ⚪ | LLM via ModelHub |
| F24 | Contract & Signal Gap Detection | ⚫ | not in tracing plan |
| F25 | Context Inference | ⚫ | not in tracing plan |
| F26 | Tiny Sanity Arbiter Validation | ⚫ | not in tracing plan |
| F27 | Uncertainty Estimation | ⚫ | not in tracing plan |
| F28 | Entropy-Minimizing Question Planning | ⚫ | not in tracing plan |

## Section 2.5 — Phase-1 → SessionState updates (F29–F32)

> With UltraBERT removed, these flows now depend on the LLM-Phase-1 output
> actually being written into SS by the ack pipeline. Wiring exists for
> F31/F32; F29/F30 still need a concrete AFFECTIVE_NOW / BELIEFS_ACTIVE
> writer hookup from the LLM-extracted fields.

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F29 | Emotion → AFFECTIVE_NOW Update | 🟡 | LLM emits emotion; AFFECTIVE_NOW writer wiring not in tracing plan — verify under M1 |
| F30 | NER → BELIEFS_ACTIVE Update | 🟡 | LLM emits NER; BELIEFS_ACTIVE writer wiring not in tracing plan |
| F31 | Safety → CONTROL Update | ✅ | I1.7.4 wired to LLM-emitted safety_band |
| F32 | Intent/Ingress → CONTROL Update | ✅ | E1.7 fed by LLM-emitted intent |

## Section 3 — Capability Fabric / Tools / Memory (F33–F42)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F33 | Capability Fabric Tool Invocation | ✅ | E3.1.1 + E3.2 9-step pipeline |
| F34 | MCP Tool Execution | 🟡 | E3.4.1 OK with `TestMCPTransport`; real MCP servers not bundled |
| F35 | K0 Memory Operation | � | **Recipe-C:** K1 → Bridge LIVE → pseudo-K0 `/k0/command.submit` (M7 E7.2). Real K0 future. |
| F36 | WASM Sandbox Execution | ✅ | E3.4.3 (64 MB, no network) |
| F37 | Tool Result Return | ✅ | E3.2 STEP 9 |
| F38 | Tool Result → LLM Context Staging | ✅ | E1.2 Back snapshot-at-start |
| F39 | K0 Query Port Recall | 🟢 | **Recipe-C:** `recall.request.v1` via Bridge LIVE → pseudo-K0 LIKE search (M7 E7.3); FTS/vector faked |
| F40 | WAL Driver Query | 🟢 | pseudo-K0 `SQLiteK0Store` (M7 E7.3) |
| F41 | Vector Semantic Search | 🔴 | **I6.11.C5** — `IEmbeddingPort` not wired in shared Fabric S4 |
| F42 | Context Budget Application | ✅ | E3.2.5 + E3.9.2/.3 |

## Section 4 — Orchestration (F43–F52)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F43 | Task Announcement & Bidding | ⚫ | no bidding subsystem in tracing plan |
| F44 | Multi-Criteria Scoring & Selection | 🟡 | E3.1.5 capability soft-rank only; agent bidding absent |
| F45 | Parallel DAG Execution | ✅ | E4.5 / I4.5.1 Kahn waves |
| F46 | Saga Pattern Recovery | 🟡 | E3.11.4 `compensation_capability` AttributeError risk |
| F47 | Constraint Manager Iteration | ⚫ | no ConstraintManager in tracing plan |
| F48 | Solution Validation (LLM + Rule) | 🟡 | E3.2.10 Tier-3 ANNOTATEs only; LLM solution validator absent |
| F49 | Constraint HIL Fallback | ⚫ | depends on F47 |
| F50 | Workflow Scheduling & Trigger | 🟡 | **GAP-O03** — `_last_run` not persisted; CRON re-fires on restart |
| F51 | Workflow Run Supervisor | ✅ | M4 has WorkflowScheduler |
| F52 | Workflow Compiler → DAG | ✅ | E3.4.7 WorkflowProvider; cycle detection FAB-12 |

## Section 5 — Planner 4-Stage (F53–F59)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F53 | Stage 1 — Sketch Plan | 🟡 | E4.8 OK; **GAP-P03** ToolCallRouter uses semantic similarity for exact lookup |
| F54 | Stage 2 — Expand with Tools | ✅ | E4.9 deterministic infra fields |
| F55 | Stage 3 — Validation | 🟡 | E4.10 OK; **GAP-P04** ValidationVerdict bypass risk |
| F56 | Stage 4 — Commit to K0 | 🟡 | E4.11 emits `plan.ready.v1`; K0 persist fire-and-forget but K0 itself offline |
| F57 | Requirement Clarification HIL | ✅ | E4.8.2/.3 max-2 rounds |
| F58 | Plan Approval HIL | 🟡 | **GAP-O06** wave HIL over-interrupts (>3 steps OR >5 s) |
| F59 | Execution Monitoring HIL | 🟡 | same GAP-O06 |

**Cross-cutting blocker for the whole Planner path:** **GAP-P02 (HIGH)** —
`llm_gateway_adapter.py:185` imports `build_payload` from private module
([I4.15.1]); breaks at first real call without the private→public migration.

## Section 6 — Agent Lifecycle (F60–F64)

> Entire agent system gated by a single GAP: **I3.4.5** — AgentProvider
> `mailbox=None`. No agent can be spawned; all flows here are 🔴.

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F60 | Agent Spawn via Fabric | 🔴 | I3.4.5 |
| F61 | PENDING → WARMING → ACTIVE | 🔴 | depends on F60 |
| F62 | ACTIVE → IDLE → ACTIVE | 🔴 | depends on F60 |
| F63 | Agent Draining & Termination | 🔴 | depends on F60 |
| F64 | Sub-Agent Clarification via DeltaBus | 🔴 | depends on F60 |

## Section 7 — SessionState (F65–F77)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F65 | Concierge Pending Clarifications Single-Writer | ✅ | E5.5.3 `_write_lock RLock` |
| F66 | Concierge → Single Writer → SS | ✅ | E5.5 + E5.7 |
| F67 | Multi-Reader Access | 🟡 | **I6.11.C6** systemic: only Fabric+MW live readers; Orch=Mock (H5), Planner=None |
| F68 | Agent Deltas → DeltaBus | 🔴 | depends on F60 |
| F69 | DeltaBus → Aggregation Window → Concierge | 🟡 | E5.8.5 aggregator dedup OK; producer side BLOCKED |
| F70 | HOT → WARM Eviction | ✅ | E5.5.5 documented order |
| F71 | WARM → COLD Archive | ✅ | LocalColdArchive (E5.6.3) |
| F72 | COLD → HOT Reconstruction | 🟡 | E5.11.6 SLA < 50 ms P95 unverified (no test) |
| F73 | Emergency Summarization ≥ 95 KB | ⚫ | not in tracing plan |
| F74 | Emergency Read-Only Mode | ✅ | E5.5.2 SS-06 |
| F75 | Emergency Priority Shedding | ⚫ | not in tracing plan |
| F76 | Write Request → Mutation Guard | 🟡 | E5.5.4 **GAP-SS-03** latent deadlock (`MutationGuard._lock` is `Lock` not `RLock`) |
| F77 | Eviction Engine Trigger | ✅ | E5.5.5 |

## Section 8 — Memory Writer / K0 (F78–F87)

> Bridge is active (MS-2.5 + MS-3a). Recipe-C runs K1→Bridge→pseudo-K0
> end-to-end. **MW01 (topic typo) remains the dominant production-impact
> bug** on the MW side. M6 Retention is still stub.

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F78 | Memory Writer Agents → K0 | 🟡 | **ISSUE-MW01** default dispatcher hears nothing; MW04 zero geohash; MW06 newest-wins corrections dropped |
| F79 | Delta Aggregator → K0 Command | 🟢 | **Recipe-C:** aggregator emits → Bridge LIVE → pseudo-K0 WAL (M7 E7.2) |
| F80 | K0 P02 Episodic Write | 🟢 | **Recipe-C:** persists to pseudo-K0 `wal` table; real K0 P02 future |
| F81 | K0 P03 Consolidation | ⚫ | pseudo-K0 does not emulate P03 consolidation |
| F82 | K0 SSE → K1 EventBus | 🟢 | **Recipe-C:** `tool_state.changed.v1` SSE wired end-to-end (M7 E7.4); other SSE channels pending MS-3c |
| F83 | SSE Trigger → Proactive Decision | ⚫ | M6 Proactive stub (no consumer) |
| F84 | Session Checkpoint | ✅ | E5.11.2 StandaloneLifecycle 30 s checkpoint |
| F85 | Retention Expiry → Automated Deletion | ⚫ | M6 Retention is stub package |
| F86 | User Deletion → Soft Delete | ⚫ | M6 Retention stub |
| F87 | Grace Period Recovery | ⚫ | M6 Retention stub |

## Section 9 — Proactive / Learning (F88–F94)

> Whole namespace M6 stub. Tracing-plan master index labels M6 cluster
> "stubs, mostly empty". The K0 SSE side now works (Recipe-C), but no K1
> consumer for proactive/learning channels exists yet.

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F88 | SSE Event → Proactive Decision | ⚫ | M6 stub consumer missing |
| F89 | Proactive Budget Gate Check | ⚫ | M6 stub |
| F90 | Proactive Agent Spawn via Fabric | 🔴 | F60 (I3.4.5 AgentProvider mailbox=None) |
| F91 | Feedback Signal Collection | ⚫ | M6 Learning stub; bridge contract `feedback.envelope.v1` exists but no K1 emitter |
| F92 | Drift Detection | ⚫ | M6 Learning stub |
| F93 | Advisory Emission → K0 P06 | ⚫ | bridge contract `k0.learning.advisory.v1` exists; no K1 emitter; pseudo-K0 has no P06 |
| F94 | K0 SSE → Proactive Agent Spawner | 🔴 | F90 (AgentProvider mailbox=None) |

## Section 10 — Fabric Routing / Policy / MCP (F95–F103)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F95 | Capability Resolver Selection | ✅ | E3.1.5 + E3.1.10 lookup rules |
| F96 | Provider Matcher → DAG | ✅ | E3.1.4 BatchStrategy.DAG |
| F97 | Affective Routing (Emotion-Aware) | � | LLM provides emotion (⚪ F15); downstream `AffectiveRouter` consumer wiring not in tracing plan |
| F98 | Cognitive Load Routing | 🟡 | LLM provides complexity (⚪ F22); router consumer wiring not in tracing plan |
| F99 | QoS Integration (Token Budget) | ✅ | E3.9.2/.3/.4 budget gates |
| F100 | Security Context (Band-Based Access) | 🟡 | E3.1.6 OK; **E3.11.3** default GREEN if `safety_band` missing |
| F101 | Local MCP Server Discovery | 🟡 | factory wires `TestMCPTransport`; real discovery not bundled |
| F102 | Remote MCP Server → K0 Proxy | 🟢 | **Recipe-C:** `connector.execute.*` routes via Bridge LIVE → pseudo-K0 `ConnectorHost` (M7 E7.5) |
| F103 | MCP Capability Registration | ✅ | E3.3.5 hot-reload poll |

## Section 11 — LLM / Model Hub (F104–F111)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F104 | Model Router Load Balancing | ✅ | E3.7 9-step router |
| F105 | Model Cache Hit/Miss | 🟡 | E3.7.2/.3 OK; **ISSUE-M04** `repr(payload)` cache-key shape unconfirmed |
| F106 | LLM Provider Routing | ✅ | E3.8 (test-mode `StubProviderPlugin`) |
| F107 | Concierge LLM Inference | 🟡 | **E3.11.6** `ModelHubPOCBridge` bypasses pipeline — zero budget/cache/CB |
| F108 | Planner LLM Inference | 🟡 | **GAP-P02** private→public `build_payload` import |
| F109 | Memory Writer LLM Inference | ✅ | E5.8 pipeline; budget=2000 BACKGROUND |
| F110 | Solution Validator LLM | 🟡 | I4.10.4 arbiter unavailable → auto-approve (silent fallback) |
| F111 | Proactive Decision LLM | ⚫ | M6 stub |

## Section 12 — Emotional / Narrative / Anticipation (F112–F119)

> Higher-cognition layer. The vision doc imagined dedicated engines
> (NarrativeEngine, AnticipationEngine, PersonaHints, etc.); the tracing plan
> does not list any of them. Treat the entire band as ⚫ except F114, which
> has a partial DynamicIdentityContext implementation (I1.6.3).

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F112 | Emotional Trajectory Analysis | � | LLM emotion signal available (⚪ F15); trajectory analyzer not in tracing plan |
| F113 | Emotional Mirroring → Style Adjustment | 🟡 | LLM emotion signal available; mirror consumer not in tracing plan |
| F114 | Persona Hints Update | 🟡 | I1.6.3 DynamicIdentityContext role priority (FSM-driven only) |
| F115 | Narrative Thread Analysis | ⚫ | engine absent |
| F116 | Thread → Narrative Engine | ⚫ | engine absent |
| F117 | Narrative Arc Update | ⚫ | engine absent |
| F118 | User Needs Prediction | ⚫ | engine absent |
| F119 | Context Prefetch | ⚫ | engine absent |

## Section 13 — Conversational Rhythm / ToM / Prediction (F120–F127)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F120 | Rhythm Patterns → Conversation Beat | ⚫ | engine absent |
| F121 | Dynamic Timing Adjustment | 🟡 | E1.9 WeavePolicy timing decides 500 ms BATCH fallback only |
| F122 | Pacing → Concierge FSM | 🟡 | inherits F121 |
| F123 | ToM Engine → Mental Model Update | ⚫ | engine absent |
| F124 | Mental Model → Cognitive Load | ⚫ | engine absent |
| F125 | Capacity Estimate → Concierge | ⚫ | engine absent |
| F126 | Predictions → Anticipation Engine | ⚫ | engine absent |
| F127 | Anticipation → Speculative Execution | ⚫ | engine absent |

## Section 14 — Module Discovery & Registration (F128–F131)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F128 | Module Scanner Discovery | ✅ | E3.3.5 hot-reload 2 s poll |
| F129 | Tool Registry Registration | ✅ | E3.1.8 / E3.1.9 (`DuplicateCapabilityError`, `VERSION_UPGRADED`) |
| F130 | Prompt Registry Registration | ✅ | E3.1.7 `find_relevant_prompts` |
| F131 | Agent Registry → Factory | 🔴 | depends on F60 |

## Section 15 — Bus Routing / WFQ (F132–F137)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F132 | Capability Invoked Event | ✅ | E3.1.1 |
| F133 | Capability Completed Event | ✅ | E3.1.1 |
| F134 | Affect Analyzed Event | � | LLM emits affect (⚪ F15); event publisher wiring needs verification |
| F135 | Constraint Progress Event | ⚫ | depends on F47 |
| F136 | Priority-Based Event Bus Delivery | ✅ | E5.4.2 STRICT/RELAXED + E5.2.1 monotonic sequence |
| F137 | Priority-Based Mailbox Router | ✅ | E2.2 S1 `create_mailbox_router()` + E4.1.3 FIFO within band |

## Section 16 — User Loops (F138–F141)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F138 | Concierge ↔ User Bidirectional | ✅ | E1.1 + E1.3 |
| F139 | Planner ↔ User Bidirectional | 🟡 | E4.8 HIL clarify; direct user→planner uncommon |
| F140 | Sub-Agents ↔ User Bidirectional | 🔴 | depends on F60 |
| F141 | Orchestrator ↔ User Bidirectional | 🟡 | E4.6 wave HIL — GAP-O06 over-interrupt |

## Section 17 — Tracing / Metrics / Health (F142–F144)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F142 | Distributed Tracing → Cognitive Trace ID | ✅ | E5.10.2 (`cognitive_trace_id` propagated across envelopes + into K0 atoms) |
| F143 | Metrics Aggregator → SessionState | ⚫ | aggregator absent in tracing plan |
| F144 | Health Check Orchestrator | 🟡 | E2.1.5 GAP aggregation undefined; **ISSUE-M01** ModelHub `health_port` unwired |

## Section 18 — Prompts / Output Validation (F145–F154)

| # | Flow | Status | Tracing-plan basis |
|---|---|---|---|
| F145 | Prompt Resolution → Template Lookup | ✅ | E1.6 PromptMode + E3.1.7 |
| F146 | Prompt Variable Injection | ✅ | E1.6 builder |
| F147 | Prompt Compilation → Model Gateway | ✅ | E3.8 adapter normalization |
| F148 | Dynamic Agent Prompt Registration | 🔴 | depends on F60 |
| F149 | LLM Output → 3-Tier Validation Pipeline | ✅ | E3.2.8/.9/.10 |
| F150 | Schema Registry → Agent Schema Lookup | 🟡 | E3.4 contracts OK; dynamic schema for agents BLOCKED |
| F151 | Hallucination Detection → SS Cross-Reference | ⚫ | E3.2.10 Tier-3 ANNOTATEs only; no cross-reference verifier |
| F152 | Validation Fallback → Retry/Repair/Reject | ✅ | E3.2.8 REJECT + E3.2.9 coerce + tier-3 annotate |
| F153 | Dynamic Agent Schema Registration | 🔴 | depends on F60 |
| F154 | Core vs Generic Payload Schema Selection | 🟡 | E3.11.5 PlanStep type collision warning |

---

## Quick lookup — what blocks the most flows?

> **2026-05-13 update.** Two former top blockers are gone: ~~OPEN §5 (Bridge
> offline)~~ resolved by MS-2.5/MS-3a + pseudo-K0 Recipe-C; ~~I1.7.1 (UltraBERT
> Stub)~~ resolved by removing UltraBERT in favor of LLM-via-ModelHub.

| Single GAP / blocker | Flows it kills |
|---|---|
| **I3.4.5 — AgentProvider `mailbox=None`** | F60, F61, F62, F63, F64, F68, F90, F94, F131, F140, F148, F153 — **12 flows** |
| **M6 stub cluster** (Retention/Learning/Anticipation/Narrative/ToM engines absent) | F73, F75, F81, F83, F85–F87, F89, F91–F93, F111, F115–F120, F123–F127 — **~22 flows; entire higher-cognition + retention bands** |
| **I1.5.1 / Finding N6 — HIGH path not wired** | F06, F09 (HIGH leg) — **2 flows, but the entire T3 milestone** |
| **I6.11.C6 + I6.11.H5 — Mock/Null SS readers in prod** | F67 + degrades F07 — **2 flows + safety implications** |
| **I6.11.C5 — `IEmbeddingPort` not wired** | F41 — **1 flow** |
| **ISSUE-MW01 — Topic typo `complete` vs `completed`** | F78 default path silent — **1 flow, but biggest production-impact bug** |
| **GAP-O06 — wave HIL over-interrupt** | F58, F59, F141 — **3 flows** |
| **GAP-O02 — ConcurrencyGuard mailbox flood** | hits F45 + any HIGH-tier replay — **resource blast radius** |
| **GAP-P02 — Planner `build_payload` private import** | F108 + crashes whole planner LLM path on first call |

**Pseudo-K0 caveats** (not blockers, but Recipe-C limitations to flag):

- Pseudo-K0 launch is manual (`python -m scripts.pseudo_k0 ...`) — **I7.1.4**.
- Recall is LIKE-only (no FTS/vector) — F39/F40 succeed but with degraded relevance.
- No policy/gate/signature verification — K1 flows that depend on K0 enforcement will silently pass on pseudo-K0 (must be marked `xfail-on-real-K0`).
- `belief`/`graph`/`device`/`session` recall selectors return empty — not a Recipe-C failure, but a Recipe-D (real K0) consideration.

## Recommendations for the live-wiring SOP

1. **Two-recipe split.** Treat hermetic Recipe-A (no bridge, no K0) and Recipe-C (Bridge LIVE + pseudo-K0) as separate suites:
   - **Recipe-A** addresses the 48 ✅ AVAILABLE + 33 🟡 PARTIAL = 81 flows in-process.
   - **Recipe-C** additionally unlocks the 9 🟢 PSEUDO-K0-AVAILABLE flows (F35, F39, F40, F79, F80, F82, F102, plus envelope/SSE/connector contract tests).
2. **Pseudo-K0 launch fixture (priority).** Add a pytest fixture / docker-compose target that boots `python -m scripts.pseudo_k0 --port 8090 --db :memory:` for the duration of Recipe-C tests. Until this lands, Recipe-C is gated on manual launch (I7.1.4).
3. **Mark LLM-COVERED flows non-test.** F11–F23 should NOT appear in live test inventory. Instead, add **one** integration test per acking pipeline that asserts the LLM-Phase-1 call shape (input contract, output contract, latency budget). This collapses 13 vision flows into 1 contract test.
4. **Collapse Agent path into a single negative-wire probe** (`mailbox is None` → spawn → expect typed error). This covers F60–F64, F68, F90, F94, F131, F140, F148, F153 (12 flows → 1 assertion that flips green when AgentProvider is wired).
5. **Skip M6 stubs (~22 flows)** from live tests entirely — no engine to test. Track as a single "M6 not implemented" issue.
6. **Cross-reference each F-number with the live-procedure step IDs** from [live_kernel_wiring_test_procedure.md](live_kernel_wiring_test_procedure.md):
   - **M1-L3** (LOW flow) verifies **F04 + F08 + F138 + F142 + F145–F147 + F149/F152**.
   - **M1-L4** (MED flow) verifies **F05 + F09 (MED) + F33 + F36–F38 + F132–F133 + F136–F137**.
   - **M1-L5** (HIGH flow) is the gated test confirming **F06 + F09 (HIGH)** remain BLOCKED.
   - **M5-L1** (topic match) verifies **F78**.
   - **M3-L5** (ModelHub 10 topics) verifies **F104 + F105**.
   - **M4-L2** (DAG) verifies **F45 + F95 + F96**.
   - **M7-L1** (Recipe-C memory.write round-trip) verifies **F35 + F79 + F80**.
   - **M7-L2** (Recipe-C recall) verifies **F39 + F40**.
   - **M7-L3** (Recipe-C SSE) verifies **F82**.
   - **M7-L4** (Recipe-C connector dispatch) verifies **F102**.
7. **⚪ LLM-COVERED flows: contract test, not flow test.** Phase-1 LLM call must (a) hit `ModelHubPOCBridge`, (b) respect `KernelConfig` budget/timeout, (c) fall through to `StubPhase1Pipeline` on timeout. One test per acking handler.

---

## Appendix — Cross-cutting flow gaps not numbered in K1_FLOWS.md

These are missing from the vision doc entirely; the tracing plan and the
bridge / pseudo-K0 work introduce them and they need live coverage even
though they have no F-number:

- **Bridge envelope signing round-trip** (E2.7.9): HMAC + Ed25519; canonical JSON; idem-key excluded from hash. Cover under M7-L1.
- **LocalOutbox durability under 5xx** (E2.7.4 + E7.2.4): kill pseudo-K0, submit, observe `LocalOutbox` queue, restart pseudo-K0, observe `DrainWorker` drain + Prometheus counter. Cover under M7-L5.
- **Bridge mode selection at S4** (E2.10 / new): start KernelService with `K0_ENDPOINT` set vs unset vs `bridge_enabled=False`; assert correct client class (`HttpBridgeClient` / `SinkBridgeClient` / null) and adapter (`LiveBridgeAdapter` / `SinkBridgeAdapter` / `OfflineBridgeAdapter`). Cover under M2-L0.
- **MW pipeline → K0 outbox** (separate from F78 because vision assumed K0 online): under SINK mode, exercise the `LocalOutbox` enqueue path. Under LIVE + pseudo-K0, exercise WAL persistence.
- **Per-session bus isolation**: vision assumes one bus; live kernel has per-session buses (E2.2 P1). Cover under M5-L5.
- **S6b Mock→real planner swap window** (E2.3): vision doesn't model the composition root races. Cover under M2-L2.
- **Lifecycle teardown order** (E2.4.7, E5.11.4): vision doc has no shutdown section. Cover under M2-L1 and M5-L3.
- **Bridge-aware bus topic guard** (E2.7.5 / `BridgeAwareLocalBus`): attempt to publish a bridge-reserved topic directly; assert R10 mitigation kicks in. Cover under M2-L4.
- **Pseudo-K0 gap matrix** (E7.6): tests must flag flows that succeed on pseudo-K0 but will need policy/gate/idem on real K0 (mark with `xfail-on-real-K0`).

These eight are the "implicit flows" the live SOP catches that the vision
doc missed.
