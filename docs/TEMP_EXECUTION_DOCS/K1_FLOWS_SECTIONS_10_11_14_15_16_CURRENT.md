# K1 Flows §10/§11/§14/§15/§16 — Audit Bundle

**Source-of-truth design doc:** [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md)
**Inventory:** [K1_FLOWS_ENUMERATED.md](K1_FLOWS_ENUMERATED.md)
**Companions:** [§1](K1_FLOWS_SECTION1_CURRENT.md) · [§2](K1_FLOWS_SECTION2_CURRENT.md) · [§3](K1_FLOWS_SECTION3_CURRENT.md) · [§4](K1_FLOWS_SECTION4_CURRENT.md) · [§5](K1_FLOWS_SECTION5_CURRENT.md) · [§6](K1_FLOWS_SECTION6_CURRENT.md) · [§7](K1_FLOWS_SECTION7_CURRENT.md) · [§8](K1_FLOWS_SECTION8_CURRENT.md)
**Verification basis:** 5 parallel Explore subagents with mandatory kernel-side wiring inspection
**Date:** 2026-04-28

Legend: ✅ wired · ⚠️ partial · ❌ missing · 🔵 stub-only / aspirational · 🟣 K0-undeployed-blocked

---

## Combined Status Summary

| § | Section | Flows | ✅ | ⚠️ | ❌ | 🔵 |
|---|---|---|---|---|---|---|
| §10 | Fabric (F95–F103) | 9 | 3 | 3 | 3 | — |
| §11 | Model Gateway (F104–F111) | 8 | 4 | 3 | 1 | — |
| §14 | Module Loader (F128–F131) | 4 | 0 | 3 | 1 | — |
| §15 | Event Bus (F132–F137) | 6 | 0 | 4 | 2 | — |
| §16 | HIL (F138–F141) | 4 | 1 | 3 | 0 | — |
| **Total** | — | **31** | **8** | **16** | **7** | **0** |

**26% wired · 52% partial · 22% missing**

**Headline:** §11 Model Gateway is the strongest section in the entire audit so far — all 5 LLM provider plugins (OpenAI/Anthropic/Google/Ollama/vLLM) are real, both streaming + cost tracking work end-to-end, and the kernel loud-fails on unknown `model_mode` (test-stub guard intact). §14 Module Loader has zero ✅ — the doc-described `MODULE_SCANNER` / `TOOL_REGISTRY` / `PROMPT_REGISTRY` / `AGENT_REGISTRY` separation was collapsed into a single `CapabilityRegistry` (P3.1). §15 Event Bus has zero ✅ — F134/F135 publishers don't exist; F132/F133 publish but have no live subscribers wired. §16 HIL is **fragmented across 4 subsystems with no unified port** (`k1/kernel/ports/hil_port.py` does not exist) — two `HILCoordinator` classes (Concierge + Planner) share no code.

---

## §10 Fabric (F95–F103)

