# K1 — Component Bloat & Misplaced-Responsibility Audit

**Date:** 2026-04-28
**Scope:** Apply single-responsibility lens to every K1 subsystem touched by the F01–F141 audit. Call out what each component is doing that **does not belong inside it**.
**Companion:** [K1_FLOWS_CONSOLIDATED_TODO.md](K1_FLOWS_CONSOLIDATED_TODO.md) · [§10/§11/§14/§15/§16](K1_FLOWS_SECTIONS_10_11_14_15_16_CURRENT.md)

Legend: 🔴 doesn't belong here · 🟡 belongs but over-scoped · 🟢 correct fit

---

## TL;DR — the 7 architectural smells

1. **Model Hub is a model provider** — it has metastasized into a billing system, a cache, a router, a health monitor, and a circuit breaker. Strip it back to: pick model → call model → return tokens.
2. **Fabric is a capability invoker** — it has metastasized into a policy engine (4 sibling routing classes), a telemetry emitter, a DAG compiler, and a hot-reload watcher. Strip it back to: resolve capability → invoke provider → return.
3. **HIL is fragmented across 4 subsystems** — opposite problem: 3 `HILRequest` types, 2 `HILCoordinator` classes, no port. Should be ONE port + ONE coordinator.
4. **SessionState is a section store** — has metastasized into an eviction engine, an emergency-mode FSM, a reconstruction-SLA tracker, a writer-role enforcer, and a priority shedder. Strip back to: read section, write section.
5. **Concierge FSM is a state machine** — has absorbed UltraBERT, Phase1 pipeline, tier classifier, router, HIL coordinator, arbiter, delta aggregator, writer registry, mutation guard. The FSM should drive transitions, not own all of them.
6. **Orchestrator is a DAG runner** — has absorbed Saga compensation, constraint resolution, HIL emission, priority queue, resource-exhaustion handler. DAG runner should run DAGs.
7. **Event Bus is a message bus** — fine, but two backends (Local + Rust), two priority schemes (V1 strict / V2 WFQ), an unwired SQLite outbox, a per-actor mailbox router, a DLQ that's only used by FSM, and `K1_BUS_BACKEND` env auto-detection. One bus. One priority scheme. One persistence story.

---

## §11 Model Hub — the worst offender

**What it is supposed to be:** Provider-of-record for LLM completions. Given a `HubRequest(model, messages, capability)`, return a `HubResponse(text, tokens)`.

**What it actually contains:**

| Component | Belongs here? | Where it should live |
|---|---|---|
| 5 provider plugins (OpenAI/Anthropic/Google/Ollama/vLLM) with `execute` + `stream_execute` | 🟢 yes — this IS the provider | — |
| Test-mode guard (`model_mode="test"` gates `StubProviderPlugin`) | 🟢 yes — provider-internal | — |
| `ModelSelector` (5-dim weighted: cost/latency/preference/placement/health) | 🟡 belongs, but over-scoped — should be 1 dim (preference) + fallback list | — |
| `RequestRouter` (9-step pipeline) | 🟡 9 steps for "pick a provider and call it" is bloat | collapse to 3: select → call → record |
| `_DefaultHealthQuery` + `_HEALTH_SCORES` (always HEALTHY today) | 🔴 health monitoring | move to **observability/probes** subsystem; Hub consumes via interface |
| `CostTracker` (manifest-driven $/token) | 🔴 financial accounting | move to **observability/cost** or **policy/budget** |
| `BudgetEnforcer` ($5/day, 3-tier ALLOW/DEGRADED/REJECT) | 🔴 spend governance | move to **policy/budget** — Hub should just receive a "deny" decision |
| `AuditLogger` | 🔴 audit pipeline | move to **observability/audit** |
| `ResponseCache` (LRU + TTL, skip TOOL_CALL/BATCH/MODERATE) | 🔴 cache is a cross-cutting concern | move to **fabric/cache** or **policy/cache**; Hub gets a cache-miss request |
| `ModelGatewayAdapter` circuit breaker (CB_MODEL, half-open 30s, canned response) | 🔴 resilience pattern | move to **kernel/resilience** wrapper around any port |
| `consumer_id="planner"` cost attribution stamping | 🔴 belongs to whoever is paying | caller stamps, Hub records |

**Recommended shape:**

```
ModelHub
├── plugins/          # 5 provider plugins (KEEP)
├── selector.py       # preference-list lookup (SHRINK from 5-dim to 1)
└── port.py           # IModelHubPort: execute(req) -> resp
```

Everything else moves to:

```
k1/observability/cost/         # CostTracker, AuditLogger
k1/observability/health/       # health probes
k1/policy/budget/              # BudgetEnforcer + 3-tier decisions
k1/policy/cache/               # ResponseCache (or k1/fabric/cache/)
k1/kernel/resilience/          # CircuitBreaker wrapper (used by ALL adapters)
```

**Net win:** Model Hub goes from ~15 classes to ~8. Cost/budget/cache become reusable across Concierge, Planner, MW, Fabric without each duplicating the logic.

---

## §10 Fabric — second worst offender

**What it is supposed to be:** Resolve a capability name → pick a provider → invoke it.

**What it actually contains:**

| Component | Belongs here? | Where it should live |
|---|---|---|
| `Resolver` (5-step pipeline) | 🟢 core job | — |
| `CapabilityRegistry` | 🟢 core | — |
| `ProviderMatcher` | 🟢 core | — |
| `ModuleLoader` (YAML scanner) | 🟡 borderline; OK to live in fabric | — |
| `AffectiveRouting` (reads `affective_now` from SS) | 🔴 routing policy | merge into **policy/routing** |
| `CognitiveLoadRouting` (reads cog load from SS) | 🔴 routing policy | merge into **policy/routing** |
| `QoSIntegration` (CONTEXT_BUDGET routing) | 🔴 routing policy | merge into **policy/routing** |
| `SecurityContext` (band → safety mailbox) | 🔴 routing/safety policy | merge into **policy/safety** |
| `EventEmitter` (3 topics) | 🔴 telemetry | move to **observability/events** OR have Fabric publish via a single `IEventPort` only |
| DAG compilation (F96) | 🔴 belongs to **Orchestrator** | already partially there; doc lies |
| Hot-reload daemon (`watch=False` in prod) | 🔴 operational concern | move to **kernel/lifecycle** OR delete |
| MCP transport injection (F101–F103) | 🟢 capability invocation | KEEP — this is fabric's job |