| F# | Name | Status | Key gap |
|---|---|---|---|
| F95 | Capability Resolver Selection | ✅ wired | `Resolver` (5-step pipeline) richer than docs (3 steps); PolicyEngine fully composed |
| F96 | Provider Matcher → DAG | ⚠️ partial | `ProviderMatcher` wired; DAG compilation lives in **Orchestrator**, not Fabric — doc conflates two subsystems |
| F97 | Affective Routing | ✅ wired | `AffectiveRouting(state_reader=...)` wired; **single-session reader picks first active session** ([service.py#L126](../../k1/kernel/service.py#L126)) — multi-session uses wrong state |
| F98 | Cognitive Load Routing | ✅ wired | Same multi-session single-reader issue |
| F99 | QoS Integration | ⚠️ partial | `QoSIntegration()` constructed with **no `state_reader`** ([factory.py#L621](../../k1/fabric/factory.py#L621)) — doc says reads `CONTEXT_BUDGET` from SS, code can't |
| F100 | Security Context (Band) | ⚠️ partial | `SecurityContext()` no state_reader; band check operates on request param only; **`BAND_CRISIS → SAFETY_MAILBOX` not implemented** |
| F101 | Local MCP Server Discovery | ❌ missing | No path/mDNS/process scan; no `StdioTransport`; no `SSETransport`; `mcp_transport=None` in production ([service.py#L1003](../../k1/kernel/service.py#L1003)) |
| F102 | Remote MCP → K0 Proxy | ❌ missing | No `K0_CONNECTOR_PROXY`; no OAuth/API-key handling; `BridgeConnectionAdapter` is K0 bridge not MCP proxy |
| F103 | MCP Capability Registration | ❌ missing | No `MCPCapabilityRegistrar`; no MCP JSON Schema ingestion; no per-server health checks; hot-reload exists but **`watch=False`** in prod ([factory.py#L764](../../k1/fabric/factory.py#L764)) |

### §10 Notable findings

- **Telemetry fully wired** — `EventEmitter` emits `TOPIC_CAPABILITY_INVOKED`, `TOPIC_CAPABILITY_COMPLETED`, `TOPIC_LEARNING_SIGNAL` via `IEventPort` → `EventPortProdAdapter` → DeltaBus
- **Capability registration is YAML-driven, not decorator-based** — `ModuleLoader` scans `k1/contracts/`, `CapabilityRegistry.register()` stores
- **MCP transport gap is the single critical blocker** for F101–F103 — one missing injection: `create_shared()` never receives `mcp_transport`
- **Hot-reload daemon exists but disabled** — `EVENT_CONTRACT_HOT_RELOADED` event defined but never fires in production

### §10 Top recommended actions

| Pri | Action | Touches | Anchor |
|---|---|---|---|
| P0 | Implement `IMCPTransport` production impls (`StdioTransport`, `SSETransport`, `HttpTransport`) and inject at S3 | F34 (§3), F101 | [service.py#L1003](../../k1/kernel/service.py#L1003) |
| P1 | Inject `state_reader` into `QoSIntegration()` so context-budget routing matches doc | F99 | [factory.py#L621](../../k1/fabric/factory.py#L621) |
| P1 | Inject `state_reader` into `SecurityContext()` for live band checks | F100 | [factory.py#L617](../../k1/fabric/factory.py#L617) |
| P1 | Fix multi-session affective/cognitive single-reader (currently picks first active session) | F97, F98 | [service.py#L126](../../k1/kernel/service.py#L126) |
| P2 | Implement `BAND_CRISIS → SAFETY_MAILBOX` routing or remove from doc | F100 | [security_context.py](../../k1/fabric/policy/security_context.py) |
| P2 | Build `MCPCapabilityRegistrar` (JSON Schema → `CapabilityContract` translation) | F103 | new |
| P2 | Build local MCP discovery (path scan / mDNS / process inspect) | F101 | new |
| P2 | Build K0 proxy for remote MCP (OAuth + API-key vault) | F102 | new |
| P3 | Enable `watch=True` in production OR delete hot-reload code | F128 (§14), F103 | [factory.py#L764](../../k1/fabric/factory.py#L764) |
| P3 | Update K1_FLOWS.md §10: clarify F96 DAG compilation is Orchestrator concern, not Fabric | doc | — |

---

## §11 Model Gateway (F104–F111)

| F# | Name | Status | Key gap |
|---|---|---|---|
| F104 | Model Router Load Balancing | ⚠️ partial | Doc says "Weighted Round Robin"; code does **5-dimension weighted scoring per request** (cost/latency/preference/placement/health); `_DefaultHealthQuery` returns HEALTHY for all (no live probe) |
| F105 | Model Cache Hit/Miss | ⚠️ partial | Doc says 24h temp=0 / 1h temp>0 TTL; code has **flat 5min default LRU**; streaming requests never cached; explicit `_SKIP_CAPABILITIES` for `TOOL_CALL`/`BATCH`/`MODERATE` |
| F106 | LLM Provider Routing | ✅ wired | All 5 plugins real (OpenAI, Anthropic, Google, Ollama, vLLM) with `execute` + `stream_execute`; `StubProviderPlugin` guarded behind `model_mode="test"`; `ValueError` on unknown mode |
| F107 | Concierge LLM Inference | ✅ wired | `ILLMPort = IModelHubPort` ([ports.py#L49](../../k1/concierge/ports.py#L49)); `ModelGatewayAdapter` (CB_MODEL) wraps with retry → CB half-open 30s → canned response |
| F108 | Planner LLM Inference | ✅ wired | `LLMGatewayAdapter` V2 wired unconditionally at [service.py#L1067](../../k1/kernel/service.py#L1067); `consumer_id="planner"` for cost attribution; **no silent TestLLMAdapter fallback at kernel level** |
| F109 | Memory Writer LLM Inference | ✅ wired | Anti-corruption `ModelHubAdapter` bridges MW's `chat()` ↔ K1's `execute(HubRequest)` at [service.py#L1306](../../k1/kernel/service.py#L1306) |
| F110 | Solution Validator LLM | ⚠️ partial | LLM arbiter is **inside Planner `ValidateService` STAGE3** (phase 1 deterministic, phase 2 LLM with `STRUCTURED` capability, temp 0.1); standalone `SOLUTION_VALIDATOR` was **removed (ORCH-02)** |
| F111 | Proactive Decision LLM | ❌ missing / 🔵 stub | `ProactiveAgent` is 50ms-budget stub returning `FillMessage()` ([proactive_agent.py#L67](../../k1/concierge/experience/proactive_agent.py#L67)); `ProactiveDecisionService` is design-doc only |

### §11 Notable findings

- **Production providers all real** — five plugin files implement both `execute` and `stream_execute` with SSE streaming
- **Cost/budget tracking real** — manifest-driven `CostTracker`, `BudgetEnforcer` ($5/day, 3-tier ALLOW/ALLOW_DEGRADED/REJECT), `AuditLogger`
- **Test-mode safety intact** — kernel loud-fails on unknown `model_mode`; stub plugin path emits `logger.warning` and is gated
- **Doc fidelity drift on F104/F105** — algorithm names (round-robin) and TTL tiers (24h/1h) are stale; code is more sophisticated
- **§5 P1 concern resolved** — V1 historical "TestLLMAdapter in all environments" no longer applies; kernel wires V2 unconditionally
- **F111 confirms §8 F83 finding** — entire proactive subsystem is design intent only

### §11 Top recommended actions

| Pri | Action | Touches | Anchor |
|---|---|---|---|
| P1 | Replace `_DefaultHealthQuery` (always HEALTHY) with live latency/error-rate probe feeding `_HEALTH_SCORES` | F104 | [request_router.py#L87](../../k1/model_hub/services/request_router.py#L87) |
| P1 | Reconcile cache TTL: doc 24h/1h vs code 5min flat — pick one and update both | F105 | [response_cache.py](../../k1/model_hub/services/response_cache.py) |
| P2 | Decide F111 proactive: build real `ProactiveDecisionService` OR keep stub + amend doc | F111 (§8 F83) | [proactive_agent.py#L67](../../k1/concierge/experience/proactive_agent.py#L67) |
| P3 | Update K1_FLOWS.md §11: F104 algorithm naming, F105 TTL, F110 (Solution Validator removed → Planner STAGE3 LLM arbiter) | doc | — |

---

## §14 Module Loader (F128–F131)

**Architectural note:** docs describe `k1/kernel/loader.py` + separate `TOOL_REGISTRY`/`PROMPT_REGISTRY`/`AGENT_REGISTRY`. **None of those files exist** — collapsed into single `CapabilityRegistry` (P3.1) and `ModuleLoader` lives in `k1/fabric/core/module_loader.py`, wired by `FabricFactory` not kernel.

| F# | Name | Status | Key gap |
|---|---|---|---|
| F128 | Module Scanner Discovery | ⚠️ partial | Wrong file location in docs; **`module.yaml` files are NOT consumed** — loader scans contract YAMLs directly under `tools/`/`agents/`/`prompts/`/`workflows/`; no `entry_points` discovery; `finance/` module referenced in docs **does not exist** |
| F129 | Tool Registry Registration | ⚠️ partial | No `TOOL_REGISTRY` class; tools stored as `ContractUnion` in single `CapabilityRegistry`; YAML structure differs from doc's multi-tool manifest |
| F130 | Prompt Registry Registration | ❌ missing | Loader only handles `.yaml`/`.yml` extensions; `.md` prompt files never load; **no `PromptRegistry` class anywhere**; prompts/ subdir enumerated but unreachable |
| F131 | Agent Registry → Factory | ⚠️ partial | No separate `AGENT_REGISTRY`; spawn path `AgentFactory` → `CapabilityRegistry.get_agent_contract()` works ([agent_provider.py#L1378](../../k1/fabric/providers/agent_provider.py#L1378)); `finance_agent` referenced doesn't exist; lifecycle FSM state names not verified |

### §14 Notable findings

- **Hot-reload exists but `watch=False` in production** ([factory.py#L760](../../k1/fabric/factory.py#L760)) — `EVENT_CONTRACT_HOT_RELOADED` defined, never fires
- **No `entry_points` plugin discovery** — `pyproject.toml` has no `[project.entry-points]` for modules
- **No security gate on module load** — any YAML in scanned dir is registered
- **Two real modules on disk:** `k1/modules/health/`, `k1/modules/stress_table/` — `finance/` is fictional
- **`module.yaml` files exist but are dead** — present in `health/` and `stress_table/` but the loader scans contract YAMLs directly, ignoring `module.yaml`

### §14 Top recommended actions

| Pri | Action | Touches | Anchor |
|---|---|---|---|
| P1 | Decide P3.1 stance: either build `PromptRegistry` for `.md` prompt loading OR drop `prompts/` from `_CONTRACT_SUBDIRS` and amend doc | F130 | [module_loader.py#L73](../../k1/fabric/core/module_loader.py#L73) |
| P2 | Either parse `module.yaml` (currently dead files) OR delete them | F128 | [module_loader.py](../../k1/fabric/core/module_loader.py) |
| P2 | Decide hot-reload: enable `watch=True` in prod OR delete watch code | F128, F103 (§10) | [factory.py#L760](../../k1/fabric/factory.py#L760) |
| P2 | Add module-load security gate (signed YAMLs / allowlist) | F128 | new |
| P3 | Update K1_FLOWS.md §14: collapse `TOOL_REGISTRY`/`PROMPT_REGISTRY`/`AGENT_REGISTRY` → `CapabilityRegistry`; remove `finance/` references; correct file location to `k1/fabric/core/module_loader.py` | doc | — |

---

## §15 Event Bus (F132–F137)

| F# | Name | Status | Key gap |
|---|---|---|---|
| F132 | Capability Invoked Event | ⚠️ partial | Publish ✅ via `EventEmitter.emit_invoked()` ([fabric.py#L419](../../k1/fabric/fabric.py#L419)); **zero live subscribers** for `k1.capability.invoked.v1` — `FABRIC_MAILBOX`/`CONCIERGE_MAILBOX`/`DISTRIBUTED_TRACING` subscribers don't exist |
| F133 | Capability Completed Event | ⚠️ partial | Publish ✅; Orchestrator subscribes via `EventSubscriptionAdapter` ([service.py#L1042](../../k1/kernel/service.py#L1042)) → `StepRunner`; **`TOOL_RESULT_BUFFER` subscriber missing**; Concierge path is FSM dispatch not direct subscribe |
| F134 | Affect Analyzed Event | ❌ missing | Doc topic `k1.affect.analyzed.v1` **does not exist**; actual is `k1.affect.update.v1` (different name); UltraBERT publishes **nothing** to bus — affect flows synchronously through pipeline return value; `AFFECTIVE_ROUTING`/`EMOTIONAL_MIRRORING` subscribers absent |
| F135 | Constraint Progress Event | ❌ missing | Topic `k1.constraint.progress.v1` **not found anywhere**; `CONSTRAINT_MANAGER` component absent; `k1.constraint.*` exists only as RELAXED-mode prefix in [defaults.py#L62](../../k1/bus/timing/defaults.py#L62) |
| F136 | Priority-Based Bus Delivery (WFQ) | ⚠️ partial | `Priority` enum exists; **V1 is single-threaded sync dispatch with strict-priority ordering**, NOT weighted round-robin; true WFQ is V2 future ([local_mailbox.py#L41](../../k1/bus/impl/local_mailbox.py#L41)); no named `WFQ_SCHEDULER` component |
| F137 | Priority-Based Mailbox Router | ⚠️ partial | `LocalMailboxRouter` real with priority sub-queues ✅; **doc's "URGENT evicts oldest BACKGROUND" backpressure NOT implemented** — `BackpressureError` raised instead; per-actor queue depths (100/50/20/200) are doc-only, config drives uniform value |

### §15 Notable findings

- **Two backend bus impls exist:** `LocalBus` (Python) and `RustBusAdapter` (`k1_bus_core.RustBus`); `BusFactory._resolve_backend()` uses `K1_BUS_BACKEND` env var → param → `"auto"` (Rust if compiled)
- **Persistence/replay (`BusOutbox` SQLite WAL P6.13) exists but NOT wired** at kernel S1 boot — none of F132–F137 topics have durable delivery
- **No bus-level dead-letter queue** wired by default; `BusStats.async_handler_dlq` counter exists; Concierge FSM has its own `_publish_dead_letter` for FSM-level DLQ only
- **`mailbox_full_drops` stats exist** but no automatic retry/escalation
- **F134 affect topic naming drift:** doc `analyzed.v1` vs code `update.v1` — single subscriber (Concierge FSM) consumes the actual topic
- **F135 is pure design intent** — entire `CONSTRAINT_MANAGER` + topic + subscriber chain absent

### §15 Top recommended actions

| Pri | Action | Touches | Anchor |
|---|---|---|---|
| P1 | Wire `bus.subscribe("k1.capability.invoked.v1", ...)` — currently published into the void | F132 | [event_emitter.py#L152](../../k1/fabric/events/event_emitter.py#L152) |
| P1 | Wire `BusOutbox` (SQLite WAL) at kernel S1 for durable F132/F133 delivery | F132, F133 | [sqlite_outbox.py](../../k1/bus/outbox/sqlite_outbox.py) |
| P1 | Implement `TOOL_RESULT_BUFFER` subscriber for `k1.capability.completed.v1` OR amend doc | F133 | new |
| P2 | Decide F134 affect publish: have UltraBERT publish to bus OR delete `AFFECTIVE_ROUTING`/`EMOTIONAL_MIRRORING` subscribers from doc | F134 | [concierge/session.py#L345](../../k1/concierge/session.py#L345) |
| P2 | Decide F135 constraint progress: build `CONSTRAINT_MANAGER` + publisher + subscribers OR drop from doc | F135 | new |
| P2 | Implement "URGENT evicts oldest BACKGROUND" backpressure OR change doc to "raises `BackpressureError`" | F137 | [local_mailbox.py](../../k1/bus/impl/local_mailbox.py) |
| P3 | Decide V2 WFQ: implement weighted round-robin OR mark V1 strict-priority as final design | F136 | [local_mailbox.py#L41](../../k1/bus/impl/local_mailbox.py#L41) |
| P3 | Wire bus-level DLQ topic for dropped envelopes | F136, F137 | new |
| P3 | Update K1_FLOWS.md §15: rename `analyzed.v1` → `update.v1` (F134); document V1-vs-V2 WFQ; correct backpressure semantics | doc | — |

---

## §16 HIL (F138–F141) — Cross-Subsystem

**Architectural finding:** F138–F141 are **NOT pure HIL/HITL flows**. They are documented as "bidirectional feedback" loops per subsystem. **HIL is fragmented across 4 subsystems with no unified contract.** No `IHILPort` in `k1/kernel/ports/` (verified: only bridge/bus/fabric/lifecycle/model_hub/orchestrator/planner/session_manager ports exist). Two `HILCoordinator` classes (Concierge + Planner) share zero code.

| F# | Name | Status | Key gap |
|---|---|---|---|
| F138 | Concierge ↔ User | ⚠️ partial | `HILCoordinator.handle_needs_human()` / `handle_user_response()` real ([hitl_coordinator.py#L188](../../k1/concierge/protocols/hitl_coordinator.py#L188)); FSM state `CLARIFYING_WORKER` triggered on `task.suspended`; **doc events `k1.hil.correction.received.v1`/`k1.hil.preference.captured.v1` don't exist**; CORRECTION/FEEDBACK paths have no code anchors |
| F139 | Planner ↔ User | ✅ wired (best of 4) | `HILCoordinator` real ([hil_coordinator.py#L70](../../k1/planner/services/hil_coordinator.py#L70)); `TOPIC_HIL_CLARIFICATION`/`APPROVAL_REQ`/`RESP` real; PLAN-10 max 2 rounds; PLAN-12 micro-replan never HIL; **timeouts 60s/120s, NOT 5min as doc says** |
| F140 | Sub-Agents ↔ User | ⚠️ partial / 🔵 stub | `pending_clarifications` field exists in agent builder + tool contract; `PendingHILContext` in orchestrator types; **no live wiring** for `SUB_AGENT_MAILBOX → CONCIERGE_MAILBOX` route; sub-agent → Orchestrator HIL dispatch absent |
| F141 | Orchestrator ↔ User | ⚠️ partial | `HIL_OVERRIDE_RESPONSE`/`FALLBACK_RESPONSE` events real ([events.py#L92](../../k1/orchestrator/events.py#L92)); `IDeltaEmitPort.emit_hil_request()` real; `hil_timeout_ms=120_000`/`max_pending_hil=20` configured; **doc events `k1.orchestrator.priority.updated.v1` etc. don't exist**; `PRIORITY_CONFLICT`/`RESOURCE_EXHAUSTION` types unimplemented; **Concierge-side delta_port HIL receiver is critical unverified link** |

### §16 Notable findings

- **No `IHILPort` exists in `k1/kernel/ports/`** — HIL is split across `IDeltaEmitPort.emit_hil_request()` (orchestrator) + `HILCoordinator` callbacks (concierge) + `HILCoordinator` event-bus (planner)
- **Three different `HILRequest` types** in different modules (Concierge, Orchestrator, Planner) — type confusion risk
- **Inconsistent topic naming:** Planner uses `k1.hil.clarification.v1`; Orchestrator uses `k1.hil.override_response.v1`/`fallback_response.v1`; Concierge emits `task.suspended.v1`
- **`PENDING_CLARIFICATIONS` correlation map** referenced in Planner docs and `.mmd` diagrams but **not directly verified as a live class** in Concierge
- **No escalation to human supervisor anywhere** — RED safety band blocks but does not escalate
- **Concierge HILCoordinator** has crash recovery (`recover_pending_hitl()` on startup, `SuspensionManager`); Planner HILCoordinator has `HILTimeoutError` + best-effort fallback; Orchestrator config has timeout but **no timeout handler found**
- **Sub-agent HIL is 3 disconnected anchor points** (agent_builder field, contract field, orchestrator types) with no connecting call chain — most fragmented path
- **F140 confirms §6 F64/F65 finding** — clarification routing is structurally absent
- **F141 confirms §4 F49 P3 item** — orchestrator → concierge HIL handoff via delta_port is partially wired but Concierge-side receiver path is the unverified gap

### §16 Top recommended actions

| Pri | Action | Touches | Anchor |
|---|---|---|---|
| P0 | Create unified `IHILPort` in `k1/kernel/ports/hil_port.py` with single `HILRequest` type — current 3-class fragmentation will compound bugs | F138, F139, F140, F141 | new |
| P1 | Verify and document Concierge-side delta_port HIL receiver (orchestrator `emit_hil_request()` → Concierge surfacing to user) — critical unverified link | F141 | [orchestrator/factory.py#L252](../../k1/orchestrator/factory.py#L252) |
| P1 | Wire sub-agent HIL dispatch: `Agent.execute()` → Orchestrator `emit_hil_request()` → Concierge | F140 | [agent_builder.py#L90](../../k1/fabric/core/agent_builder.py#L90) · [orchestrator/types.py#L1274](../../k1/orchestrator/types.py#L1274) |
| P1 | Implement orchestrator HIL timeout handler (config exists, no handler) | F141 | [orchestrator/config.py#L79](../../k1/orchestrator/config.py#L79) |
| P1 | Verify `PENDING_CLARIFICATIONS` is a live class in Concierge — referenced in 3 docs, not directly found | F138, F139, F140 | [planner.md#L4394](../../k1/planner/planner.md#L4394) |
| P2 | Implement escalation-to-human-supervisor path on persistent timeout/RED-band block | F138–F141 | new |
| P2 | Decide F138 CORRECTION/FEEDBACK/PREFERENCE paths: build OR amend doc | F138 | new |
| P2 | Decide F141 `PRIORITY_CONFLICT`/`RESOURCE_EXHAUSTION` types: build OR amend doc | F141 | new |
| P3 | Reconcile Planner timeout: doc 5min vs code 60s/120s — pick one | F139 | [hil_coordinator.py#L19](../../k1/planner/services/hil_coordinator.py#L19) |
| P3 | Rename `HILCoordinator` (Concierge) → `ConciergeHILCoordinator` and (Planner) → `PlannerHILCoordinator` to resolve naming collision (already in §5 P3) | F138, F139 | both files |
| P3 | Update K1_FLOWS.md §16: remove fictional event names; correct timeouts; add architectural note that F138–F141 are bidirectional-feedback flows, not pure HIL | doc | — |

---

## Cross-cutting findings (this batch)

1. **Doc-to-code event-name drift is severe in §15/§16.** Five named topics in §15/§16 do not exist in code: `k1.affect.analyzed.v1`, `k1.constraint.progress.v1`, `k1.hil.correction.received.v1`, `k1.hil.preference.captured.v1`, `k1.orchestrator.priority.updated.v1`. Doc cleanup pass needed.
2. **"Wired publishers without subscribers" anti-pattern** appears in §15 F132 and is structurally similar to §7 F69 `bus.subscribe` gap. Same root cause: `IBus.publish()` doesn't fail loudly when no subscribers exist.
3. **State-reader injection is inconsistent** in §10 — `AffectiveRouting`/`CognitiveLoadRouting` get one; `QoSIntegration`/`SecurityContext` don't. Same factory, divergent wiring.
4. **MCP transport gap** (§10 F101–F103) is a single missing injection point — exact same shape as §7 `section_provider=None` audit-J. One-line fix unblocks 3 flows once transports exist.
5. **§14 P3.1 collapse already happened in code** (`TOOL_REGISTRY`/`PROMPT_REGISTRY`/`AGENT_REGISTRY` → single `CapabilityRegistry`) but K1_FLOWS.md hasn't been updated.
6. **HIL is the most fragmented subsystem in the codebase** — 3 `HILRequest` types, 2 `HILCoordinator` classes, no unified port, inconsistent topics, no escalation. Highest tech-debt risk for cross-subsystem bugs.
7. **§11 Model Gateway is a positive outlier** — best-wired section in the audit; doc drift is mostly stale algorithm/TTL names, not structural gaps.
8. **Test-mode safety guards are correctly placed** — `model_mode="test"` requires explicit choice; `ValueError` on unknown mode prevents silent stub leakage to prod.

---

## ❌ Missing flows added by this batch (7 total)

| F# | Section | Name |
|---|---|---|
| F101 | §10 | Local MCP Server Discovery |
| F102 | §10 | Remote MCP → K0 Proxy |
| F103 | §10 | MCP Capability Registration |
| F111 | §11 | Proactive Decision LLM (confirms §8 F83) |
| F130 | §14 | Prompt Registry Registration |
| F134 | §15 | Affect Analyzed Event |
| F135 | §15 | Constraint Progress Event |

---

## Updated audit coverage (F01–F141 cumulative)

| Section | Flows | ✅ | ⚠️ | ❌ | 🔵 | 🟣 |
|---|---|---|---|---|---|---|
| §1 Front-LLM | 10 | 1 | 8 | 1 | — | — |
| §2 UltraBERT | 22 | 8 | 6 | 2 | 6 | — |
| §3 Tool Execution | 10 | 2 | 5 | 3 | — | — |
| §4 Orchestrator | 10 | 6 | 2 | 2 | — | — |
| §5 Planner | 7 | 5 | 2 | 0 | — | — |
| §6 Sub-Agent | 6 | 3 | 3 | 0 | — | — |
| §7 SessionState | 12 | 2 | 8 | 2 | — | — |
| §8 K0 Bridge | 10 | 0 | 2 | 6 | — | 2 |
| §10 Fabric | 9 | 3 | 3 | 3 | — | — |
| §11 Model Gateway | 8 | 4 | 3 | 1 | — | — |
| §14 Module Loader | 4 | 0 | 3 | 1 | — | — |
| §15 Event Bus | 6 | 0 | 4 | 2 | — | — |
| §16 HIL | 4 | 1 | 3 | 0 | — | — |
| **Audited (118)** | **118** | **35** | **52** | **23** | **6** | **2** |
| §9 Proactive | 7 | TBD | | | | |
| §12 Experience | 8 | TBD | | | | |
| §13 Rhythm | 8 | TBD | | | | |
| §17 Observability | 3 | TBD | | | | |
| §18 LLM Control Plane | 10 | TBD | | | | |
| **Total** | **154** | — | — | — | — | — |

**Audited 118/154 (77%) · 30% wired · 44% partial · 19% missing · 5% deprecated · 2% K0-blocked**

---

**Next:** §9 Proactive (F88–F94), §12 Experience (F112–F119), §13 Rhythm (F120–F127), §17 Observability (F142–F144), §18 LLM Control Plane (F145–F154). Given §8 F83 + §11 F111, §9 is expected to be entirely ❌.