**Smell:** Four sibling routing classes (`AffectiveRouting`, `CognitiveLoadRouting`, `QoSIntegration`, `SecurityContext`) all do the same thing — read state, output a routing decision — but each is a separate class with inconsistent state-reader injection (2 get one, 2 don't). This is the textbook "should have been one PolicyEngine" pattern.

**Recommended shape:**

```
Fabric
├── resolver.py              # 5-step capability resolution
├── capability_registry.py   # store
├── provider_matcher.py      # match
├── module_loader.py         # YAML scan (OK here)
└── port.py                  # invoke

k1/policy/
├── routing.py               # ONE PolicyEngine combining affect+cog+qos+safety
├── budget.py                # from Model Hub
└── cache.py                 # from Model Hub
```

---

## §16 HIL — the opposite problem: under-unified

**What it is supposed to be:** ONE way for ANY subsystem to ask the user a question and get an answer back.

**What it actually is:** Three independent HIL implementations:

| Subsystem | Class | HILRequest type | Topic naming | Timeout |
|---|---|---|---|---|
| Concierge | `HILCoordinator` (`hitl_coordinator.py`) | `k1.concierge.protocols.hitl.HILRequest` | `task.suspended.v1` / `task.resume.v1` | none documented |
| Planner | `HILCoordinator` (`hil_coordinator.py`) | `k1.planner.services.HILRequest` | `k1.hil.clarification.v1` / `approval_req.v1` | 60s / 120s |
| Orchestrator | (`emit_hil_request()` on `IDeltaEmitPort`) | `k1.orchestrator.types.HILRequest` | `k1.hil.override_response.v1` / `fallback_response.v1` | 120s configured, no handler |

**No `IHILPort` in `k1/kernel/ports/`.** No shared `HILRequest`. No shared topic. Two `HILCoordinator` classes with the same name in different modules.

**Recommended shape (single port):**

```
k1/kernel/ports/hil_port.py
└── IHILPort.request(question, context, timeout) -> Future[HILResponse]

k1/concierge/services/hil_coordinator.py    # ONE coordinator
                                            # subscribes to ALL HIL topics
                                            # owns user surfacing
                                            # fans responses back via correlation_id

# Planner, Orchestrator, Sub-agents all call IHILPort.request(...)
```

**Net win:** Goes from 3 implementations + 3 types + 3 topic schemes → 1 port + 1 type + 1 topic. Eliminates the "Concierge-side delta_port HIL receiver is critical unverified link" gap.

---

## §7 SessionState — section store that grew an OS

**What it is supposed to be:** Per-session typed sections (read/write).

**What it actually contains:**

| Component | Belongs here? | Where it should live |
|---|---|---|
| `Manager` + tiered storage (HOT/WARM/COLD) | 🟢 core | — |
| Section classes (control, beliefs_active, history_active, ...) | 🟢 core | — |
| `MutationGuard` (preflight) | 🟢 borderline; OK | — |
| `EvictionEngine` + `SectionDataAdapter` (audit-J) | 🟡 over-scoped — should be a periodic GC, not a multi-tier engine with `section_provider` injection | simplify |
| `EmergencyMode` FSM (`set_emergency_mode(True)`) | 🔴 cross-system back-pressure | move to **kernel/lifecycle** or **policy/back-pressure** |
| `EmergencySummarizer` (F73 unbuilt) | 🔴 LLM compression | move to **memory_writer** or **k1/llm_ops** |
| `PriorityShedder` (F75 unbuilt, uses `MutationPriority` enum) | 🔴 priority scheduling | move to **bus/scheduler** OR delete |
| `ReconstructionSLA` (built but bypassed) | 🔴 SLA monitoring | move to **observability/slo** |
| `WriterRole` matrix + `enforce_writer()` | 🟡 over-scoped — auth concern | move to **policy/access** |
| `DeltaApplicator` (3× `None` callbacks) | 🟢 OK if it just applies | — |
| `MutationPriority` enum | 🔴 priority is a bus concern | delete from SS; move to bus |

**Smell:** SessionState carries the full back-pressure / SLA / priority / role-auth machinery. None of it should live in a "store typed sections" module.

---

## §4 Orchestrator — DAG runner that grew a control plane

**What it is supposed to be:** Compile a plan into a DAG, run steps, handle failures.

**What it actually contains:**

| Component | Belongs here? | Where it should live |
|---|---|---|
| `DAGExecutor` + `StepRunner` | 🟢 core | — |
| `_compensate()` (Saga pattern, currently empty body F46) | 🟢 belongs | implement, don't move |
| `ConstraintResolver` | 🟡 borderline; arguably planner concern | leave for now |
| `HIL_OVERRIDE_RESPONSE` / `FALLBACK_RESPONSE` events | 🔴 HIL concern | move to **HIL port** |
| `IDeltaEmitPort.emit_hil_request()` | 🔴 HIL concern | move to **HIL port** |
| `metrics.set_pending_hil(count)` | 🔴 HIL telemetry | move to **HIL port** |
| `PendingHILContext` + `HILRequest` | 🔴 HIL types | move to **HIL port** |
| `max_pending_hil=20` / `hil_timeout_ms=120_000` config | 🔴 HIL config | move to **HIL port** |
| `PRIORITY_CONFLICT` / `RESOURCE_EXHAUSTION` types (unimplemented) | 🟡 if implemented, belong here | TBD |
| `DAGExecutor.guards=[]` (timeout + max-retries) | 🟢 belongs | populate (F45) |
| Multi-agent bidding (F43/F44) | 🔴 doesn't exist; doc artifact | drop from doc |

**Smell:** ~40% of orchestrator surface is HIL plumbing that should live behind a single `IHILPort`.

---

## §1+§2 Concierge FSM — state machine that grew a brain

**What it is supposed to be:** Drive Front-LLM ↔ Tool ↔ Response state transitions.

**What it actually contains (just `controller.py` + `fsm/`):**

| Subsystem inside Concierge | Belongs here? | Where it should live |
|---|---|---|
| FSM state table + transitions | 🟢 core | — |
| `Front-LLM` invocation | 🟢 core | — |
| `UltraBERTPhase1Pipeline` | 🟡 borderline — Phase1 should be a separate "perception" subsystem | extract to `k1/perception/` |
| `UltraBERTAdapter` (multi-label NER, intent_scores, domains, etc.) | 🟡 perception | extract to `k1/perception/` |
| `Tier classification` (P3 demolition pending) | 🔴 deprecated-by-design; should already be deleted | delete (P0 #7) |
| `PassthroughPlannerStub` (F06) | 🔴 stub for missing plumbing | replace with real planner mailbox enqueue |
| `HILCoordinator` (Concierge-side) | 🔴 HIL concern | move to unified HIL coordinator |
| `SuspensionManager` | 🔴 HIL concern | move to unified HIL coordinator |
| `Arbiter` (`pending_hil` reading) | 🔴 HIL concern | move to unified HIL coordinator |
| `DeltaAggregator` (Concierge-internal, NOT subscribed to bus) | 🔴 should subscribe to bus + forward to MW | wire P0 #3 |
| `WriterRegistry` + role enforcement | 🔴 access control | move to **policy/access** (with SS one) |
| `MutationGuard` (Concierge-side) | 🔴 duplicate of SS `MutationGuard` | merge or delete |
| `Builders` (`build_hil_response`, etc.) | 🟢 OK as adapters | — |

**Smell:** "Concierge" has become the dumping ground for everything user-facing. Should be: FSM + Front-LLM glue. Perception, HIL, access-control, delta aggregation should all be peers, not children.

---

## §15 Event Bus — bus that grew options

**What it actually contains:**

| Component | Belongs here? | Notes |
|---|---|---|
| `LocalBus` (Python impl) | 🟢 core | — |
| `RustBusAdapter` (`k1_bus_core`) | 🟡 second backend | pick one or commit to abstraction tax |
| `BusFactory._resolve_backend()` (env `K1_BUS_BACKEND` auto-detect) | 🔴 deployment-time choice in code | move to config |
| `LocalMailbox` strict-priority V1 | 🟢 OK | — |
| WFQ V2 (future, no class exists) | 🔴 vapor | delete from doc OR commit to building |
| `LocalMailboxRouter` (per-actor) | 🟢 OK | — |
| Backpressure: doc says "URGENT evicts BACKGROUND"; code raises `BackpressureError` | 🔴 doc/code drift | pick one |
| `BusOutbox` (SQLite WAL P6.13) — built, NOT wired | 🔴 dead code | wire it (P1) OR delete |
| Per-actor mailbox depths (100/50/20/200 in doc; uniform in code) | 🔴 doc/code drift | pick one |
| DLQ: `BusStats.async_handler_dlq` counter only; FSM has its own `_publish_dead_letter` | 🔴 two DLQ schemes | unify |
| Five fictional topics (`k1.affect.analyzed.v1` etc.) | 🔴 doc lies | delete from doc |

**Smell:** Two backends, two priority schemes (V1+V2), two DLQ implementations, an unwired persistence layer, env-driven backend selection. Pick a lane.

---

## §14 Module Loader — already simplified ✅

This is the only positive case. P3.1 collapsed `TOOL_REGISTRY` + `PROMPT_REGISTRY` + `AGENT_REGISTRY` into one `CapabilityRegistry`. **Doc just hasn't been updated.** Good simplification, do more of this.

Remaining cleanup is small:

- `module.yaml` files exist but are dead — delete OR parse them
- `.md` prompts never load — drop `prompts/` from `_CONTRACT_SUBDIRS` OR build a real loader
- `finance/` referenced in doc doesn't exist — delete from doc

---

## §8 K0 Bridge — correctly scoped, blocked on K0

K0 Bridge itself is small and focused (just `SinkBridgeAdapter` + `SinkBridgeClient`). Its problems are all **K0-undeployed-blocked**, not bloat. Leave structure alone, deploy K0.

---

## Top 10 cross-cutting refactor opportunities

| # | Refactor | Removes | Adds |
|---|---|---|---|
| 1 | Extract `IHILPort` + unify 3 `HILCoordinator`/`HILRequest` impls | 3 types, 2 classes, 5 fictional topics | 1 port, 1 coordinator |
| 2 | Move cost/budget out of Model Hub → `policy/budget` | `CostTracker`, `BudgetEnforcer`, `AuditLogger` from Hub | `IBudgetPort` (Hub consumes decision) |
| 3 | Move cache out of Model Hub → `fabric/cache` or `policy/cache` | `ResponseCache` from Hub | reusable cache for any port call |
| 4 | Move circuit breakers out of every adapter → `kernel/resilience` | per-adapter CB code | one `CircuitBreaker` wrapper |
| 5 | Merge 4 routing classes in Fabric → one `PolicyEngine` | 4 sibling classes with inconsistent state_reader injection | 1 class, 1 injection point |
| 6 | Move emergency-mode/SLA/priority out of SS → `policy` + `observability` | `EmergencyMode`, `ReconstructionSLA`, `PriorityShedder`, `MutationPriority` from SS | reusable across subsystems |
| 7 | Extract perception (UltraBERT) out of Concierge → `k1/perception/` | UltraBERT classes from concierge/fsm/ | clean perception subsystem |
| 8 | Pick ONE event-bus backend (Local OR Rust) | `K1_BUS_BACKEND` env, factory branch, WFQ V2 vapor | one bus, one priority scheme |
| 9 | Wire OR delete unwired components: `BusOutbox`, hot-reload watcher, `ReconstructionSLA`, `_compensate()` body, `WriterRole` enforcement, `_DefaultHealthQuery` | dead code/false promises | code matches reality |
| 10 | Doc cleanup: kill ~10 fictional event topics + ~6 fictional class names + 2 fictional modules (`finance/`, `k1/proactive/`) | doc-fiction | doc matches code |

---

## Anti-patterns observed (codify these as review rules)

1. **"Sibling classes for the same concern"** — Fabric's 4 routing classes; SS's 3 emergency/SLA/shedder classes. **Rule:** if 3+ classes take the same inputs and produce the same shape of output, they're one class with strategies.
2. **"Cross-cutting concern stuffed into a leaf"** — cost/cache/CB inside Model Hub; HIL inside Orchestrator. **Rule:** if N subsystems need it, it lives at a layer N subsystems can reach (kernel/policy/observability).
3. **"Stub callbacks `=None`"** — `DeltaApplicator` (3× None), `EvictionEngine.section_provider=None`, `DAGExecutor.guards=[]`, `mailbox=None`, `mcp_transport=None`. **Rule:** required collaborators should be required constructor args. Optional collaborators should have a no-op default, not None.
4. **"Doc-fictional events/classes"** — 5 fictional topics in §15/§16; `finance_agent`, `MODULE_SCANNER`, `WFQ_SCHEDULER`, `CONSTRAINT_MANAGER`. **Rule:** doc names get tested against code; missing → delete from doc.
5. **"Two implementations of the same name"** — 2 `HILCoordinator`, 2 `DeltaAggregator`, 2 `MutationGuard`, 3 `HILRequest`. **Rule:** name collisions across modules are a refactor signal.
6. **"Built but unwired"** — `BusOutbox`, `ReconstructionSLA`, hot-reload watcher, `_compensate()` empty, `WriterRole`. **Rule:** if it's not wired in S1/S2/S3 boot, it doesn't exist. Either wire it next sprint or delete.
7. **"Algorithm/TTL/timeout drift"** — Model Hub doc 24h/1h cache vs code 5min flat; Planner doc 5min HIL vs code 60s/120s; Mailbox doc 100/50/20/200 vs code uniform. **Rule:** numeric constants in docs are lies until proven otherwise.

---

**Bottom line:** the codebase has two opposite diseases at once — **leaf bloat** (Model Hub, Fabric, SessionState, Concierge, Orchestrator each absorb cross-cutting concerns) and **leaf fragmentation** (HIL split across 3 subsystems with no port). Same fix for both: extract cross-cutting concerns to named horizontal layers (`policy/`, `observability/`, `kernel/resilience/`, single `IHILPort`).
