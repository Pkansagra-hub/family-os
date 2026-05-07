# K1 Production Wiring Plan — End-to-End (V3)

**Date:** 2025-06-01
**Status:** PLANNING
**Scope:** COMPLETE K1 system — all components, Bridge, IFL, kernel bootstrap, production wiring
**Replaces:** `KERNEL_RESTRUCTURE_PLAN.md` (V2 — 4 milestones, 42 issues, rejected as too narrow)

---

## Spec Sources

| Source | Lines | Purpose |
|--------|-------|---------|
| `k1/kernel/kernel.md` | 6,120 | Wiring spec, source of truth |
| `docs/whiteboard/k1_wiring_simulation.md` | 4,820 | Stress-test of spec vs code |
| `docs/whiteboard/k1_wiring_whiteboard.md` | 996 | Milestones, epics, design decisions D-1..D-16 |
| `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd` | 2,000+ | Full K1 cognitive architecture: L0–L6 + Bridge + IFL + Family Mesh |
| `bridge/README.md` | 657 | Bridge design: 5 responsibilities, 4 ports |
| `bridge/architecture_diagrams/interkernel_fabric_layer.mmd` | 368 | IFL architecture |

---

## THE PROBLEM

The kernel was built INSIDE `k1/concierge/kernel/` — one of the 7 components it should manage. K1 has 26 directories, 8 hexagonal components (7 known + MemoryWriter), and the entire Bridge + IFL layer is mostly unimplemented. Nothing is wired end-to-end.

---

## COMPLETE SYSTEM INVENTORY

### 8 Hexagonal Components (Port-Bearing)

| # | Component | Ports | Factory | Prod Adapters | Test Adapters | Status |
|---|-----------|-------|---------|---------------|---------------|--------|
| 1 | Bus | 3 | BusFactory (4 methods) | 2 | 0 | ✅ READY |
| 2 | SessionState | 5 | SessionStateFactory (3 methods) | 5 | 0 | ✅ READY |
| 3 | Fabric | 6 | FabricFactory (3 methods) | 5 | 7 | ✅ READY |
| 4 | ModelHub | 7 | ModelHubFactory (3 methods) | 7 | 0 | ✅ READY |
| 5 | Orchestrator | 9 | OrchestratorFactory (4 methods) | 9 | 8 | ✅ READY |
| 6 | Planner | 7 | PlannerFactory (4 methods) | 7 | 0 | ✅ READY |
| 7 | Concierge | 8 | ❌ NONE (E-0.5.21 planned) | 6 prod + 5 null | 7 | ⚠️ NO FACTORY (ports+adapters ready) |
| 8 | MemoryWriter | 5 | ❌ NONE | 0 | 0 | ⚠️ PORTS ONLY |

**Totals: 50 ports, 43 prod adapters, 23 test adapters**

### Bridge Layer

| Component | Status | Lines |
|-----------|--------|-------|
| `bridge/core/` (EnvelopeBuilder, Signing, Transport) | ✅ PRODUCTION (tested) | 773 |
| `bridge/kernel/` (KernelCommandPort — K1→K0 write) | ✅ PRODUCTION (tested) | 179 |
| `bridge/sync/` (LocalOutbox — offline queue) | ✅ PRODUCTION (tested) | 216 |
| `bridge/contracts/` (YAML + JSON Schema) | ✅ REAL | 330 |
| IKernelQueryPort (K1 reads from K0) | ❌ NOT IMPLEMENTED | 0 |
| IKernelSSEPort (K0 pushes events to K1) | ❌ NOT IMPLEMENTED | 0 |
| IConnectorGatewayPort (tools→devices) | ❌ NOT IMPLEMENTED | 0 |
| ISyncPort (multi-device sync) | ❌ NOT IMPLEMENTED | 0 |
| `bridge/codecs/` | ❌ EMPTY | 0 |
| `bridge/connector/` | ❌ EMPTY | 0 |
| `bridge/adapters/` | ❌ EMPTY | 0 |

### IFL (Universal Connector Protocol — bridge/ifl/)

| Component | Status |
|-----------|--------|
| IFL Protocol Engine (types, translator, validator) | ❌ DESIGN ONLY |
| IFL Manifest System (schema, signing, ingestion, catalog) | ❌ DESIGN ONLY |
| IFL Adapter Registry (registry, credentials, health, trust) | ❌ DESIGN ONLY |
| IFL Dispatch (company-hosted, WASM sandbox, router) | ❌ DESIGN ONLY |
| IFL Event System (webhook, SSE, poll receivers, routing) | ❌ DESIGN ONLY |
| IFL Connection Flow (6-step orchestrator) | ❌ DESIGN ONLY |
| ManifestTranslator (k1/fabric/ — auto-registration) | ❌ DESIGN ONLY |

### Support Subsystems

| Directory | Status | What It Is |
|-----------|--------|-----------|
| `k1/kernel/` | STUB (57 lines) + 6,120-line spec | THE kernel — bootstrap/wiring |
| `k1/k1_bus_core/` | REAL (6,983 lines Rust/PyO3) | Performance core: FlatBuffers, ring buffer, WFQ |
| `k1/contracts/` | ~50% REAL | ContractLoader, WiringLoader, validators. Runtime guards = stubs |
| `k1/tools/` | REAL (2,398 lines) | 4 MCP servers + 2 WASM tools |
| `k1/modules/` | YAML only (76 lines) | Module/plugin definitions |
| `k1/config/` | YAML only (394 lines) | Configuration files |
| `k1/agents/` | EMPTY + READMEs | Agent lifecycle/factory |
| `k1/cache/` | EMPTY + README | KV cache (512MB, thermal) |
| `k1/learning/` | 716-line design doc, no code | Two-system learning loop |
| `k1/coordination/` | EMPTY | LLM hub coordination, observability |
| `k1/connectors/` | EMPTY | External connector management |
| `k1/retention/` | EMPTY | Data lifecycle/deletion |
| `k1/scheduler/` | EMPTY | Cron/triggers |
| `k1/sse/` | EMPTY | K0 proactive notifications |
| `k1/supervision/` | EMPTY | Erlang-style supervision trees |
| `k1/tracing/` | EMPTY | OpenTelemetry |

---

## ARCHITECTURE LAYERS (From Skeleton Diagram)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  L0   External Interfaces (Web, Mobile, Voice, REST, WS, SSE) — DETACHED    │
├─────────────────────────────────────────────────────────────────────────────┤
│  L0.5 Module Loader (Scanner, Hot Reload, Tool/Prompt/Agent/Schema Reg)     │
├─────────────────────────────────────────────────────────────────────────────┤
│  L1   Concierge (FSM, Dual-LLM Actors, UltraBERT, HITL, Weave, Tools)       │
│  L1.5 Conversational Rhythm Controller                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  L2   Orchestrator (Blind DAG, Constraint Engine, Workflows, Connectors)    │
├─────────────────────────────────────────────────────────────────────────────┤
│  L2.5 Capability Fabric (Registry, Retrieval, Providers, Policy, ModelHub)  │
├─────────────────────────────────────────────────────────────────────────────┤
│  L3   Planner (4-Stage Pipeline, HIL, Discovery Tools)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  L4   Sub-Agents & Tools (Agent Lifecycle, MCP Runners, WASM Sandbox)       │
├─────────────────────────────────────────────────────────────────────────────┤
│  L5   SessionState (HOT 48KB + WARM 48KB + LOCAL COLD SQLite + K0 Sync)     │
├─────────────────────────────────────────────────────────────────────────────┤
│  L6   K0 Durable Storage (Cache/RAM → HOT/SQLite → COLD/Vector/KG)          │
├─────────────────────────────────────────────────────────────────────────────┤
│  🔐  Cross-Kernel Bridge (Transport, Security, Sync, Offline, IFL)          │
├─────────────────────────────────────────────────────────────────────────────┤
│  🔌  IFL (HomeKit, Nest, Tesla, Sonos, Ring, HealthKit, MQTT adapters)      │
├─────────────────────────────────────────────────────────────────────────────┤
│  📱  Family Device Mesh (iPhone + Laptop + Tablet + Hub, E2EE sync)         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Sharing Model (SIM-D-04 + SIM-D-36)

| Scope | Components |
|-------|-----------|
| **Shared** (1/process) | ModelHub, Orchestrator, Planner, BridgeClient |
| **Per-session** (N) | Bus, SessionState, Fabric, Concierge, MemoryWriter, Ledger, DeltaAggregator |
| **Shared object inside per-session host** | CapabilityRegistry (lives in Fabric, but single instance shared across all Fabric instances — SIM-D-36: "tools don't change per session, registry is thread-safe `RLock`, avoids double-registration") |

> **SIM-D-36 detail:** `CapabilityRegistry` is created ONCE at Tier 1 boot, then injected into both SharedFabric and every per-session Fabric via `FabricFactory.create_with_ports(..., capability_registry=shared_registry)`. Per-session Fabric owns its own adapters (SessionStateReader, EventPort, etc.) but shares the same CapabilityRegistry reference. **GAP:** FabricFactory doesn't yet accept an external `capability_registry` param — it creates a new one internally each time (SIM-GAP-48).

### Two-Tier Bootstrap (SIM-D-39)

| Tier | When | Creates |
|------|------|---------|
| Tier 1 — Startup | Once per process | Config → ModelHub → SharedFabric → BridgeClient → Orchestrator → Planner → Cross-wire |
| Tier 2 — Session | On demand per user | Bus → SessionState → Fabric(per-session) → Concierge → MemoryWriter → Register |

---

## 8 MILESTONES → 52 EPICS → 193 ISSUES

---

## MS-0: Full Component Code Scan, Architecture Documentation & Cross-Compatibility Verification

**Goal:** Read ALL production code for ALL 8 hexagonal components + Bridge. Produce verified ARCHITECTURE.md per component (source of truth). Build cross-component compatibility matrix. Run all existing tests. Flag every mismatch between spec, plan, and actual code BEFORE any wiring begins.
**Gating:** 9 ARCHITECTURE.md files written (8 components + Bridge). K1_COMPONENT_MATRIX.md complete. All existing tests passing. Every port, adapter, factory, and cross-component connection verified against actual code.

**Documentation Deliverables:**

| Document | Location | Contents |
|----------|----------|----------|
| Bus ARCHITECTURE.md | `k1/bus/ARCHITECTURE.md` | Full code scan: ports, internals, factory, config, tests |
| SessionState ARCHITECTURE.md | `k1/sessionstate/ARCHITECTURE.md` | Full code scan: ports, internals, factory, config, tests |
| Fabric ARCHITECTURE.md | `k1/fabric/ARCHITECTURE.md` | Full code scan: ports, internals, factory, config, tests |
| ModelHub ARCHITECTURE.md | `k1/model_hub/ARCHITECTURE.md` | Full code scan: ports, internals, factory, config, tests |
| Orchestrator ARCHITECTURE.md | `k1/orchestrator/ARCHITECTURE.md` | Full code scan: ports, internals, factory, config, tests |
| Planner ARCHITECTURE.md | `k1/planner/ARCHITECTURE.md` | Full code scan: ports, internals, factory, config, tests |
| Concierge ARCHITECTURE.md | `k1/concierge/ARCHITECTURE.md` | Full code scan: ports, internals, factory (MISSING), config, tests |
| MemoryWriter ARCHITECTURE.md | `k1/memory_writer/ARCHITECTURE.md` | Full code scan: ports, internals, factory (MISSING), config, tests |
| Bridge ARCHITECTURE.md | `bridge/ARCHITECTURE.md` | Full code scan: ports, core, codecs, connectors, sync, tests |
| **K1_COMPONENT_MATRIX.md** | `docs/architecture/K1_COMPONENT_MATRIX.md` | Cross-component wiring map, type compatibility, signature drift, blocking issues |

**ARCHITECTURE.md Template (per component):**

```markdown
# {Component} — Architecture Document
**Generated from code scan:** {date}
**Code root:** `{path}/`
**Total files:** {n}  |  **Total lines:** {n}

## 1. Port Surface
### {PortName} (Protocol | ABC)
- **Defined in:** `{file}:{line}`
- **Type:** Protocol (runtime_checkable) | ABC
- **Methods:**
  - `method_name(param: Type, ...) -> ReturnType` [async|sync]
- **Production Adapters:**
  | Adapter Class | File:Line | Wraps/Delegates To | Verified |
- **Test Adapters:**
  | Adapter Class | File:Line | Behavior | Verified |

## 2. Internal Architecture
### Core Classes
| Class | File:Line | Responsibility | Mutable State | Thread-Safe |

### Internal Message/Data Flow
{entry} → {processing stages} → {exit}

### Configuration
| Field | Type | Default | Injected Via |

### Internal Dependencies (imports)
| Import | Why | Coupling Risk |

## 3. Factory
- **File:** `{file}` | **Exists:** YES/NO
- **Methods:**
  | Method | Signature | What It Creates | What It Wires |
- **Gaps:** {what factory doesn't do yet}

## 4. Cross-Component Connections
### Outbound (adapters this component exposes for others)
| Consumer Component | Adapter Class | Satisfies Protocol | Signature Match | Verified |

### Inbound (ports this component expects injected)
| Provider Component | Expected Protocol | Injected Adapter | Signature Match | Verified |

## 5. Test Surface
| Test File | Test Count | Pass/Fail | What It Covers | Gaps |

## 6. Spec vs Code Delta
| Aspect | Spec/Plan Says | Code Actually Has | Action Required |
```

---

### Phase A: Per-Component Full Code Scan (8 epics, 1 per component)

Each epic follows the SAME 5-issue pattern. Every issue reads actual source code, documents findings, and produces a section of that component's ARCHITECTURE.md.

### E-0.1: Bus — Full Code Scan (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.1.1 | Bus port surface scan | Read ALL Protocol/ABC definitions in `k1/bus/`. Document every port with exact file:line, method signatures (params, return types, async/sync), runtime_checkable status. Read every production adapter — verify it implements all methods. Read every test adapter. Populate ARCHITECTURE.md §1. |
| I-0.1.2 | Bus internal architecture scan | Read all core classes (Bus, MailboxRouter, ring buffer, WFQ scheduler, FlatBuffer layer). Document class responsibilities, internal state, mutability, thread safety. Map message flow: publish → router → mailbox → consumer. Document Rust/PyO3 boundary (`k1_bus_core`). Populate ARCHITECTURE.md §2. |
| I-0.1.3 | Bus factory + config scan | Read `BusFactory` — document all methods with exact signatures, what each creates, what it wires. Read config surface. Flag gaps (missing methods, hardcoded values). Populate ARCHITECTURE.md §3. |
| I-0.1.4 | Bus cross-component connections | For each component that consumes Bus (SessionState via `SessionBusAdapter`, Fabric via `FabricBusAdapter`, Concierge via `BusInputAdapter`/`BusOutputAdapter`): read both sides, verify adapter method signatures match the consumer's Protocol exactly. Flag type mismatches. Populate ARCHITECTURE.md §4. |
| I-0.1.5 | Bus test scan + run | Inventory all existing Bus test files. Run them. Document pass/fail, coverage, gaps. Compare spec claims vs actual code. Populate ARCHITECTURE.md §5 + §6. |

### E-0.2: SessionState — Full Code Scan (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.2.1 | SessionState port surface scan | Read ALL 5 Protocol/ABC definitions. Document exact signatures. Read all production adapters (`SQLiteStorageAdapter`, `InMemoryStorage`, `DirectWriterAdapter`, `StandaloneLifecycle`, `LocalEventAdapter`, `SessionBusAdapter`, `NullSyncPort`). Read test adapters. Populate ARCHITECTURE.md §1. |
| I-0.2.2 | SessionState internal architecture scan | Read core: SessionStateManager, MutationGuard, HOT/WARM/COLD tiers, SQLite storage, event emission. Document state model (48KB HOT + 48KB WARM + LOCAL COLD). Map data flow: write request → MutationGuard → storage → event. Populate ARCHITECTURE.md §2. |
| I-0.2.3 | SessionState factory + config scan | Read `SessionStateFactory` — document all methods, `create_with_ports(5)` wiring. Read config. Flag gaps. Populate ARCHITECTURE.md §3. |
| I-0.2.4 | SessionState cross-component connections | Verify: Bus→SS (`SessionBusAdapter` ↔ SS `IEventPort`), SS→Fabric (`SessionStateReaderAdapter` ↔ Fabric `ISessionStateReader`), SS→Concierge (`SSMStateAdapter` ↔ Concierge `IStatePort`), SS→MemoryWriter (`ISessionReadPort`). Check exact type compatibility for each. Populate ARCHITECTURE.md §4. |
| I-0.2.5 | SessionState test scan + run | Inventory tests. Run them. Document results. Spec vs code delta. Populate ARCHITECTURE.md §5 + §6. |

### E-0.3: Fabric — Full Code Scan (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.3.1 | Fabric port surface scan | Read ALL 6 Protocol definitions (`ISessionStateReader`, `IEventPort`, `IBridgePort`, `IDeltaBusPort`, `IModelGatewayPort`, `IPromptSystemPort`). Document exact signatures. Read all production + test adapters. Populate ARCHITECTURE.md §1. |
| I-0.3.2 | Fabric internal architecture scan | Read core: CapabilityRegistry (RLock, register/query/embed), CapabilityRetrieval (embedding search), ModuleValidator (12 FAB rules), PolicyEngine, PromptSystem. Document internal state, capability lifecycle, retrieval pipeline. Populate ARCHITECTURE.md §2. |
| I-0.3.3 | Fabric factory + config scan | Read `FabricFactory` — document `create_with_ports()`, `_construct_fabric()`, shared vs per-session path. Document SIM-GAP-48 (no external `capability_registry` param). Read config. Populate ARCHITECTURE.md §3. |
| I-0.3.4 | Fabric cross-component connections | Verify: SS→Fabric (reader adapter), Bus→Fabric (event + delta adapters), ModelHub→Fabric (model gateway), Bridge→Fabric (`BridgeConnectionAdapter` ↔ `IBridgePort`), Fabric→Orchestrator (`FabricGatewayAdapter`), Fabric→Planner (`FabricRetrievalAdapter`), Fabric→Concierge (`FabricDispatchAdapter`). Check type compatibility for ALL 7+ connections. Populate ARCHITECTURE.md §4. |
| I-0.3.5 | Fabric test scan + run | Inventory tests. Run them. Document results. Spec vs code delta. Populate ARCHITECTURE.md §5 + §6. |

### E-0.4: ModelHub — Full Code Scan (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.4.1 | ModelHub port surface scan | Read ALL 7 Protocol definitions (`IModelHubPort`, `IEventPort`, `IHealthPort`, `IConfigPort`, `ICredentialPort`, `IStateReadPort`, `IMetricsPort`). Document exact signatures. Read all adapters. Populate ARCHITECTURE.md §1. |
| I-0.4.2 | ModelHub internal architecture scan | Read core: request routing, provider registry, budget management, credential injection, health aggregation, metrics emission. Document LLM call flow: request → provider select → credential inject → call → response → metrics. Populate ARCHITECTURE.md §2. |
| I-0.4.3 | ModelHub factory + config scan | Read `ModelHubFactory` — document all methods, `create_standalone(config)`. Read config (model registry, budgets, timeouts). Populate ARCHITECTURE.md §3. |
| I-0.4.4 | ModelHub cross-component connections | Verify: ModelHub→Fabric (`IModelGatewayPort`), ModelHub→Planner (`LLMGatewayAdapter`), ModelHub→Orchestrator (via Fabric gateway), ModelHub→MemoryWriter (`IModelHubPort` MW), ModelHub→Concierge (`HubLLMAdapter`). Check type compatibility. Populate ARCHITECTURE.md §4. |
| I-0.4.5 | ModelHub test scan + run | Inventory tests. Run them. Document results. Spec vs code delta. Populate ARCHITECTURE.md §5 + §6. |

### E-0.5: Orchestrator — Full Code Scan (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.1 | Orchestrator port surface scan | Read ALL 9 Protocol definitions. Document exact signatures for all 9 ports. Read all 9 production adapters + 8 test adapters. Populate ARCHITECTURE.md §1. |
| I-0.5.2 | Orchestrator internal architecture scan | Read core: Blind DAG engine, constraint engine, workflow storage, step executors, connector dispatch, admin interface. Document DAG execution flow: mailbox receive → DAG resolve → step execute → delta emit → bridge write. Rule: NO LLM in Orchestrator (ORCH-02). Populate ARCHITECTURE.md §2. |
| I-0.5.3 | Orchestrator factory + config scan | Read `OrchestratorFactory` — document all 4 methods, `create_production(config, 9 adapters)` signature. Read config. Populate ARCHITECTURE.md §3. |
| I-0.5.4 | Orchestrator cross-component connections | Verify: Fabric→Orch (`FabricGatewayAdapter` ↔ `IFabricGatewayPort`), Planner→Orch (`PlannerAdapter` ↔ `IPlannerPort`, hot-swap), SS→Orch (`StateReadAdapter` ↔ `IStateReadPort`), Bridge→Orch (`BridgeWriteAdapter` ↔ `IBridgeWritePort`), Bus→Orch (`MailboxAdapter` ↔ `IMailboxPort`). Check type compatibility. Populate ARCHITECTURE.md §4. |
| I-0.5.5 | Orchestrator test scan + run | Inventory tests. Run them. Document results. Spec vs code delta. Populate ARCHITECTURE.md §5 + §6. |

### E-0.6: Planner — Full Code Scan (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.6.1 | Planner port surface scan | Read ALL 7 Protocol definitions. Document exact signatures. Read all 7 production adapters + test adapters. Populate ARCHITECTURE.md §1. |
| I-0.6.2 | Planner internal architecture scan | Read core: 4-stage planning pipeline, HIL (Human-in-Loop), discovery tools, goal decomposition, step validation. Document flow: goal → decompose → validate → HIL check → plan output. Populate ARCHITECTURE.md §2. |
| I-0.6.3 | Planner factory + config scan | Read `PlannerFactory` — document all 4 methods, `create_production(config, 7 adapters)`. Read config. Populate ARCHITECTURE.md §3. |
| I-0.6.4 | Planner cross-component connections | Verify: ModelHub→Planner (`LLMGatewayAdapter` ↔ `ILLMPort`), Fabric→Planner (`FabricRetrievalAdapter` ↔ `IFabricRetrievalPort`), SS→Planner (`SnapshotStateReadAdapter` ↔ `IStateReadPort`), Bridge→Planner (`BridgeAdapter` ↔ `IBridgePort`), Planner→Orch (`PlannerAdapter`), Bus→Planner (`MailboxAdapter` ↔ `IMailboxPort`). Check type compatibility. Populate ARCHITECTURE.md §4. |
| I-0.6.5 | Planner test scan + run | Inventory tests. Run them. Document results. Spec vs code delta. Populate ARCHITECTURE.md §5 + §6. |

### E-0.7: Concierge — Full Code Scan (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.7.1 | Concierge port surface scan | Read ALL 8 Protocol definitions (`IInputPort`, `IOutputPort`, `IClassificationPort`, `ILLMPort`, `IStatePort`, `IDispatchPort`, `IDeltaPort`, `IMemoryPort`). Document exact signatures. Read all production adapters (8 + 5 null stubs) + 8 test adapters. Populate ARCHITECTURE.md §1. |
| I-0.7.2 | Concierge internal architecture scan | Read core: FSM (states, transitions), Dual-LLM actor model, UltraBERT classifier, HITL gates, Experience/Weave system, tool dispatch, conversation rhythm. Document flow: input → classify → FSM transition → LLM actor → dispatch → output. Populate ARCHITECTURE.md §2. |
| I-0.7.3 | Concierge factory + config scan | Document that ConciergeFactory DOES NOT EXIST. Read how Concierge is currently instantiated (if at all). Read config. Document what factory MUST create (reference OrchestratorFactory pattern). Populate ARCHITECTURE.md §3. |
| I-0.7.4 | Concierge cross-component connections | Verify: Bus→Concierge (`BusInputAdapter`/`BusOutputAdapter` ↔ `IInputPort`/`IOutputPort`), SS→Concierge (`SSMStateAdapter` ↔ `IStatePort`), Fabric→Concierge (`FabricDispatchAdapter` ↔ `IDispatchPort`), ModelHub→Concierge (`HubLLMAdapter` ↔ `ILLMPort`), Bridge→Concierge (`RecallMemoryAdapter` ↔ `IMemoryPort`). Check type compatibility. Populate ARCHITECTURE.md §4. |
| I-0.7.5 | Concierge test scan + run | Inventory tests. Run them. Document results. Spec vs code delta. Populate ARCHITECTURE.md §5 + §6. |

### E-0.8: MemoryWriter — Full Code Scan (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.8.1 | MemoryWriter port surface scan | Read ALL 5 Protocol definitions (`ISessionReadPort`, `IBridgeCommandPort`, `IEventSubscriptionPort`, `IModelHubPort`, `IHealthPort`). Document exact signatures. Note: NO production adapters exist yet. Populate ARCHITECTURE.md §1. |
| I-0.8.2 | MemoryWriter internal architecture scan | Read core: memory extraction pipeline, turn observation, LLM extraction, K0 command emission. Document 11 invariants (MW-01..MW-11). Document flow: turn.complete event → extract → validate → bridge command. Populate ARCHITECTURE.md §2. |
| I-0.8.3 | MemoryWriter factory + config scan | Document that MemoryWriterFactory DOES NOT EXIST. Read how MemoryWriter is currently structured. Document what factory MUST create. Populate ARCHITECTURE.md §3. |
| I-0.8.4 | MemoryWriter cross-component connections | Document planned connections: SS→MW (`ISessionReadPort` — lock-free reads), Bridge→MW (`IBridgeCommandPort` — fire-and-forget), Bus→MW (`IEventSubscriptionPort` — turn.complete.v1), ModelHub→MW (`IModelHubPort` — 2000 token budget). Verify port definitions exist even if adapters don't. Populate ARCHITECTURE.md §4. |
| I-0.8.5 | MemoryWriter test scan + run | Inventory tests (may be zero). Run what exists. Document coverage gaps. Spec vs code delta (MW spec vs actual code). Populate ARCHITECTURE.md §5 + §6. |

---

### Phase B: Bridge Full Code Scan (1 epic)

### E-0.9: Bridge — Full Code Scan (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.9.1 | Bridge existing code scan | Read ALL production code: `bridge/core/` (EnvelopeBuilder, Signing, Transport — 773 lines), `bridge/kernel/` (KernelCommandPort — 179 lines), `bridge/sync/` (LocalOutbox — 216 lines), `bridge/contracts/` (YAML + JSON — 330 lines). Document exact classes, methods, signatures. Populate `bridge/ARCHITECTURE.md` §1 + §2. |
| I-0.9.2 | Bridge gap inventory | Inventory all empty/stub directories: `bridge/codecs/`, `bridge/connector/`, `bridge/adapters/`, `bridge/ifl/`. Document what exists vs what MS-2/MS-3 plan says should exist. Verify `IKernelCommandPort` concrete class against planned Protocol ABC. Populate `bridge/ARCHITECTURE.md` §3. |
| I-0.9.3 | Bridge cross-component connections | Verify: Bridge→Fabric (`BridgeConnectionAdapter` ↔ Fabric `IBridgePort`), Bridge→Orchestrator (`BridgeWriteAdapter` ↔ Orch `IBridgeWritePort`), Bridge→Planner (`BridgeAdapter` ↔ Planner `IBridgePort`), Bridge→MemoryWriter (`IBridgeCommandPort`), Bridge→Concierge (`RecallMemoryAdapter` ↔ `IMemoryPort`). Check type compatibility for all existing connections. Populate `bridge/ARCHITECTURE.md` §4. |
| I-0.9.4 | Bridge test scan + run | Inventory all Bridge test files (5 files, ~1,334 lines). Run them. Document results. Populate `bridge/ARCHITECTURE.md` §5 + §6. |
| I-0.9.5 | Bridge contract verification | Read `bridge/contracts/command_port.protocol.yaml` and `command_envelope.json`. Verify schemas match actual EnvelopeBuilder output. Verify signing matches actual Signing backends. Flag any schema drift. |

---

### Phase C: Cross-Component Compatibility Matrix + Conformance Tests (2 epics)

### E-0.10: Cross-Component Compatibility Matrix (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.10.1 | Build wiring map | Using all 9 ARCHITECTURE.md §4 sections, build the FULL wiring map: every component→component connection, which adapter satisfies which Protocol, exact method signatures on both sides. Produce `docs/architecture/K1_COMPONENT_MATRIX.md` §1 (Wiring Map table). |
| I-0.10.2 | Type compatibility verification | For EVERY connection in the wiring map: compare adapter method signatures against Protocol method signatures. Check: param types match, return types match, async/sync match, optional params align. Produce `K1_COMPONENT_MATRIX.md` §2 (Type Mismatches — blocking wiring). |
| I-0.10.3 | Signature drift report | Compare what the plan (this document) claims about each component vs what ARCHITECTURE.md found in actual code. Flag: wrong port counts, wrong adapter names, wrong factory method counts, missing components. Produce `K1_COMPONENT_MATRIX.md` §3 (Signature Drift — code ≠ plan). |
| I-0.10.4 | Update plan inventory | Using findings from I-0.10.1 through I-0.10.3, update this plan's COMPLETE SYSTEM INVENTORY section (port counts, adapter counts, factory methods, status) to match verified reality. Fix any wrong issue descriptions in MS-1 through MS-7 that reference incorrect ports/adapters. |

### E-0.11: Conformance Test Suite (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.11.1 | Port conformance test framework | `tests/conformance/conftest.py` — parametrized test that takes (Protocol, Adapter) pairs and verifies: all Protocol methods exist on adapter, signatures match (param types, return type, async/sync), runtime_checkable passes. |
| I-0.11.2 | Per-component conformance tests | `tests/conformance/test_{component}.py` × 8 components — feed all (Protocol, Adapter) pairs from ARCHITECTURE.md into framework. Run. All must pass. |
| I-0.11.3 | Cross-component adapter bridge tests | `tests/conformance/test_cross_component.py` — for each wiring map connection: instantiate provider adapter, verify it satisfies consumer Protocol, test a real method call end-to-end (e.g., Bus publish → SessionBusAdapter → SS IEventPort handler). |
| I-0.11.4 | Factory wiring integration tests | `tests/conformance/test_factories.py` — for each factory that EXISTS (6 of 8): call the factory method, verify returned instance has all ports wired, call each port method with test data. Document the 2 missing factories (Concierge, MemoryWriter) as blocked for MS-1. |

**MS-0 TOTALS: 11 epics, 53 issues**

---

## MS-0.5: Architecture Gap Corrections (Post-Scan Fixes)

**Goal:** Resolve every gap, mismatch, missing adapter, type conflict, and structural deficiency discovered during the MS-0 code scan — BEFORE any new wiring begins. Each gap gets exactly one epic. Epics are ordered by dependency (cross-component type fixes first, then adapter gaps, then structural issues).
**Gating:** All gaps closed. Every cross-component connection verified compatible. No red flags remain in any ARCHITECTURE.md §4/§6.
**Source:** All 8 `ARCHITECTURE.md` files produced in MS-0.

---

### E-0.5.1: Planner→ModelHub Type Duplication (🔴 Critical)

**Source:** Planner ARCHITECTURE.md §4.2, ModelHub ARCHITECTURE.md §4 Connection #4
**Problem:** Planner defines its OWN `HubRequest`, `HubResponse`, `RequestConstraints` in `k1/planner/types.py` with a stale migration note. `k1/model_hub/types.py` already exists with incompatible definitions: `capability: str` vs `CapabilityType` (Enum), `payload: Dict[str, Any]` vs typed payloads, missing `ResponseMetadata`, missing `TokenUsage`. 5 type mismatches total.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.1.1 | Delete Planner local HubRequest/HubResponse/RequestConstraints | Remove duplicated types from `k1/planner/types.py`. Replace all imports across Planner with `from k1.model_hub.types import HubRequest, HubResponse, RequestConstraints`. |
| I-0.5.1.2 | Update LLMGatewayAdapter translation | Update `k1/planner/adapters/llm_gateway_adapter.py` to translate between Planner's `ILLMPort.execute()` and ModelHub's `IModelHubPort.execute()` using real K1 types. |
| I-0.5.1.3 | Verify Planner→ModelHub round-trip | Integration test: `PlannerFactory.create_for_testing()` → inject real `ModelHubFactory.create_for_testing()` → run a SKETCH stage → verify HubRequest/HubResponse types flow correctly. |

### E-0.5.2: Fabric→ModelHub Missing Bridge Adapter (🔴 Critical)

**Source:** ModelHub ARCHITECTURE.md §4 Connection #5, Fabric ARCHITECTURE.md §1.4
**Problem:** Fabric defines `IModelGatewayPort` (4 methods: `create_handle`, `is_model_loaded`, `list_models`, `find_model`). ModelHub exposes `IModelHubPort` (5 methods: `execute`, `stream_execute`, `discover_capabilities`, `discover_models`, `health`). Completely different APIs. No bridge adapter exists. `IModelGatewayPort` has no production adapter at all (only `TestModelGatewayAdapter`).

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.2.1 | ModelGatewayBridgeAdapter implementation | `k1/fabric/adapters/model_gateway_bridge.py` — implements `IModelGatewayPort`, wraps `IModelHubPort`. Translates `create_handle()` → `execute()`, `find_model()` → `discover_models()`, etc. |
| I-0.5.2.2 | ILLMHandle implementation | `k1/fabric/adapters/llm_handle.py` — implements `ILLMHandle` (Protocol from `k1/fabric/ports/model_gateway.py`). Wraps `IModelHubPort.execute()` with budget enforcement. |
| I-0.5.2.3 | Fabric→ModelHub integration test | Test: create `ModelGatewayBridgeAdapter(model_hub)`, verify all 4 `IModelGatewayPort` methods work through to ModelHub. |

### E-0.5.3: MemoryWriter→ModelHub Incompatible Port (🔴 Critical)

**Source:** ModelHub ARCHITECTURE.md §4 Connection #6, MemoryWriter ARCHITECTURE.md §2
**Problem:** MemoryWriter defines `IModelHubPort` with `chat(messages, budget_tokens, model_hint) → ChatResponse` — a simplified LLM call. ModelHub's `IModelHubPort` has `execute(HubRequest) → HubResponse` — completely different signature. No translation adapter exists.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.3.1 | MW ModelHub adapter implementation | `k1/memory_writer/adapters/model_hub_adapter.py` — implements MW's `IModelHubPort`, wraps K1's `IModelHubPort`. Translates `chat(messages, budget, hint)` → `execute(HubRequest(ChatPayload))` → `ChatResponse`. |
| I-0.5.3.2 | MW ModelHub adapter tests | Unit tests: verify translation, token budget enforcement (MW-06: 2000 tokens), model_hint routing. |

### E-0.5.4: Concierge→ModelHub Import Bug (🟡 Medium) ✅ COMPLETE

**Source:** ModelHub ARCHITECTURE.md §4 Connection #3
**Problem:** `k1/concierge/llm/model_hub_bridge.py` line 18 imports `HubHealthReport` and `ProviderHealthStatus` from `k1.model_hub.ports` — but these symbols are NOT exported from `ports/__init__.py`. They exist in `k1.model_hub.types`. This will fail at runtime.

**Resolution (completed):**

- Fixed import path in `model_hub_bridge.py` (line 18: `ports` → `types`)
- Added re-export in `k1/model_hub/ports/__init__.py` for backward compatibility
- Added 13 missing types to `k1/model_hub/types.py` (CapabilityResult, ChatResult, ToolCallResultSet, StructuredResult, ReasonResult, Usage alias, EmbedResult, ModerationCategory, ModerateResult, TokenCountResult, ImageInput, AudioInput, VoiceConfig)
- Fixed bridge production code: ResponseMetadata construction (added request_id, cost_usd, cache_hit), ModelInfo field names (model_id→id), model_preference field names (model_id→preferred_model), HubChunk fields (chunk_type→content/done/metadata/tool_calls), ToolCallResult.arguments type (dict→str), removed system_prompt access on non-ChatPayload types, removed duplicate method body
- Fixed 3 test files (test_model_hub_types.py: 84 tests, test_model_hub_bridge.py: 21 tests, test_model_hub_ports.py: 24 tests) to match actual type API
- 1139 tests pass across ModelHub + bridge/ports/types suites, 0 regressions

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.4.1 | Fix model_hub_bridge.py imports | ✅ Changed `from k1.model_hub.ports import HubHealthReport, ProviderHealthStatus` → `from k1.model_hub.types import HubHealthReport, ProviderHealthStatus`. Added re-exports in ports/**init**.py. Fixed all bridge production code + aligned 3 test files. 1139 tests pass. |

### E-0.5.5: Concierge→Orchestrator POC Type Migration (🟡 Medium) ✅ COMPLETE

**Source:** Orchestrator ARCHITECTURE.md §4 Connection #6, Concierge ARCHITECTURE.md §9.3
**Problem:** Concierge creates `TaskEnvelope` from POC-local types in `k1.concierge.orchestrator.types` — explicitly NOT from `k1.orchestrator.types`. Original plan assumed "fields structurally identical" but field-by-field analysis revealed **structural incompatibilities** across ALL 10 types (different field names, types, validation, factory method signatures). Simple import swap is not viable.

**Resolution (completed):**

- **I-0.5.5.1 (Map POC→production):** Produced complete field-level mapping for all 10 POC types. Found: TaskEnvelope has 7 field differences (task_id, budget, session_id, tier type, missing capabilities/params/constraints/timeout_ms). CapabilityRequest uses `name` vs production `capability_name`. CapabilityResult.error is `str` vs production `Optional[ErrorInfo]`. AggregatedResult.from_medium() signature incompatible (takes CapabilityResult vs List[StepResult]). StepResult.status is `str` vs production `StepStatus` enum. PlanStep uses `step_id` (8 fields) vs production `id` (14 fields). Budget and CannedResponse have NO production equivalents.
- **I-0.5.5.2 (Document type boundary):** Updated `k1/concierge/orchestrator/types.py` module docstring with complete architecture note documenting all type differences and production counterpart locations. POC types file RETAINED as legitimate concierge-internal contract layer. The translation adapter (POCFabricGatewayAdapter in `k1/concierge/kernel/bootstrap.py`) correctly bridges POC→production types at the dispatch boundary.
- **I-0.5.5.3 (Integration test):** `tests/k1/concierge/test_e055_poc_production_boundary.py` — verifies POCFabricGatewayAdapter correctly translates POC CapabilityRequest→production CapabilityRequest and production CapabilityResult→POC CapabilityResult. Verifies POC TaskEnvelope construction, AggregatedResult.from_medium() factory, Budget enforcement, and full stub→adapter→production round-trip. All existing 58 concierge orchestrator tests continue to pass.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.5.1 | Map POC types → production types | ✅ Complete field-level mapping: all 10 types have structural incompatibilities preventing simple import swap. Budget and CannedResponse are POC-only. |
| I-0.5.5.2 | Document type boundary + verify adapter | ✅ Updated types.py docstring with architecture note. POC types retained as concierge-internal contract. Translation adapter verified correct. |
| I-0.5.5.3 | Integration test: POC↔production boundary | ✅ `tests/k1/concierge/test_e055_poc_production_boundary.py` — round-trip translation test through POCFabricGatewayAdapter. |

### E-0.5.6: SessionState→MemoryWriter Missing Adapter (🟡 Medium) ✅ COMPLETE

**Source:** SessionState ARCHITECTURE.md §4.2 Connection #4, MemoryWriter ARCHITECTURE.md §9
**Problem:** MW defines `ISessionReadPort` (async Protocol: `snapshot()`, `read_section()`). SessionState has no adapter implementing this. The adapter directory `k1/memory_writer/adapters/` does not exist.

**Resolution (completed):**

- Created `k1/memory_writer/adapters/session_read_adapter.py` — `SessionReadAdapter` implements `ISessionReadPort`, wraps `SessionStateManager` directly (not through Fabric's reader) for minimal latency.
- `snapshot(sections)` loops `manager.get_section(name)` → `to_dict()` → collects into dict. Missing/unknown sections omitted.
- `read_section(name)` → `get_section(name)` → `to_dict()` → returns dict or None.
- `SectionNotFoundError` (KeyError subclass) caught gracefully → returns None/omits.
- **Key finding:** MW config lists 13 sections but 2 are phantom (`affective_baseline`, `ifl`) — not in SS's 15 real sections. Adapter handles these gracefully via KeyError catch. 11 of 13 MW sections are real SS sections.
- Updated `k1/memory_writer/adapters/__init__.py` to export `SessionReadAdapter`.
- MW-01 enforced: read-only, no write methods. MW-02 target: <1ms lock-free reads verified.
- 28 new tests in `tests/k1/memory_writer/test_session_read_adapter_056.py`. 208 total MW tests pass, 0 regressions.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.6.1 | SessionReadAdapter for MemoryWriter | ✅ `k1/memory_writer/adapters/session_read_adapter.py` — implements `ISessionReadPort`, wraps `SessionStateManager`. Async wrapper around sync `get_section()` → `to_dict()`. Catches `SectionNotFoundError` for phantom sections (affective_baseline, ifl). Exported via `adapters/__init__.py`. |
| I-0.5.6.2 | SessionReadAdapter tests | ✅ 28 tests: Protocol conformance (isinstance, no write methods), read_section (9 tests: existing/unknown/phantom/custom data/copy semantics/edge cases), snapshot (7 tests: all sections/phantom omission/empty/mixed/duplicates), latency (3 tests: single <1ms, 13-section <1ms, 100x stability), edge cases (5 tests: empty data/nested/slots/None manager). |

### E-0.5.7: Concierge Direct SS Import Leakage (🟡 Medium) ✅ COMPLETE

**Source:** SessionState ARCHITECTURE.md §4.3
**Problem:** Concierge bypasses `IStatePort` boundary with 6 direct imports from `k1.sessionstate` internals: `MutationRequest`, `BatchRequest`, `TaskStateEntry`, `IntentClassification`, `PrivacyBand`, `compute_temporal_anchor`, `SessionStateFactory`. If SS section schemas change, Concierge breaks.

**Resolution (completed):**

- **I-0.5.7.1 (Inventory):** Full grep found 35 `from k1.sessionstate` imports across Concierge: 6 production files (7 unique import statements), 10 test files (26 imports). Test imports kept as-is (tests legitimately need deep section access). Production imports classified as: (b) type imports (BatchRequest, MutationRequest, IntentClassification, PrivacyBand, TaskStatus, TaskStateEntry, TaskStateSection, ArtifactType, TaskArtifactEntry, TaskArtifactsSection, MetaSection), (b) function import (compute_temporal_anchor ×3), (c) factory import (SessionStateFactory).
- **I-0.5.7.2 (Facade):** Created `k1/sessionstate/public_types.py` — re-exports 16 symbols from 5 internal modules (ports.writer, sections.control, sections.task_state, sections.task_artifacts, sections.temporal_context, sections.meta, factory). Pure re-exports, no new logic. Grouped by source with `__all__` declaration.
- **I-0.5.7.3 (Redirect):** Updated 6 production files (7 import statements total):
  - `k1/concierge/tools/implementations.py` — BatchRequest, MutationRequest
  - `k1/concierge/fsm/task_bridge.py` — ArtifactType, TaskArtifactEntry, TaskArtifactsSection, TaskStateEntry, TaskStateSection, TaskStatus (consolidated from 2 imports to 1)
  - `k1/concierge/fsm/controller.py` — IntentClassification, PrivacyBand, compute_temporal_anchor (consolidated from 2 imports to 1)
  - `k1/concierge/protocols/hitl_wiring.py` — MetaSection (lazy import inside function)
  - `k1/concierge/kernel/bootstrap.py` — SessionStateFactory (lazy import inside function)
  - `k1/concierge/prompt/builder.py` — compute_temporal_anchor (2× lazy imports inside functions)
- 19 new tests in `tests/k1/sessionstate/test_public_types_057.py`: facade importability (3), re-export identity (15 — each symbol is `is` identical to deep import), boundary enforcement (1 — AST scan of all production Concierge .py files for deep SS imports).
- 2906 Concierge tests pass (46 pre-existing failures unrelated to changes), 4059 SS tests pass (5 pre-existing load test failures), 0 regressions.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.7.1 | Inventory all direct SS imports in Concierge | ✅ 35 imports found (6 production files, 10 test files). Production: 16 unique symbols from 5 SS internal modules. Tests: kept as-is. |
| I-0.5.7.2 | Create SS type re-export facade | ✅ `k1/sessionstate/public_types.py` — 16 symbols re-exported from 5 internal modules with `__all__` declaration. |
| I-0.5.7.3 | Redirect Concierge imports to facade | ✅ 6 production files updated (7 import statements). Zero deep SS imports remain in production Concierge code. AST-based boundary enforcement test verifies. |

### E-0.5.8: ModelHub ResponseCache Thread-Safety (🟡 Medium)

**Source:** ModelHub ARCHITECTURE.md §2 — ResponseCache
**Problem:** Docstring claims "lock-free reads, write lock for put + eviction" but NO actual locks exist in implementation. `OrderedDict` ops are not thread-safe. Under concurrent requests, cache corruption is possible.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.8.1 | Add threading.Lock to ResponseCache | ✅ Added `threading.Lock` to `ResponseCache.__init__`. Wrapped `get()`, `put()`, `invalidate()`, `clear()` with `self._lock`. All 38 existing tests pass. |
| I-0.5.8.2 | ResponseCache concurrency tests | ✅ `tests/k1/model_hub/test_response_cache_concurrency.py` — 8 stress tests: 100 concurrent puts, 100 concurrent gets, mixed R/W, eviction under contention, concurrent invalidate, stats consistency, clear+read, lock attribute check. All pass. Full suite: 1018 passed, 0 failed. |

### E-0.5.9: ModelHub→Bus Envelope Deserialization Gap (🟡 Medium)

**Source:** ModelHub ARCHITECTURE.md §4 Connection #1
**Problem:** `LLMRequestBusAdapter` wraps `IModelHubPort` and expects bus envelope delivery. But no code in `k1/bus/` deserializes bus envelopes into `HubRequest`. The bus-to-ModelHub pipeline is broken.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.9.1 | Bus→ModelHub envelope deserializer | ✅ `k1/model_hub/adapters/bus_envelope_deserializer.py` — `BusEnvelopeDeserializer` subscribes to `TOPIC_HUB_EXECUTE` (`k1.model_hub.execute.v1`), deserializes JSON `Envelope.payload` → `HubRequest` via `deserialize_hub_request()`, dispatches to `LLMRequestBusAdapter.execute()`, serializes `HubResponse` back → `Envelope` on `TOPIC_HUB_RESPONSE`. Handles non-JSON drop, malformed JSON, bad HubRequest fields. Async dispatch via `run_coroutine_threadsafe`. Exported from `adapters/__init__.py`. |
| I-0.5.9.2 | Bus→ModelHub round-trip test | ✅ `tests/k1/model_hub/test_bus_envelope_deserializer.py` — 18 tests: 7 deserialization unit tests (chat, tool_call, missing capability, empty trace_id, defaults, unknown capability, fallback payload), 2 serialization tests, 9 integration tests (subscribe/close lifecycle, non-JSON drop, malformed JSON drop, invalid HubRequest drop, full round-trip with LocalBus + background event loop, error resilience, response parent_id linking, topic constant verification). Full suite: 1036 passed, 0 failed. |

### E-0.5.10: ModelHub→SessionState Stub Binding (🟡 Medium) ✅ DONE

**Source:** ModelHub ARCHITECTURE.md §4 Connection #2
**Problem:** `SessionStateReadAdapter` in ModelHub is a stub using in-memory `Dict[str, Any]`. No production binding to real SessionState. Reads `persona` + `control` sections but never connects to actual SS.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.10.1 | ModelHub SS production adapter | ✅ `k1/model_hub/adapters/session_state_prod.py` — `SessionStateProdAdapter` implements `IStateReadPort`, wraps `SessionStateManager`. Uses `to_dict()` for WARM/COLD sections and `get_metadata()` for HOT sections (control, task_state, etc.). SectionNotFoundError → omit; catastrophic error → empty StateSnapshot. MH-01 enforced (no writes). Lock-free, `__slots__`. |
| I-0.5.10.2 | ModelHub SS adapter integration test | ✅ `tests/k1/model_hub/test_session_state_prod.py` — 16 tests across 7 classes: protocol conformance (3), persona read (2), control read (2), multi-section read (2), unknown sections (2), degraded mode (3), slot efficiency (2). Uses `SessionStateFactory.create_for_testing()` with real SS manager. Full suite: 1052 passed, 0 failed. |

### E-0.5.11: SessionState Missing Production Adapters ✅ DONE

**Source:** SessionState ARCHITECTURE.md §1.5
**Problem:** 5 production adapters referenced in architecture diagrams do not exist: `BridgeStorageAdapter`, `DeltaBusAdapter`, `ConciergeWriterAdapter`, `FabricLifecycleAdapter`, `BridgeSyncAdapter`. These are needed for MS-2+ but should be stubbed now.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.11.1 | SS production adapter stubs (5) | ✅ Created 5 stub adapters in `k1/sessionstate/adapters/`: `bridge_storage.py` (BridgeStorageAdapter→IStoragePort), `delta_bus.py` (DeltaBusAdapter→IEventPort), `concierge_writer.py` (ConciergeWriterAdapter→IWriterPort), `fabric_lifecycle.py` (FabricLifecycleAdapter→ILifecyclePort), `bridge_sync.py` (BridgeSyncAdapter→IK0SyncPort). All methods raise `NotImplementedError` with blocking message referencing MS-2+. Properties return safe defaults. `__init__.py` updated to export all 10 adapters. |
| I-0.5.11.2 | SS adapter stub tests | ✅ `tests/k1/sessionstate/test_production_adapter_stubs_0511.py` — 52 tests across 7 classes: per-adapter tests (instantiation, ABC isinstance, property defaults, NotImplementedError on all methods with message match), package export tests (2), slot efficiency tests (5). Full SS suite: 4116 passed, 0 failures. |

### E-0.5.12: SessionState Two-Phase Construction Smell ✅ DONE

**Source:** SessionState ARCHITECTURE.md §3.2
**Problem:** `create_standalone()` and `create_for_testing()` use two-phase construction — manager created with `None` ports, then private attributes mutated. Fragile and error-prone.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.12.1 | Refactor SS factory to single-phase | ✅ Refactored `create_standalone()` and `create_for_testing()` to single-phase: adapters created unbound → manager constructed with ALL ports (never None) → `bind_manager()` sets back-references. Added `bind_manager()` to `DirectWriterAdapter` and `StandaloneLifecycle`. Fixed `create_with_ports()` latent bug: `_k0_sync_port` added to `__slots__` and constructor param. All 35 existing factory tests pass. |
| I-0.5.12.2 | SS factory refactor tests | ✅ `tests/k1/sessionstate/test_single_phase_construction_0512.py` — 22 tests across 5 classes: no-None ports verification (6), DirectWriter bind_manager (4), StandaloneLifecycle bind_manager (4), single-phase end-to-end flow (8: correct binding, guard identity, start/stop, mutation). Full SS suite: 4138 passed, 0 regressions. |

### E-0.5.13: Fabric Missing Production Adapters (✅ DONE)

**Source:** Fabric ARCHITECTURE.md §1.4
**Problem:** 3 ports lack production adapters: `IModelGatewayPort` (covered by E-0.5.2), `IPromptSystemPort`, `IDeltaBusPort`. `LocalEventAdapter` serves dual production/test role.

| Issue | Title | Deliverable | Status |
|-------|-------|-------------|--------|
| I-0.5.13.1 | PromptSystem production adapter | `k1/fabric/adapters/prompt_system_prod.py` — implements `IPromptSystemPort`, loads prompt templates from configurable YAML directory. | ✅ DONE |
| I-0.5.13.2 | DeltaBus production adapter | `k1/fabric/adapters/delta_bus_prod.py` — implements `IDeltaBusPort`, wraps IBus for delta emission with JSON serialization. | ✅ DONE |
| I-0.5.13.3 | Separate production IEventPort adapter | `k1/fabric/adapters/event_port_prod.py` — dedicated production `IEventPort` adapter wrapping IBus. Removes dual-role from `LocalEventAdapter`. | ✅ DONE |

**Resolution:** Created 3 production adapters + 54-test suite (`tests/k1/fabric/test_adapters_prod_510_512.py`). All satisfy port protocols via structural subtyping, are thread-safe (RLock), and use `__slots__`. Updated `k1/fabric/adapters/__init__.py` with 3 new exports (5.2.10, 5.2.11, 5.2.12). Existing 263 adapter tests pass with no regressions.

### E-0.5.14: Fabric CapabilityRegistry Not Injectable (✅ DONE)

**Source:** Fabric ARCHITECTURE.md §3.5 (SIM-GAP-48)
**Problem:** `FabricFactory` always constructs `CapabilityRegistry` internally. There is no parameter to inject a pre-built registry. Per SIM-D-36, the registry should be shared across all per-session Fabric instances.

| Issue | Title | Deliverable | Status |
|-------|-------|-------------|--------|
| I-0.5.14.1 | Add capability_registry param to FabricFactory | Added optional `capability_registry` param to `create_with_ports()` and `_construct_fabric()`. If provided, uses it; if None, creates new (backward-compatible). | ✅ DONE |
| I-0.5.14.2 | FabricFactory shared-registry test | `tests/k1/fabric/test_capability_registry_injectable_0514.py` — 13 tests: backward-compat (6), shared registry cross-instance (7: identity, visibility, unregister, 3-instance, mixed, pre-populated). | ✅ DONE |

**Resolution:** Added `capability_registry: Optional[Any] = None` param to `FabricFactory.create_with_ports()` and `_construct_fabric()`. Step 3 uses injected registry if provided, else creates new. 13 tests pass. 110 existing factory-consuming tests pass with no regressions (2 pre-existing perf flakes excluded).

### E-0.5.15: Concierge Missing Observability Submodules (🟢 Low) ✅ DONE

**Source:** Concierge ARCHITECTURE.md §10.3
**Problem:** `obs/__init__.py` docstring references 6 submodules (`alerts`, `fsm_metrics`, `hitl_metrics`, `arbiter_metrics`, `weave_metrics`, `phase1_metrics`) that do not exist.
**Resolution:** Created all 6 stub files with functional placeholder classes (AlertRule, AlertEngine, AlertEvent, FSMMetricsSubscriber, HITLMetricsSubscriber, ArbiterMetricsSubscriber, WeaveMetricsSubscriber, Phase1MetricsSubscriber). Updated `obs/__init__.py` with imports and `__all__` exports. 23 tests pass (`test_e0515_obs_stubs.py`).

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.15.1 | Create obs submodule stubs | ✅ Created 6 stub files in `k1/concierge/obs/` with placeholder classes matching the docstring references. Each stub has functional methods that emit metrics via MetricsCollector. |

### E-0.5.16: Concierge POC Circuit Breakers Need HALF_OPEN (🟢 Low) ✅ DONE

**Source:** Concierge ARCHITECTURE.md §9.3 — Degradation Cascade
**Problem:** POC circuit breakers are simplified (open/closed only). Production needs HALF_OPEN + failure counting per `k1.fabric.circuit_breaker` pattern.
**Resolution:** Replaced POC CircuitBreaker in `degradation.py` with 3-state (CLOSED/OPEN/HALF_OPEN) implementation using `CircuitBreakerState` from `k1.fabric.circuit_breaker`. Added sliding-window failure counting, automatic OPEN→HALF_OPEN transition after timeout, probe success/failure handling. Thread-safe via `threading.Lock`. Backward-compatible `is_open()`/`force_open()`/`force_closed()` preserved. 23 tests pass (`test_e0516_circuit_breakers.py`). 520 existing concierge tests pass.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.16.1 | Replace POC CBs with Fabric CBs | ✅ Replaced `k1/concierge/orchestrator/degradation.py` CircuitBreaker (was in `degradation.py`, not `orchestrator_stub.py` as originally referenced) with 3-state circuit breaker using `CircuitBreakerState` from `k1.fabric.circuit_breaker`. |
| I-0.5.16.2 | CB state transition tests | ✅ Test: failure threshold → OPEN, timeout → HALF_OPEN, probe success → CLOSED, probe failure → OPEN. |

### E-0.5.17: Bus Configuration Gaps (🟢 Low) ✅ DONE

**Source:** Bus ARCHITECTURE.md §3.5
**Problem:** No `K1_BUS_BACKEND` env var support. No YAML/JSON config loading. Hardcoded-only configuration.
**Resolution:** Added `K1_BUS_BACKEND` env var override to `_resolve_backend()` in `k1/bus/factory.py` — case-insensitive, invalid values logged and ignored, empty/whitespace ignored. Created `k1/bus/config.py` with `BusConfig` frozen dataclass and `load_bus_config()` YAML loader. Created `k1/config/bus.yaml` with 18 timing rules matching hardcoded defaults. Fallback to `defaults.py` on missing file, invalid YAML, or missing PyYAML. Exported `BusConfig` + `load_bus_config` from `k1/bus/__init__.py`. 26 tests pass (`test_e0517_bus_config.py`). 604 existing bus tests pass with 0 regressions.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.17.1 | K1_BUS_BACKEND env var support | ✅ `_resolve_backend()` reads `K1_BUS_BACKEND` env var (highest priority). Valid values: `"auto"`, `"python"`, `"rust"` (case-insensitive). Invalid/empty values logged and ignored. 10 tests. |
| I-0.5.17.2 | Bus config file support | ✅ `k1/bus/config.py` — `BusConfig` dataclass + `load_bus_config(path?)` loads `k1/config/bus.yaml`. Parses timing_rules + default_mode. Falls back to hardcoded defaults on missing file, bad YAML, or missing PyYAML. 16 tests. |

### E-0.5.18: SessionState FlatBuffer Schema Drift (🟢 Low) ✅ DONE

**Source:** SessionState ARCHITECTURE.md §2.5
**Problem:** Generated FlatBuffers have 8 HOT + 4 WARM section types (12 total). Python code has 10 HOT + 5 WARM sections (15 total). The 3 additions (`task_state`, `task_artifacts`, `artifacts_warm`) were M4/M6 extensions without FlatBuffer schema updates.
**Resolution:** Created 3 new `.fbs` schemas (`task_state_section.fbs`, `task_artifacts_section.fbs`, `artifacts_warm_section.fbs`) in `k1/contracts/flatbuffers/sessionstate/`. Updated `session_kernel.fbs` with new includes and HotCore/WarmTier fields. Generated 7 Python FlatBuffer classes (`TaskStatus.py`, `ArtifactType.py`, `TaskStateEntry.py`, `TaskArtifactEntry.py`, `TaskStateSection.py`, `TaskArtifactsSection.py`, `ArtifactsWarmSection.py`) in `k1/sessionstate/generated/flatbuffers/K1/SessionState/`. Updated `HotCore.py` and `WarmTier.py` with new section accessors + builder functions. Updated `__init__.py` with all new exports. 28 tests pass (`test_e0518_flatbuffer_drift.py`).

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.18.1 | Add missing FlatBuffer schemas | ✅ Created 3 `.fbs` schemas + 7 generated Python classes. Updated `session_kernel.fbs`, `HotCore.py`, `WarmTier.py`, and package `__init__.py`. Schema now covers all 15 sections (10 HOT + 5 WARM). |
| I-0.5.18.2 | FlatBuffer round-trip tests for new sections | ✅ 28 tests across 6 classes: empty/populated round-trips for all 3 sections, field preservation, HOT→WARM demotion pipeline, schema drift verification (field counts, enum values, .fbs file existence). |

### E-0.5.19: MemoryWriter Empty `__init__.py` (🟢 Low) ✅ COMPLETE

**Source:** MemoryWriter ARCHITECTURE.md §10, §12 Gap G-5
**Problem:** `module.contract.yaml` claims 25+ exports from `k1.memory_writer.__init__`. The file is empty. Any import from `k1.memory_writer` for types, ports, or services will fail.

**Resolution (completed):**

- Populated `k1/memory_writer/__init__.py` with 78 exports across all MW modules: types, ports, enums, config, events, adapters, pipeline, factory, service, and circuit breaker.
- Full MW subsystem built through Phases 1–5 (E-MW-1.x through E-MW-5.x): types, invariants, config, context_assembly, place_resolver, pipeline stages, TurnDispatcher, Factory, Service, CircuitBreaker, 5 adapters (SessionRead, BridgeCommand, EventSubscription, ModelHub, Health), FabricRegistration.
- 773 MW tests passing.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.19.1 | Populate MW `__init__.py` | ✅ 78 exports covering all types, ports, enums, config, events, adapters, pipeline, factory, service, and circuit breaker symbols. |

### E-0.5.20: MemoryWriter Zero Test Coverage (🟢 Low) ✅ COMPLETE

**Source:** MemoryWriter ARCHITECTURE.md §11
**Problem:** Zero test files exist for memory_writer. Types, invariants, config, context_assembly, and place_resolver are all untested.

**Resolution (completed):**

- 773 MW tests across 20+ test files covering all MW modules:
  - Phase 1 (E-MW-1.x): types, invariants (MW-01..MW-11), config, context_assembly, place_resolver, events
  - Phase 2 (E-MW-2.x): pipeline stages (Extract, Transform, Validate, Emit), stage contracts
  - Phase 3 (E-MW-3.x): TurnDispatcher, turn lifecycle, error handling
  - Phase 4 (E-MW-4.x): Pipeline integration, Factory, Service, CircuitBreaker
  - Phase 5 (E-MW-5.x): Production adapters (28 tests), test adapters (20 tests), CB tests (22 tests), FabricRegistration integration (18 tests)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.20.1 | MW types + invariants tests | ✅ Full coverage: MemoryAtom, enums, frozen enforcement, all 11 invariant assertion helpers (MW-01..MW-11). |
| I-0.5.20.2 | MW context_assembly + place_resolver tests | ✅ Full coverage: temporal/spatial resolution, exact/prefix match, slug generation, edge cases. |
| I-0.5.20.3 | MW config + events tests | ✅ Full coverage: MWConfig construction, defaults, properties, event payload construction, topic constants. |

### E-0.5.21: ConciergeFactory — Port-Injected Component Factory (🟡 Medium)

**Source:** Concierge ARCHITECTURE.md §16, `k1_wiring_whiteboard.md` D-1..D-16, `k1_wiring_simulation.md` Step 3
**Problem:** Concierge has NO `ConciergeFactory`. Bootstrap is hard-wired in `k1/concierge/kernel/bootstrap.py` — a 28-step monolith that creates its OWN Bus, SessionState, Fabric, ModelHub by importing `poc.k1_poc.main.boot()`. This violates the hexagonal boundary: **Concierge is NOT a kernel — it is a COMPONENT that receives 8 external ports from the kernel.** No `create(PortBundle)` pattern exists, blocking Tier 2 kernel bootstrap.

**Existing infrastructure (Phase C1 ~85% done):**

- `k1/concierge/ports.py` — all 8 external port Protocols: `IInputPort`, `IOutputPort`, `IClassificationPort` (=Phase1Pipeline), `ILLMPort` (=IModelHubPort), `IStatePort`, `IDispatchPort`, `IDeltaPort` (=IBus), `IMemoryPort`
- `k1/concierge/adapters/` — 21 adapter files (7 test, 6 production, 5 null for two-tier boot, 3 support)
- `tests/k1/concierge/test_c1_port_protocols.py` + `tests/k1/concierge/ports/` — port protocol compliance tests

**Existing draft implementations (restored, ~60% of E-0.5.21 — imports clean ✅):**

- `k1/concierge/config/kernel.py` (37 lines) — `KernelConfig` dataclass extracted from `bootstrap.py` to break circular import. Identical 14 fields. Zero dependencies. Factory imports from here.
- `k1/concierge/factory.py` (497 lines) — `ConciergeFactory` class (instance-based, NOT static pattern yet). Has `create_session(**8 ports)` with 16-step wiring. Contains 3 internal adapter classes (`_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter`) already moved from bootstrap.py. 3 HITL callback helpers extracted.
- `k1/concierge/session.py` (435 lines) — `ConciergeSession` lifecycle wrapper with `start()`/`stop()`/`inject()`. `_mailbox_consumer()`, `_tick_experience()`, `_build_experience_context()` already moved from bootstrap.py. Properties for fsm, bus, model, session_state, started, etc.

**Gaps in restored drafts (still needed for E-0.5.21 completion):**

- `PortBundle` frozen dataclass — factory takes 8 loose kwargs instead of a typed bundle
- `ConciergeRuntime` dataclass — session.py uses `ConciergeSession` class (different approach: class vs dataclass)
- `ConciergeConfig` frozen dataclass — uses `KernelConfig` directly (works but not the clean separation planned)
- Static factory pattern (OrchestratorFactory convention) — current is instance-based factory
- `create_standalone()` / `create_for_testing(overrides)` / `create_with_ports()` — only `create_session()` exists
- `_ALL_PORT_KEYS` frozenset validation — missing
- No tests — zero test files exist
- `from k1.concierge.kernel.bootstrap import _build_delta_applicator` — circular dependency (factory imports from the thing it replaces)

**Convention to follow: `k1/orchestrator/factory.py` (OrchestratorFactory)**

- Static methods only, NO constructor (raises `TypeError` if instantiated)
- 4 public methods: `create_standalone()`, `create_for_testing(overrides)`, `create_with_ports(**ports)`, `create_production(config)`
- Private `_construct_concierge(config, adapters)` does all N-step wiring (numbered steps, explicit injection)
- Private `_build_test_adapters()` returns dict of all port→mock-adapter mappings
- `_ALL_PORT_KEYS` frozenset for upfront validation of required adapter keys
- Design: NO service locator, NO default args silently used, every dependency visible

**Precise bootstrap→factory decomposition (from `k1/concierge/kernel/bootstrap.py` L62→L380):**

The existing `start_kernel()` does 28 steps. The factory takes ownership of steps that wire Concierge internals (Layers 1-5). Steps that create INFRASTRUCTURE (Bus, SessionState, ModelHub, Fabric, CapabilityRegistry) stay in `start_kernel()` — those are the KERNEL's job, NOT the component factory's.

```
STAYS IN start_kernel()                    MOVES TO ConciergeFactory
────────────────────────                   ──────────────────────────
boot() → bus, router, adapter,             Layer 1 (Sync): LedgerStore, LedgerWriter
  front_mailbox, back_mailbox              Layer 2 (Sync): ConciergeController(bus, router)
_create_model(cfg) → model                 Layer 2 (Sync): Phase1Pipeline wiring → fsm._phase1_pipeline
_create_session_state(cfg) → ss            Layer 2 (Sync): fsm.set_ledger(), set_history_sink(),
_create_capability_registry() → registry                    set_session_state()
_create_fabric(registry) → fabric          Layer 3 (Sync): 2× ToolContext (front_ctx, back_ctx)
_build_recall_fn(cfg) → recall_fn          Layer 3 (Sync): front_dispatcher, back_dispatcher
                                           Layer 4 (Async): ExperienceLayer, DeltaAggregator/Applicator,
                                             HILCoordinator (3 bus callbacks), WeaveBatcher,
                                             WeavePolicy, UserActivityTracker, DeadLetterConsumer,
                                             OrchestratorStub (3 internal adapters)
                                           Layer 4 (Async): 10 FSM setters (set_hitl_coordinator,
                                             set_weave_batcher, set_weave_policy,
                                             set_activity_tracker, set_orchestrator)
                                           Layer 5 (Async): subscribe_front_events(), consumer task
```

**ConciergeConfig fields (extracted from `KernelConfig` L62-82, only Concierge-relevant):**

```python
@dataclass(frozen=True)
class ConciergeConfig:
    tool_tier: str = "LOW"                    # from KernelConfig.tool_tier — dispatchers use this
    enable_experience: bool = True            # from KernelConfig.enable_experience
    enable_delta: bool = True                 # from KernelConfig.enable_delta
    enable_hitl: bool = True                  # from KernelConfig.enable_hitl
    enable_orchestrator: bool = True          # from KernelConfig.enable_orchestrator
    auto_start_consumer: bool = True          # from KernelConfig.auto_start_consumer
    enable_ledger: bool = True                # from KernelConfig.enable_ledger
    enable_dead_letter_consumer: bool = True  # from KernelConfig.enable_dead_letter_consumer
    session_id: str | None = None             # from KernelConfig.session_id — ledger uses this
    seed_memories: list = field(default_factory=list)  # from KernelConfig.seed_memories
    phase1_pipeline: str = "stub"             # from get_config().phase1.pipeline (config/loader.py)
    phase1_warmup: bool = False               # from get_config().phase1.warmup_on_startup
    delta_batch_window_ms: int = 100          # from get_config().delta.batch_window_ms
    dead_letter_enabled: bool = False         # from get_config().fsm.dead_letter_enabled
    # EXCLUDED: ordered_bus, capture_bus, test_mode, session_mode — these are kernel/infra concerns
```

**PortBundle fields (mapped from ports.py 8 Protocols + bootstrap.py actual usage):**

```python
@dataclass(frozen=True)
class PortBundle:
    # REQUIRED — factory raises if None
    delta: IDeltaPort          # IBus — used for publish/subscribe (bus in bootstrap.py L125)
    input_: IInputPort         # Wraps front_mailbox (bootstrap.py L129)
    output: IOutputPort        # Wraps bus.publish for response emission
    state: IStatePort          # SessionState duck-type (bootstrap.py L181, session_state)
    llm: ILLMPort              # IModelHubPort (bootstrap.py L131, model)
    # OPTIONAL — default to null adapters (two-tier boot)
    classification: IClassificationPort | None = None  # Phase1Pipeline (bootstrap.py L155-168)
    dispatch: IDispatchPort | None = None              # Fabric+Orchestrator (bootstrap.py L199)
    memory: IMemoryPort | None = None                  # recall_fn closure (bootstrap.py L186)
```

**ConciergeRuntime fields (mapped from `KernelRuntime` L84-116, Concierge-owned subset):**

```python
@dataclass
class ConciergeRuntime:
    config: ConciergeConfig
    fsm: ConciergeController                     # from KernelRuntime.fsm
    front_dispatcher: Any                         # from KernelRuntime.front_dispatcher
    back_dispatcher: Any                          # from KernelRuntime.back_dispatcher
    front_ctx: ToolContext                        # NOT in KernelRuntime — new, exposed for session scoping
    back_ctx: ToolContext                          # NOT in KernelRuntime — new, exposed for session scoping
    # Optional subsystems (created in Layer 4, gated by ConciergeConfig flags)
    experience_layer: ExperienceLayer | None = None       # from KernelRuntime.experience_layer
    delta_aggregator: DeltaAggregator | None = None       # from KernelRuntime.delta_aggregator
    delta_applicator: Any | None = None                   # from KernelRuntime.delta_applicator
    hitl_coordinator: HILCoordinator | None = None        # from KernelRuntime.hitl_coordinator
    orchestrator: OrchestratorStub | None = None          # from KernelRuntime.orchestrator
    weave_batcher: WeaveBatcher | None = None             # in KernelRuntime as dynamic attr
    weave_policy: WeavePolicy | None = None               # in KernelRuntime as dynamic attr
    activity_tracker: UserActivityTracker | None = None   # in KernelRuntime as dynamic attr
    dead_letter_consumer: DeadLetterConsumer | None = None # from KernelRuntime.dead_letter_consumer
    ledger: LedgerWriter | None = None                    # from KernelRuntime.ledger
    ledger_store: InMemoryLedgerStore | None = None       # from KernelRuntime.ledger_store
    # Lifecycle state
    front_subscriptions: list[Any] = field(default_factory=list)  # from KernelRuntime.front_subscriptions
    consumer_task: asyncio.Task | None = None                     # from KernelRuntime.consumer_task
    started: bool = False                                         # from KernelRuntime.started
    # Injected refs (needed for lifecycle but NOT owned)
    _bus_ref: IDeltaPort | None = field(default=None, repr=False)       # back-ref for stop() teardown
    _state_ref: IStatePort | None = field(default=None, repr=False)     # back-ref for stop() teardown
```

**3 internal adapter classes that MOVE from bootstrap.py → factory.py (bootstrap.py L900-1100):**

```python
class _FabricGatewayAdapter:
    """Translates POC CapabilityRequest ↔ K1 CapabilityRequest for OrchestratorStub.
    Constructor: __init__(self, fabric_instance: IFabricPort)
    Method: async execute(k1_request) → K1 CapabilityResult
    Used by: OrchestratorStub(fabric_gateway=_FabricGatewayAdapter(fabric))"""

class _StateReadAdapter:
    """Wraps SessionState for OrchestratorStub read surface.
    Constructor: __init__(self, session_state: IStatePort)
    Methods: get_snapshot() → dict, read_section(name) → Any
    Used by: OrchestratorStub(state_read=_StateReadAdapter(ss))"""

class _DeltaEmitAdapter:
    """Routes deltas to DeltaAggregator, non-deltas to bus.
    Constructor: __init__(self, aggregator: DeltaAggregator | None, bus: IDeltaPort)
    Method: async emit(envelope) → None
    Used by: OrchestratorStub(delta_emit=_DeltaEmitAdapter(aggregator, bus))"""
```

**`_construct_concierge()` exact 15-step wiring (mirrors OrchestratorFactory._construct_orchestrator pattern):**

```
Step 1:  Validate PortBundle — assert 5 required ports non-None, default 3 optional to null adapters
Step 2:  Create LedgerStore + LedgerWriter (if config.enable_ledger, session_id from config)
Step 3:  Create ConciergeController(bus=ports.delta, router=<IMailboxRouter from ports.input_>)
Step 4:  Wire Phase1Pipeline: if config.phase1_pipeline=="ultrabert", create UltraBERTPhase1Pipeline
           else use StubPhase1Pipeline. Set fsm._phase1_pipeline.
           If ports.classification provided, use that instead.
Step 5:  Wire fsm.set_ledger(ledger_writer)
Step 6:  Wire fsm.set_history_sink(ports.state.get_section("history_active"))
Step 7:  Wire fsm.set_session_state(ports.state)
Step 8:  Extract _writer_port = getattr(ports.state, "_writer_port", None)
Step 9:  Build recall_fn from ports.memory (or _build_recall_fn(config.seed_memories))
Step 10: Create front_ctx = ToolContext(session_manager=ports.state, actor="front",
           recall_fn=recall_fn, fabric_port=ports.dispatch, writer_port=_writer_port)
Step 11: Create back_ctx = ToolContext(session_manager=ports.state, actor="back",
           recall_fn=recall_fn, fabric_port=ports.dispatch, writer_port=_writer_port)
Step 12: Create front_dispatcher = create_front_dispatcher(tier=config.tool_tier, ctx=front_ctx, bus=ports.delta)
Step 13: Create back_dispatcher = create_back_dispatcher(tier=config.tool_tier, ctx=back_ctx, bus=ports.delta)
Step 14: Construct ConciergeRuntime with all sync-created fields
Step 15: Return runtime (NOT started — caller must await runtime.start())
```

**`ConciergeRuntime.start()` exact 10-step async wiring (bootstrap.py L245-370):**

```
Step 1: If config.enable_experience → runtime.experience_layer = ExperienceLayer()
Step 2: If config.enable_delta → create DeltaAggregator + _build_delta_applicator(state, bus)
Step 3: If config.enable_hitl → create HILCoordinator with 3 bus callbacks
          (_on_suspended → build_task_suspended → bus.publish,
           _on_resume → build_task_resume → bus.publish,
           _on_timeout → build_task_failed → bus.publish)
          → fsm.set_hitl_coordinator(coordinator)
Step 4: Create WeaveBatcher(flush_fn) → fsm.set_weave_batcher(batcher)
Step 5: Create WeavePolicy() → fsm.set_weave_policy(policy)
Step 6: Create UserActivityTracker() → fsm.set_activity_tracker(tracker)
Step 7: If config.enable_dead_letter_consumer && config.dead_letter_enabled
          → DeadLetterConsumer(bus=self._bus_ref)
Step 8: If config.enable_orchestrator → OrchestratorStub(
          fabric_gateway=_FabricGatewayAdapter(ports.dispatch),
          state_read=_StateReadAdapter(ports.state),
          delta_emit=_DeltaEmitAdapter(aggregator, bus))
          → fsm.set_orchestrator(orchestrator)
Step 9: subscribe_front_events(bus, _route_front_subscription) → store handles
Step 10: If config.auto_start_consumer → asyncio.create_task(_mailbox_consumer(runtime))
          → self.started = True
```

**`ConciergeRuntime.stop()` exact 7-step teardown (bootstrap.py L370-420):**

```
Step 1: Cancel consumer_task (if running)
Step 2: Flush ledger (if enabled)
Step 3: Log dead-letter summary (if dead_letter_consumer active)
Step 4: Flush delta_aggregator (if enabled)
Step 5: fsm.teardown()
Step 6: Close session_state via _state_ref (if set)
Step 7: Close model via _llm_ref (if set) — self.started = False
```

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.21.1 | `PortBundle` + `ConciergeRuntime` + `ConciergeConfig` dataclasses | ✅ `ConciergeConfig` frozen dataclass (12 fields), `PortBundle` frozen dataclass (5 required + 3 optional ports), `@classmethod` factory pattern per SIM-D-09. In `k1/concierge/factory.py` (~850 lines). |
| I-0.5.21.2 | `ConciergeFactory` static class + `_construct_concierge()` 16-step sync wiring | ✅ `ConciergeFactory` @classmethod pattern: `create_standalone()`, `create_for_testing(overrides)`, `create_with_ports(**8 ports)`, `_construct_concierge()` 16-step wiring. 3 internal adapters, `_build_delta_applicator` inlined, `_seed_minimal_state()`, `_build_test_adapters()`, `_ALL_PORT_KEYS` frozenset. |
| I-0.5.21.3 | `ConciergeRuntime.start()` / `.stop()` async lifecycle | ✅ Already aligned in `session.py`. Lifecycle verified: `start()` creates consumer task, `stop()` 7-step teardown. No changes needed — session.py already correct. |
| I-0.5.21.4 | Bridge `start_kernel()` → `ConciergeFactory` | ✅ `bootstrap.py` imports `KernelConfig` from `config.kernel` (single source). 4 symbols re-exported from `factory.py` for backward compat: `_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter`, `_build_delta_applicator`. All 3036 existing tests pass unchanged. |
| I-0.5.21.5 | ConciergeFactory integration tests | ✅ `tests/k1/concierge/test_concierge_factory.py` — 52 tests across 11 classes: TestCreateStandalone, TestCreateForTesting, TestCreateWithPorts, TestLifecycle, TestPortBundle, TestConfigFlagGating, TestWiringVerification, TestToolContextWiring, TestNoInstantiation, TestConciergeConfig, TestBackwardCompatExports. All passing. |

### E-0.5.22: MemoryWriter No Factory (🟡 Medium) — ⏭️ SKIPPED

**Source:** MemoryWriter ARCHITECTURE.md §10, §12 Gap G-3
**Problem:** No `MemoryWriterFactory`. `__init__.py` is empty. Cannot be instantiated by Tier 2 bootstrap.
**Resolution:** Skipped — memory writer module is complete end-to-end. Factory pattern not needed at this stage.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.22.1 | MemoryWriterFactory skeleton | ⏭️ Skipped (memory writer complete end-to-end) |
| I-0.5.22.2 | MemoryWriterFactory wiring tests | ⏭️ Skipped (memory writer complete end-to-end) |

### E-0.5.23: Concierge 6 Unregistered Event Types (🔴 Critical)

**Source:** Concierge ARCHITECTURE.md §16.1 Gap G-3
**Problem:** 6 event types are defined as classes but NOT registered in `EVENT_TYPE_REGISTRY` (`k1/concierge/events/registry.py`). `deserialize_event()` will fail silently for these types — any bus replay, ledger replay, or delta deserialization involving them produces `None`. This is a **runtime bug**.

**Missing registrations:**

- `Phase1Classified` (`k1.phase1.classified.v1`) — from `events/conversation.py`, M10 E10.3.4
- `TaskRouted` (`k1.task.routed.v1`) — from `events/conversation.py`, M10 E10.3.4
- `HITLRequestedEvent` — from `events/hitl.py`, M6 lifecycle
- `HITLResolvedEvent` — from `events/hitl.py`, M6 lifecycle
- `HITLTimedOutEvent` — from `events/hitl.py`, M6 lifecycle
- `HITLBlockedRedEvent` — from `events/hitl.py`, M6 lifecycle

**Note:** `Phase1Classified` and `TaskRouted` also lack `from_payload()` overrides — base class `from_payload()` will lose domain-specific fields.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.23.1 | Register 6 missing event types in EVENT_TYPE_REGISTRY | ✅ Added 6 imports + 6 registry entries to `registry.py` (32 total). Added `from_payload()` to `Phase1Classified` (8 domain fields) and `TaskRouted` (3 domain fields) in `conversation.py`. HITL events already had `from_payload()`. Round-trip verified. |
| I-0.5.23.2 | Event registry completeness test | ✅ `tests/k1/concierge/test_event_registry_completeness.py` — 25 tests: `__subclasses__()` recursive completeness check, no duplicates, round-trip tests for all 6 types (type assertion, domain field preservation, double-roundtrip idempotence), edge cases (unknown/missing/empty event_type). Also updated `test_m01_event_validator.py` ALL_EVENT_CLASSES to include 6 new types. 3113 total concierge tests passing. |

### E-0.5.24: Concierge Kernel Bootstrap Zero Tests (🔴 Critical) ✅ COMPLETE

**Source:** Concierge ARCHITECTURE.md §16.1 Gap G-1
**Problem:** `k1/concierge/kernel/bootstrap.py` (32-step `start_kernel()`) and `k1/concierge/kernel/runner.py` (CLI entry point) have ZERO test coverage. This is the single most critical untested code path in K1 — every wiring error only surfaces at runtime. The factory (E-0.5.21) will eventually replace `start_kernel()`, but the existing bootstrap must be tested to validate the bridge from old → new.

**Resolution:** 68 tests across 2 files. Bootstrap smoke (48 tests): runtime fields populated, stop lifecycle, FSM wiring (ledger, session_state, hitl_coordinator, weave_batcher, weave_policy, activity_tracker, orchestrator), subsystem gating (5 disable flags), bus subscriptions, consumer task, session ID, model creation, KernelRuntime/KernelConfig field inventory. Runner CLI (20 tests):_parse_args defaults/explicit/invalid, config construction,_run lifecycle mock, signal handler registration. 3181 total concierge tests passing.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.24.1 | Bootstrap smoke test | ✅ `tests/k1/concierge/test_bootstrap_smoke.py` — 48 tests across 10 classes: TestBootstrapSmoke (14 runtime field assertions), TestStopKernel (3: started→false, idempotent, consumer cancel), TestFSMWiring (7: ledger, session_state, hitl_coordinator, weave_batcher, weave_policy, activity_tracker, orchestrator), TestSubsystemGating (8: enabled + 5 disable flags), TestBusSubscriptions (2), TestConsumerTask (2), TestSessionID (2: auto + custom), TestModelCreation (1), TestKernelRuntimeFields (2), TestKernelConfigDefaults (7). |
| I-0.5.24.2 | Bootstrap port wiring verification | ✅ Covered in TestFSMWiring (7 tests verifying FSM internal attributes: _ledger,_task_bridge,_hil_coordinator,_weave_batcher,_weave_policy,_activity_tracker,_orchestrator) + TestSubsystemGating (5 disable-flag tests). |
| I-0.5.24.3 | Runner CLI test | ✅ `tests/k1/concierge/test_runner_cli.py` — 20 tests across 6 classes: TestParseArgsDefaults (5), TestParseArgsExplicit (7: individual flags + combined), TestParseArgsInvalid (3: invalid session_mode/tool_tier/log_level), TestConfigFromArgs (2), TestRunLifecycle (2: start/stop mock, config passthrough), TestSignalHandling (1: SIGINT + SIGTERM registered). |

### E-0.5.25: Concierge Orchestrator Subsystem Untested (🔴 Critical)

**Source:** Concierge ARCHITECTURE.md §16.1 Gap G-2
**Problem:** All 6 files in `k1/concierge/orchestrator/` (degradation, interfaces, ports, routing, stub, types) have ZERO test coverage. `OrchestratorStub` is the gateway for MED/HIGH tier task execution — it bridges Concierge to K1 Fabric/Orchestrator. Untested routing logic means tier misroutes go undetected.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.25.1 | OrchestratorStub + routing tests | ✅ `tests/k1/concierge/test_orchestrator_stub.py` — 40 tests across 7 classes: TestHandleTask (10: 6-step flow, fabric execution, delta emit acceptance/completion, snapshot read, trace_id, step_results, fabric failure), TestHandleMultiStep (5: two caps, single, budget exceeded, emit events, partial failure), TestBudgetEnforcement (3: within budget, error fields, 1-call limit), TestStructuralInvariants (5: ORCH-01..04, port protocol compliance), TestRouteTaskSync (5: LOW/MEDIUM/HIGH dispatch records, budget, planner tokens), TestRouteTaskAsync (3: LOW emit_fn, MEDIUM dispatch_fn, no emit_fn ok), TestDispatchRecord (2: defaults, tier budget constants). |
| I-0.5.25.2 | Orchestrator degradation + interfaces tests | ✅ `tests/k1/concierge/test_orchestrator_stub.py` TestDegradationCascade (7 tests: no degradation all closed, HIGH→MEDIUM, MEDIUM→LOW, LOW→None, full cascade HIGH→None, canned response on CB open, normal dispatch record). `tests/k1/concierge/test_orchestrator_types.py` TestPortProtocols (7: runtime-checkable, count, separate core ports, execute/snapshot/emit/dispatch_envelope members), TestABCInterfaces (3: ABC subclasses, not instantiable, count), TestHighTierEvents (4: dict, count≥6, string values, k1. naming). |
| I-0.5.25.3 | Orchestrator type conformance tests | ✅ `tests/k1/concierge/test_orchestrator_types.py` — 59 tests across 13 classes: TestBudget (5: defaults, frozen, negative rejected ×2, custom), TestTaskEnvelope (6: construction, empty intent, LOW rejected, frozen, HIGH accepted, custom fields), TestCapabilityRequest (3: construction, empty name, frozen), TestCapabilityResult (3: success, failure, frozen), TestStepResult (4: construction, to_dict, failed status, frozen), TestAggregatedResult (7: basic, from_medium success/failure, from_multi_step success/mixed, to_dict, frozen), TestCannedResponse (3: defaults, custom, frozen), TestPlanRequest (3: construction, empty intent, frozen), TestPlanStep (5: construction, empty step_id/capability, to_dict, frozen), TestCommittedPlan (6: construction, empty plan_id/request_id, cycle detected, no cycle ok, frozen). |

### E-0.5.26: Concierge OPP Primitives Test Coverage (🟡 Medium)

**Source:** Concierge ARCHITECTURE.md §16.2 Risks R-5, R-6, R-7
**Problem:** Three OPP (Orchestral Prompt Protocol) primitives have zero test coverage:

- **R-5:** `TrustAccumulator` (OPP-4) — auto-approve logic (≥0.85 trust AND ≤0.5 risk). Incorrect trust scores could auto-approve dangerous operations.
- **R-6:** `EpisodicCompressor` (OPP-6) — wired via `on_pre_prompt_build`. Incorrect compression could drop important context.
- **R-7:** `DynamicIdentityContext` (OPP-7) — computes per-turn identity snapshots for prompt injection.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.26.1 | TrustAccumulator tests | ✅ `tests/k1/concierge/test_trust_accumulator.py` — 40 tests across 7 classes: TestInitialState (5: default trust, zero interactions, custom initial, config defaults), TestRecordOutcome (8: all 6 event types + unknown + interaction count), TestTrustClamping (4: clamped max/min, repeated approvals/rejections), TestShouldAutoApprove (9: boundary 0.84/0.85/0.86 × low/medium/high risk, default risk, max/zero trust, custom threshold), TestDynamicMaxRounds (7: default/high/very-high/low/mid trust, exactly 0.9/0.2 boundaries), TestSnapshotRestore (4: fields, round-trip recovery, auto_approvals counted, last_event_ns), TestAccumulationSequences (4: gradual buildup to 0.85, erosion, mixed sequence, timeout preserves). |
| I-0.5.26.2 | EpisodicCompressor tests | ✅ `tests/k1/concierge/test_episodic_compressor.py` — 38 tests across 7 classes: TestCompressionConfig (3: strategy constants, default config, custom config), TestShouldCompress (5: below/at/above threshold, zero turns, custom threshold), TestIdentifyCompressible (6: empty, fewer than window, segment grouping, HITL preservation, safety preservation, recent window intact), TestCompressSegment (10: basic, custom id, empty, key_facts extraction, string/dict entities, facts cap ≤5, topic from intent, default topic, compression count), TestCompressAll (4: below threshold, above threshold, episode count, empty), TestCompressedEpisode (5: to_prompt_block structure, no topic, no facts, token_estimate, compressed_at_ns), TestBuildCompressedContext (5: episodes+recent, empty episodes, empty recent, both empty, truncation). |
| I-0.5.26.3 | DynamicIdentityContext tests | ✅ `tests/k1/concierge/test_dynamic_identity.py` — 53 tests across 9 classes: TestInitialState (4: zero turns, empty expertise, config defaults, role constants), TestCompute (4: returns snapshot, user fields, turn count, relationship turns), TestRoleSelection (8: crisis→SUPPORTER, low→SUPPORTER, HIGH→EXPERT, inflight→EXECUTOR, early→GUIDE, >10→PEER, crisis overrides HIGH, HIGH overrides inflight), TestRoleAdaptationDisabled (2: always default, custom default), TestDomainExpertise (7: accumulates, capped at 1.0, multiple domains, no domain, tracking disabled, in snapshot, snapshot is copy), TestFormalityDrift (5: early formal, mid decrease, late casual, floor ≥0.2, disabled), TestEmotionalAttunement (6: crisis/low/neutral/positive/elevated/unknown bands), TestContextTags (5: multitasking, extended_session, domain, returning_topic, baseline), TestToPromptBlock (12: header/footer, user name present/absent, role, expertise, formal/casual/balanced register, attunement present/absent, tags present/absent). |

### E-0.5.27: Concierge InMemoryLedgerStore Production Path (🟡 Medium — Defer Candidate)

**Source:** Concierge ARCHITECTURE.md §16.2 Risk R-2
**Problem:** `InMemoryLedgerStore` is the only implementation. Thread-safe but not persistent — crash recovery works within process but data lost on restart. `_find_existing_seq()` is O(n). No `SqliteLedgerStore` exists. This is acceptable for MS-0.5 but needs a persistent path before MS-2.

**Recommendation:** Defer to MS-1 or MS-2. Document the gap. Add `SqliteLedgerStore` when Bridge persistence (MS-2) is built.

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-0.5.27.1 | LedgerStore persistence interface + test | Add `ILedgerStore.flush()` and `ILedgerStore.load()` to the Protocol (with default no-op implementations for backward compat). Add performance regression test for `_find_existing_seq()` at 10K events to document O(n) baseline. |

---

**MS-0.5 Summary:**

| Severity | Epics | Issues |
|----------|-------|--------|
| 🔴 Critical | 6 (E-0.5.1, E-0.5.2, E-0.5.3, E-0.5.23, E-0.5.24, E-0.5.25) | 16 |
| 🟡 Medium | 13 (E-0.5.4–E-0.5.14, E-0.5.21, E-0.5.22, E-0.5.26, E-0.5.27) | 35 |
| 🟢 Low | 8 (E-0.5.15–E-0.5.20) | 11 |
| **TOTAL** | **27 epics** | **62 issues** |

**Execution order:** 🔴 Critical first (E-0.5.1→E-0.5.3, then E-0.5.23→E-0.5.25), then 🟡 Medium (E-0.5.4→E-0.5.14, E-0.5.21→E-0.5.22, E-0.5.26→E-0.5.27), then 🟢 Low (E-0.5.15→E-0.5.20).

**Concierge-specific execution order (recommended):**

1. **E-0.5.23** (G-3: event registry — 10 min runtime bug fix, unblocks ledger/delta replay)
2. **E-0.5.21** (ConciergeFactory — the big one, 5 issues, creates the component factory)
3. **E-0.5.24** (G-1: bootstrap tests — validates old→new bridge from E-0.5.21.4)
4. **E-0.5.25** (G-2: orchestrator tests — validates tier routing through factory)
5. **E-0.5.26** (R-5/R-6/R-7: OPP primitives — lower risk, but needed before MS-1)
6. **E-0.5.27** (R-2: ledger persistence — defer candidate to MS-2)

---

## MS-1: Concierge + MemoryWriter Hexagonal Completion

**Goal:** Both remaining components get factories, session wrappers, and full adapter coverage.
**Gating:** `ConciergeFactory.create_session()` and `MemoryWriterFactory.create_session()` return working instances.

### E-1.1: ConciergeFactory Hardening + ConciergeSession Wrapper (4 issues)

**Dependency:** E-0.5.21 (factory skeleton + runtime lifecycle), E-0.5.23 (event registry), E-0.5.24 (bootstrap tests)
**Note:** E-0.5.21 delivers `ConciergeFactory.create_*()` + `ConciergeRuntime.start()/stop()`. MS-1 E-1.1 hardens the factory with `ConciergeSession` (per-request scope), config extraction, and stress tests.

**What `session.py` does (based on codebase analysis):**

The current `bootstrap.py` creates 2× `ToolContext` at boot time (front_ctx, back_ctx) with FIXED `cognitive_trace_id` values (e.g., `k-front-abcdef`). In production, each user REQUEST needs its own trace ID, writer_port scope, and potentially device-specific context. `ConciergeSession` wraps `ConciergeRuntime` to provide per-request scoping:

```python
# k1/concierge/session.py
@dataclass
class ConciergeSession:
    """Per-request scope wrapper around ConciergeRuntime.

    Created by: ConciergeFactory.create_session(runtime, request_ctx)
    Lifetime: one user turn (request → response)
    """
    runtime: ConciergeRuntime              # Shared long-lived runtime
    trace_id: str                          # Per-request cognitive_trace_id (uuid per turn)
    front_ctx: ToolContext                  # Scoped copy: runtime.front_ctx with overridden trace_id
    back_ctx: ToolContext                   # Scoped copy: runtime.back_ctx with overridden trace_id
    active_device_id: str | None = None    # Per-request device (from ToolContext.active_device_id)
    active_task_id: str | None = None      # Per-request task (from ToolContext.active_task_id)

    def inject(self, *, hitl_coordinator=None, dispatch=None, memory=None) -> None:
        """Late-bind optional ports into this session's ToolContext.
        Maps to ToolContext fields: hil_coordinator, fabric_port, recall_fn.
        Used for two-tier boot: kernel creates session, then injects real ports."""

    async def close(self) -> None:
        """Cleanup per-request state. Does NOT stop the runtime."""
```

**Scoped ToolContext creation (from `ToolContext` 11 fields in `k1/concierge/tools/implementations.py` L57):**

```python
# Per-request ToolContext is a shallow copy of runtime.front_ctx / back_ctx with overrides:
ToolContext(
    session_manager=runtime.front_ctx.session_manager,   # SHARED — same SessionState
    cognitive_trace_id=request_trace_id,                  # SCOPED — new uuid per request
    actor=runtime.front_ctx.actor,                        # SHARED — "front" or "back"
    writer_port=runtime.front_ctx.writer_port,            # SHARED — same MutationRequest port
    bundle_idempotency_cache={},                          # SCOPED — fresh dict per request
    active_device_id=request_device_id,                   # SCOPED — from request metadata
    hil_coordinator=runtime.front_ctx.hil_coordinator,    # SHARED (or injected via inject())
    active_task_id=request_task_id,                       # SCOPED — from request metadata
    fabric_port=runtime.front_ctx.fabric_port,            # SHARED (or injected via inject())
    recall_fn=runtime.front_ctx.recall_fn,                # SHARED (or injected via inject())
    capability_cache=None,                                # SCOPED — fresh per request
)
```

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-1.1.1 | `ConciergeSession` per-request wrapper | `k1/concierge/session.py` — `ConciergeSession` dataclass wrapping `ConciergeRuntime`. Creates scoped `ToolContext` copies (overrides `cognitive_trace_id`, `bundle_idempotency_cache`, `active_device_id`, `active_task_id`, `capability_cache` per request; shares `session_manager`, `writer_port`, `actor`, `fabric_port`, `recall_fn`, `hil_coordinator`). `inject()` method for late-binding optional ports (`hil_coordinator`, `fabric_port`/`dispatch`, `recall_fn`/`memory`). `close()` for per-request cleanup. Add `ConciergeFactory.create_session(runtime, *, trace_id, device_id, task_id)` static method. |
| I-1.1.2 | `ConciergeConfig` extraction from `KernelConfig` | `k1/concierge/config/concierge.py` — move `ConciergeConfig` from `factory.py` to dedicated config module. Add `from_legacy(kc: KernelConfig)` classmethod (maps 10 KernelConfig fields + reads 4 fields from `get_config()` loader). Add `with_overrides(**kwargs)` for test flexibility (returns new frozen instance with overrides). Add `from_dict(d: dict)` classmethod. Validate: `tool_tier` in `{"LOW","MED","HIGH"}`, `delta_batch_window_ms > 0`, `phase1_pipeline` in `{"stub","ultrabert"}`. |
| I-1.1.3 | Factory stress tests | `tests/k1/concierge/test_concierge_factory_stress.py` — (a) Concurrent session creation: 10 `ConciergeSession` from same `ConciergeRuntime`, verify `cognitive_trace_id` uniqueness, `bundle_idempotency_cache` isolation (mutate one, others unaffected). (b) Session isolation: `inject()` on one session does NOT affect sibling sessions. (c) Memory cleanup: after `session.close()` + `runtime.stop()`, no dangling asyncio tasks, no subscription leaks (assert `len(runtime.front_subscriptions) == 0`). (d) Rapid start/stop: 5 cycles of `runtime.start()` / `runtime.stop()` — no resource leaks. |
| I-1.1.4 | Delete old bootstrap after migration | Once all callers use factory: remove `start_kernel()` wiring logic from `kernel/bootstrap.py` (keep as thin delegate to `ConciergeFactory`), remove `_FabricGatewayAdapter` / `_StateReadAdapter` / `_DeltaEmitAdapter` classes (moved to factory.py in E-0.5.21.2), remove `KernelConfig` / `KernelRuntime` dataclasses (replaced by `ConciergeConfig` / `ConciergeRuntime`), remove `from poc.k1_poc.main import boot` dependency (kernel caller builds `PortBundle` directly). Gated on all E-0.5.24 bootstrap tests passing through factory path. |

### E-1.2: Concierge Adapter Hardening (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-1.2.1 | I/O adapter tests | `BusInputAdapter`, `BusOutputAdapter` — bus→adapter→FSM, envelope format. |
| I-1.2.2 | Core adapter tests | `SSMStateAdapter`, `FabricDispatchAdapter`, `RecallMemoryAdapter`. |
| I-1.2.3 | Classification + LLM adapter tests | `UltraBERTv4Adapter`, `HubLLMAdapter`. |

### E-1.3: MemoryWriter Factory + Pipeline (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-1.3.1 | MemoryWriterFactory | `k1/memory_writer/factory.py` — `create_session(5 ports) → MemoryWriterInstance`. |
| I-1.3.2 | MemoryWriter pipeline service | `k1/memory_writer/pipeline.py` — Observes turns, extracts memories, emits K0 commands. |
| I-1.3.3 | MemoryWriter 5 adapters | Implement all 5 port adapters: SessionRead, BridgeCommand, EventSubscription, ModelHub, Health. |
| I-1.3.4 | MemoryWriter config | `k1/memory_writer/config.py` — frozen dataclass, 11 invariants (MW-01..MW-11). |
| I-1.3.5 | MemoryWriter tests | Factory wiring, pipeline service, adapter conformance, invariant enforcement. |

> **⚠️ GOTCHA — MemoryWriter 3-Layer Bootstrap Architecture**
>
> MW uses three distinct layers that may appear redundant but each solves a different problem:
>
> | Layer | Module | Responsibility |
> |-------|--------|----------------|
> | **Adapters** | `adapters/*.py` | Pure protocol translation — each adapter wraps one K1 infrastructure object and exposes it as an MW `IPort`. No wiring logic, no lifecycle. |
> | **Factory** | `factory.py` | Internal assembly — takes 5 **ready-made** port instances, validates them (protocol conformance + MW-01..MW-11 invariants), constructs all pipeline internals (TurnDispatcher, stages, circuit breaker bindings), returns an **un-started** `MemoryWriterService`. |
> | **FabricRegistration** | `fabric_registration.py` | Bootstrap orchestration — the only layer that **creates** infrastructure. Creates `CircuitBreaker`, creates `HealthAdapter` with a forward-reference lambda (`get_started=lambda: service.is_started`), calls `Factory.create()`, then calls `service.start()`. |
>
> **Why FabricRegistration can't be folded into Factory:**
> `HealthAdapter` needs both the `CircuitBreaker` (created during bootstrap) AND `service.is_started` (but the service doesn't exist yet — it's the Factory's output). This circular dependency is resolved by FabricRegistration using a forward-reference lambda that captures `service` after Factory returns it. The Factory's contract is "give me 5 ready-made ports" — it cannot create its own inputs.
>
> **Rule of thumb:** Adapters translate. Factory wires. FabricRegistration orchestrates the chicken-and-egg bootstrap sequence.

**MS-1 TOTALS: 3 epics, 12 issues**

---

## MS-2: Bridge — Complete K1↔K0 Connectivity

**Goal:** All 5 bridge ports implemented (Command, Query, SSE, Obs, Connector). Formal Protocol ABCs. Offline awareness working end-to-end.
**Gating:** K1 can write to K0, read from K0, receive K0 push events, emit telemetry/feedback, and route capability invocations through connector gateway. All degrade gracefully offline.

**Bridge Port Map (from `architecture_diagrams/bridge/bridge_architecture.mmd`):**

| Port | K0 Endpoint | Direction | Purpose |
|------|-------------|-----------|----------|
| `IKernelCommandPort` | `POST /k0/command.submit` | K1→K0 ONE-WAY | Fire-and-forget writes (memory, session, beliefs, history, plans, IFL events, sync deltas) |
| `IKernelQueryPort` | `POST /k0/query.recall` | K1→K0→K1 REQUEST/RESPONSE | Multi-selector recall bundles: episodic, semantic, session, device, belief, graph |
| `IKernelSSEPort` | `GET /k0/sse.subscribe` | K0→K1 STREAMING | Real-time events: memory.formed, learning.advisory, proactive.signal, curiosity.intent, sync.complete, vector.stored |
| `IKernelObsPort` | `POST /k0/obs.emit` | K1→K0 ONE-WAY | Telemetry (metrics, logs) + feedback (FeedbackEnvelope for System 2 learning loop) |
| `IConnectorGatewayPort` | IFL Runtime | BIDIRECTIONAL | ALL external traffic: devices, APIs, services, sensors via IFL Universal Connector Protocol |

**Envelope Schemas (from diagram):**

- `CommandEnvelope`: cognitive_trace_id, tenant_id, space_id, topic, schema_uri, body, actor, device_id, band, sig_alg (Ed25519), sig_kid, sig, envelope_sha256, idem_key (BLAKE3)
- `QueryEnvelope`: selectors[] (type, topic, limit, cursor, after, query), space_id, tenant_id, max_latency_ms, fail_fast
- `SSETraceEvent`: cursor, topic, wal_pos, commit_ts, policy_stamp + backpressure (level: ok/throttle/shed, lag_ms, pending_events)
- `FeedbackEnvelope`: feedback_id, pipeline_id (P02/P06/P08), signal_class (CORRECTION/VALIDATION/IMPLICIT/EXPLICIT/OUTCOME), correlation, provenance, payload

**Command Topics (canonical: `k0/contracts/taxonomies/command_topics.yaml`):**
`memory.write` → P02, `session.snapshot` → Archive, `beliefs.archive` → Archive, `history.archive` → Archive, `plan.committed` → P02, `ifl.*` → P02, `sync.delta` → P07

**Query Selectors (canonical: `k0/contracts/taxonomies/query_selectors.yaml`):**
`episodic` (WAL recall), `semantic` (pgvector), `session` (SS history), `device` (IFL events), `belief` (archived beliefs), `graph` (KG traversal)

**SSE Events (K0→K1):**
`memory.formed.v1`, `k0.learning.advisory.v1`, `k0.proactive.signal.v1`, `curiosity.intent.v1`, `k0.sync.complete.v1`, `cognitive.vector.stored.v1`

### E-2.1: Bridge Port Formalization (5 issues — 1 per port)

| Issue | Port | Deliverable |
|-------|------|-------------|
| I-2.1.1 | `IKernelCommandPort` Protocol | Extract formal Protocol ABC from existing concrete `KernelCommandPort`. Methods: `submit(topic, schema_uri, body)`, `submit_batch(envelopes[])`. ONE-WAY fire-and-forget, no response. |
| I-2.1.2 | `IKernelQueryPort` Protocol | Define Protocol: `query(selectors[], space_id) → RecallBundle`, `multi_query()`, `paginate()`. REQUEST/RESPONSE. Selector types: episodic, semantic, session, device, belief, graph. |
| I-2.1.3 | `IKernelSSEPort` Protocol | Define Protocol: `subscribe(topics[], cursor) → AsyncIterator[SSETraceEvent]`, `ack(topic, offset)`. K0→K1 streaming. Backpressure handling (ok/throttle/shed). Header: `X-SSE-Subscriber`. |
| I-2.1.4 | `IKernelObsPort` Protocol | Define Protocol: `emit(kind, body)`. ONE-WAY. Kinds: `metrics` (prometheus snapshots), `logs` (structured entries), `feedback` (FeedbackEnvelope for System 2 model refinement). |
| I-2.1.5 | `IConnectorGatewayPort` Protocol | Define Protocol: `execute(adapter_id, action, params) → CapabilityResult`, `register_adapter(manifest, oauth_token)`, `unregister_adapter(adapter_id)`, `list_adapters() → AdapterStatus[]`. Security gateway for ALL external traffic. |

### E-2.2: Query Port Implementation (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-2.2.1 | QueryEnvelope + RecallSelector types | `bridge/core/query_types.py` — `QueryEnvelope` (selectors[], space_id, max_latency_ms, fail_fast), `RecallSelector` (type, topic, limit, cursor, after, query), `RecallBundle` result. |
| I-2.2.2 | QueryBuilder | `bridge/core/query_builder.py` — fluent builder for RecallSelector bundles. Episodic, semantic, session, device, belief, graph selector helpers. |
| I-2.2.3 | HttpQueryTransport | `bridge/kernel/query_port.py` — async HTTP POST to `/k0/query.recall`. Multi-selector bundles. Offline fallback to local cache. |
| I-2.2.4 | Query port tests | Multi-selector query, result merging, timeout, offline cache fallback, pagination. |

### E-2.3: SSE Port Implementation (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-2.3.1 | SSETraceEvent + SSE event types | `bridge/core/sse_types.py` — `SSETraceEvent` (cursor, topic, wal_pos, commit_ts, policy_stamp). All 6 event types: memory.formed, learning.advisory, proactive.signal, curiosity.intent, sync.complete, vector.stored. |
| I-2.3.2 | SSEReceiver + EventRouter | `bridge/kernel/sse_port.py` — async SSE client to `GET /k0/sse.subscribe`. Reconnect with exponential backoff. `EventRouter` for topic→handler mapping. |
| I-2.3.3 | SSEAcknowledger + CursorManager | `bridge/kernel/sse_ack.py` — `ack(subscriber_id, topic, offset)` for cursor advancement. `CursorManager` tracks wal_pos per topic for resume on reconnect. |
| I-2.3.4 | SSE backpressure + tests | Backpressure handling (ok → normal, throttle → reduce rate, shed → HTTP 429). Connection lifecycle, reconnect, event parsing, topic filtering tests. |

### E-2.4: Observability Port Implementation (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-2.4.1 | TelemetryBuffer | `bridge/kernel/obs_port.py` — batch emissions for metrics + logs. Buffer + flush to `/k0/obs.emit`. |
| I-2.4.2 | FeedbackBuilder | `bridge/kernel/feedback_builder.py` — build `FeedbackEnvelope` with correlation (session_id, event_ids[], wal_positions[], recall_id), provenance (source_message_id, recall_context_hash), and pipeline-specific payloads (P02/P08). Signal classes: CORRECTION, VALIDATION, IMPLICIT, EXPLICIT, OUTCOME. |
| I-2.4.3 | Obs port tests | Metrics batching, log buffering, feedback envelope construction + validation, offline drop policy (LOW priority = dropped). |

### E-2.5: Connector Gateway (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-2.5.1 | ConnectorGateway skeleton | `bridge/connector/gateway.py` — security pipeline: `TokenVerifier` → `AdapterVerifier` (FamilyOS CA signature check) → `RateLimiter` (per-adapter, per-user, per-action TokenBucket) → `CircuitBreaker` (per-adapter) → `RequestRouter`. |
| I-2.5.2 | ToolRegistry + ToolValidator | `bridge/connector/tool_registry.py` — registered tools with capabilities, actions, rate limits. `ToolValidator` checks action allowed + auth + rate. |
| I-2.5.3 | CredentialStore + OAuthFlow | `bridge/connector/credentials.py` — OAuth token store (encrypted at rest AES256-GCM), auto-refresh before expiry, API key rotation. `OAuthFlow` for authorization code exchange. |
| I-2.5.4 | Connector gateway tests | Security pipeline enforcement, tool registration, auth flow, rate limiting, circuit breaker, audit log verification. |

### E-2.6: Offline Awareness (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-2.6.1 | K0HealthChecker | `bridge/core/health_checker.py` — periodic `/healthz` ping (30s interval). States: `ONLINE` / `DEGRADED` / `OFFLINE`. Circuit breaker integration. |
| I-2.6.2 | K0AvailabilityStatus + DegradedModeManager | `bridge/core/degraded_mode.py` — mode transitions: ONLINE→DEGRADED→OFFLINE. Degradation policy: Query → local cache, Command → LocalOutbox queue, SSE → reconnect loop, Telemetry → drop (LOW priority). |
| I-2.6.3 | Offline priority system | Offline priority enforcement: CRITICAL (IFL local devices = always work), HIGH (SessionState LOCAL COLD = works), NORMAL (memory writes = queued), LOW (telemetry = dropped). |
| I-2.6.4 | Offline awareness tests | Health transitions, outbox drain on K0 return, priority enforcement, degradation cascades. |

### E-2.7: Bridge Codecs + Transport Adapters (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-2.7.1 | JSONCodec formalization | `bridge/codecs/json_codec.py` — formalize existing JSON envelope serialization. `CodecSelector` for content-type routing. |
| I-2.7.2 | FlatBufferCodec | `bridge/codecs/flatbuffer_codec.py` — binary serialization for performance path (commands + sync). |
| I-2.7.3 | Transport adapter registry | `bridge/adapters/http_adapter.py` (K0 REST), `bridge/adapters/tcp_adapter.py` (LAN device sync). Future: gRPC. |

### E-2.8: Security Core (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-2.8.1 | CapabilityToken system | `bridge/security/tokens.py` — `TokenIssuer` (issue), `TokenValidator` (verify signatures). `CapabilityToken`: issuer, subject, capabilities[], band, expires_at, signature. |
| I-2.8.2 | BandEnforcer | `bridge/security/bands.py` — privacy band enforcement: GREEN/AMBER/RED/BLACK. Per-band policy rules. |
| I-2.8.3 | AuditLogger + AuditStore | `bridge/security/audit.py` — all operations logged. Structured events. `AuditExporter` for compliance reports. |

### E-2.9: BridgeClient Facade (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-2.9.1 | IBridgeClient Protocol | `bridge/client.py` — unified facade: `query()`, `command()`, `subscribe()`, `observe()`, `connect()`, `health()`. Composes all 5 ports. |
| I-2.9.2 | ProductionBridgeClient | Concrete implementation composing all 5 ports + health checker + degraded mode + codec selection. |
| I-2.9.3 | StubBridgeClient | Offline stub returning empty/cached. For tests and offline-only operation. |

### E-2.10: Household Projection (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-2.10.1 | HouseholdProjection dataclass | `bridge/household.py` — frozen projection of family members, roles, preferences, device registry. |
| I-2.10.2 | hydrate_household() | Boot-time hydration from K0 query (selector: type=session) or local SQLite cache. |
| I-2.10.3 | Household tests | Online hydration, offline cache fallback, projection immutability, stale detection. |

**MS-2 TOTALS: 10 epics, 33 issues**

---

## MS-3: IFL — Universal Connector Protocol

**Goal:** IFL is the universal language all external services speak to connect to FamilyOS. Like Alexa Skills Kit but for EVERYTHING: devices, banks, health, transport, shopping, education, communication, sensors. Companies build IFL-compliant adapters. FamilyOS publishes the IFL Spec + SDK.
**Gating:** IFL Runtime operational. Manifest ingestion pipeline working. At least 2 adapters (1 company-hosted + 1 WASM) dispatching end-to-end through ConnectorGateway → IFL → external service. Auto-registration in Fabric Capability Registry verified.

**IFL Architecture (from `architecture_diagrams/bridge/interkernel_fabric_layer.mmd`):**

```
Layer 1: K1 Fabric (caller — auto-registered capabilities from IFL manifests)
Layer 2: Bridge ConnectorGateway (security, auth, rate limiting, offline queue)
Layer 3: IFL Runtime (manifest mgmt, protocol translation, adapter routing)
Layer 4: IFL Adapters (company-hosted endpoints OR WASM sandboxed)
Layer 5: External Services and Devices (the real world)
Storage: K0 (adapter registry, credentials, event persistence)
```

**Key Design Decisions (from diagram):**

| Decision | Rule |
|----------|------|
| Manifest Trust | FamilyOS signing REQUIRED. Only owning company can publish (Chase builds `com.chase.*`). Company domain verification + FamilyOS CA code signing. |
| Adapter Hosting | Primary: company-hosted (their infra). Optional: WASM sandboxed (64MB mem, 5s CPU, no network) for offline/local. |
| Auto-Registration | User connects adapter (OAuth) → IFL pulls manifest → translates to Fabric tool contracts → registers in Capability Registry + Embedding Index. |
| Event Taxonomy | `ifl.{category}.{adapter_id}.{event_type}` — e.g., `ifl.finance.chase.transaction.alert` |
| Adapter Categories | home, health, finance, transport, shopping, calendar, education, communication, media, security, energy, custom |

**IFL Message Format:**

- `IFLRequest`: ifl_version, request_id, adapter_id, action, params, auth_token, trace_id, timestamp
- `IFLResponse`: request_id (correlation), status (success/error/pending), data, error, latency_ms, adapter_version
- `IFLEvent`: event_id, adapter_id, topic, data, timestamp, safety_band

**Capability Manifest Schema (`ifl_manifest.schema.yaml`):**

- Header: ifl_version, adapter_id, adapter_name, company, category, hosting_mode, endpoint/wasm_module, auth_flow, familyos_signature
- Capabilities[]: name, type (read/execute/subscribe), description, safety_band_min, inputs, output, latency_hint_ms, rate_limit, requires_confirmation, cost_tier
- Events_inbound[]: topic, full_topic, description, schema, frequency_hint, safety_band_min
- Events_outbound[]: topic, trigger
- Permissions_required[]: scope, reason + data_retention, data_shared_with

### E-3.1: IFL Protocol Engine (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-3.1.1 | IFL message types | `bridge/ifl/protocol/types.py` — `IFLRequest`, `IFLResponse`, `IFLEvent` envelope dataclasses. ifl_version 1.0. Request/response correlation via request_id. |
| I-3.1.2 | Protocol Translator | `bridge/ifl/protocol/translator.py` — `to_ifl(fabric_request) → IFLRequest` (Fabric CapabilityRequest → IFL envelope), `from_ifl(ifl_response) → CapabilityResult`, `translate_event(ifl_event) → K0CommandEnvelope` (topic: `ifl.{category}.{adapter}.{event}`). |
| I-3.1.3 | Payload Validator | `bridge/ifl/protocol/validator.py` — `validate_request(request, manifest)` (check params vs capability input schema), `validate_response(response, manifest)` (check output vs declared schema, flag unexpected fields), `validate_event(event, manifest)` (check topic + schema, reject undeclared events). |
| I-3.1.4 | Protocol engine tests | Translation round-trip, validation enforcement, event taxonomy, error handling. |

### E-3.2: IFL Manifest System (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-3.2.1 | Manifest schema | `bridge/ifl/manifest/ifl_manifest.schema.yaml` — complete YAML schema for capability manifest. Header + capabilities[] + events_inbound[] + events_outbound[] + permissions_required[] + data_retention. |
| I-3.2.2 | ManifestSigner + FamilyOS CA | `bridge/ifl/manifest/signing.py` — `sign(manifest, company_cert) → signed_manifest`, `verify(signed_manifest) → bool`, `check_revocation(adapter_id) → bool`. Company domain ownership verification. |
| I-3.2.3 | ManifestIngestion pipeline | `bridge/ifl/manifest/ingestion.py` — 4-step pipeline: `pull_manifest(endpoint)` → `verify_signature()` (FamilyOS CA + company domain) → `validate_manifest()` (schema + safety band audit) → `store_manifest()` (persist + emit `ifl.adapter.manifest.ingested.v1`). |
| I-3.2.4 | AdapterCatalog (Marketplace) | `bridge/ifl/manifest/catalog.py` — all published adapters, searchable by category/name. `search_adapters(category?, query?)`, `browse_categories()`, `get_adapter_info(adapter_id)`. Cached locally, refreshed daily from FamilyOS Marketplace API. |
| I-3.2.5 | Manifest system tests | Schema validation, signing/verification, ingestion pipeline, catalog search, revocation check. |

### E-3.3: IFL Adapter Registry (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-3.3.1 | AdapterRegistry | `bridge/ifl/registry/adapter_registry.py` — `register(adapter_id, manifest, credentials)`, `unregister()`, `get()`, `list(category?)`, `update_status()`. Status: CONNECTED / DEGRADED / OFFLINE / REVOKED. |
| I-3.3.2 | CredentialStore | `bridge/ifl/registry/credential_store.py` — `store(adapter_id, oauth_token, refresh_token)`, `get()`, `refresh()`, `revoke()`. Encrypted at rest (AES256-GCM). Auto-refresh before expiry. |
| I-3.3.3 | AdapterHealthMonitor + TrustScore | `bridge/ifl/registry/health_monitor.py` — periodic `/ifl/health` ping (60s). 3 consecutive fails → DEGRADED, 5 → OFFLINE. `AdapterTrustScore`: rolling score 0.0-1.0, factors: response validity, latency accuracy, error rate, schema compliance. Below 0.5 → flag, below 0.2 → auto-suspend. |
| I-3.3.4 | Registry tests | Registration lifecycle, credential encryption, health monitoring, trust score calculation, auto-suspend. |

### E-3.4: IFL Adapter Dispatch (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-3.4.1 | DispatchRouter | `bridge/ifl/dispatch/router.py` — route based on `manifest.hosting_mode`: `company_hosted` → CompanyHostedDispatcher, `wasm_sandboxed` → WASMSandboxDispatcher. |
| I-3.4.2 | CompanyHostedDispatcher | `bridge/ifl/dispatch/company_hosted.py` — HTTP/2 + TLS 1.3 to company endpoint. Timeout from manifest `latency_hint * 2`. 1 retry on 5xx with exponential backoff. ConnectionPool per adapter (max 10, keep-alive 30s). |
| I-3.4.3 | WASMSandboxDispatcher | `bridge/ifl/dispatch/wasm_sandbox.py` — local WASM execution. Sandbox: 64MB mem, 5s CPU timeout, no network, no filesystem. Host imports: `ifl_host_send()`, `ifl_host_receive()`. `WASMModuleCache` (signature check on load, auto-update from Marketplace). |
| I-3.4.4 | Dispatch tests | Company-hosted round-trip, WASM sandbox isolation, timeout enforcement, retry logic, connection pooling. |

### E-3.5: IFL Event System (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-3.5.1 | Event Ingress (3 receivers) | `bridge/ifl/events/ingress.py` — `WebhookReceiver` (POST `/ifl/events/{adapter_id}`, verify adapter signature), `SSEStreamReceiver` (persistent connection per adapter, backpressure pause/resume), `PollReceiver` (configurable interval from manifest, dedup via event_id tracking). |
| I-3.5.2 | Event taxonomy + routing | `bridge/ifl/events/routing.py` — standard topic format `ifl.{category}.{adapter_id}.{event_type}`. Dual routing: → K0 command.submit (persist via P02) AND → K1 Event Bus (real-time: `k1.ifl.event.v1`). |
| I-3.5.3 | Event validation | Validate inbound events against declared manifest event schemas. Reject undeclared event topics. Adapter trust score adjustment on validation failures. |
| I-3.5.4 | Event system tests | Webhook receive, SSE stream, poll dedup, taxonomy routing, dual K0+K1 delivery, schema validation. |

### E-3.6: Fabric Auto-Registration (ManifestTranslator) (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-3.6.1 | ManifestTranslator | `k1/fabric/manifest_translator.py` — triggered by `k1.ifl.adapter.connected.v1`. For each capability in manifest: translate to Fabric tool contract (name: `tool.{type}.{category}.{adapter}.{action}`, provider_type: BRIDGE, safety_band_min from manifest, input/output schemas). |
| I-3.6.2 | Auto-register + unregister | `validate_contracts()` via Module Validator (12 rules FAB-12), then `register_in_fabric()` → Capability Registry + Embedding Index + emit `k1.fabric.capability.registered.v1`. Unregister on `k1.ifl.adapter.disconnected.v1`. |
| I-3.6.3 | Auto-registration tests | Manifest → tool contract translation, registry population, embedding index update, disconnect cleanup, schema validation failures. |

### E-3.7: IFL Connection Flow (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-3.7.1 | Connection orchestrator | `bridge/ifl/connection/flow.py` — 6-step flow: (1) User browses Marketplace → (2) OAuth authorization (company URL from manifest) → (3) Token exchange + store → (4) Manifest ingestion (pull → verify → validate → store) → (5) Auto-registration in Fabric → (6) Ready. |
| I-3.7.2 | Disconnection + revocation | Graceful disconnect (unregister from Fabric, revoke credentials). Revocation handling (FamilyOS CA revokes → adapter goes REVOKED status → all capabilities removed). |
| I-3.7.3 | Connection flow tests | Full 6-step happy path, OAuth failure, manifest verification failure, revocation mid-session. |

### E-3.8: IFL K0 Storage Integration (2 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-3.8.1 | K0 adapter storage schemas | `st_ifl_adapter_registry` (adapter_id, company, category, manifest_hash, status), `st_ifl_credentials` (encrypted tokens), `st_ifl_manifests` (manifest YAML + signature), `st_ifl_events` (event_id, adapter_id, topic, data JSONB). |
| I-3.8.2 | K0 persistence tests | Adapter registry CRUD, credential encryption at rest, manifest versioning, event persistence via P02. |

**MS-3 TOTALS: 8 epics, 29 issues**

---

## MS-4: Contracts & Module System

**Goal:** Runtime contract enforcement, module loading, capability/event/state registries wired.
**Gating:** All contract validators pass on real component YAML. Module scanner discovers all k1/modules/*.

### E-4.1: Contract Runtime Guards (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-4.1.1 | CapabilityGuard | Enforce capability contracts at invocation time. |
| I-4.1.2 | EventGuard | Enforce event schema on publish. |
| I-4.1.3 | StateGuard | Enforce SessionState section write contracts. |
| I-4.1.4 | WiringGuard | Enforce dependency graph at bootstrap. Validate all required ports are satisfied. |
| I-4.1.5 | Runtime guard tests | Guard enforcement, violation handling, performance overhead measurement. |

### E-4.2: Module Loader System (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-4.2.1 | ModuleScanner | `k1/kernel/loader.py` — discover `k1/modules/*/module.yaml`. Replace empty stub. |
| I-4.2.2 | HotReloadEngine | `k1/kernel/hot_reload.py` — file watcher for dev mode. Replace empty stub. |
| I-4.2.3 | Registry population | Wire ToolRegistry, PromptRegistry, AgentRegistry, SchemaRegistry from module scan results. |
| I-4.2.4 | Module system tests | Discovery, registration, hot reload, schema validation. |

### E-4.3: Capability Registry Wiring (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-4.3.1 | CapabilityRegistry implementation | Replace stub. Index capabilities from tool contracts + agent contracts + module manifests. |
| I-4.3.2 | EventRegistry implementation | Replace stub. Index events from event schemas. |
| I-4.3.3 | Registry tests | Registration, lookup, semantic search preparation, versioning. |

**MS-4 TOTALS: 3 epics, 12 issues**

---

## MS-5: Agent Lifecycle & Learning Loop

**Goal:** Dynamic agents can be spawned, managed, and terminated via Fabric. Learning loop (System 1 + System 2) operational.
**Gating:** Agent lifecycle FSM works. CuriosityAgent can spawn, ask user question, write answer to K0.

### E-5.1: Agent Lifecycle System (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-5.1.1 | BaseAgent + AgentLifecycleFSM | `k1/agents/base.py` — 6-state FSM: PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED. |
| I-5.1.2 | AgentFactory | `k1/agents/factory.py` — create from YAML templates. Integrates with Fabric spawn. |
| I-5.1.3 | AgentSupervisor | `k1/supervision/agent_supervisor.py` — health monitoring, crash detection <2s, blacklist (3 crashes/10min → 1hr ban). |
| I-5.1.4 | Agent lifecycle tests | FSM transitions, factory creation, supervisor monitoring, crash recovery. |

### E-5.2: Learning Loop — System 1: Gap Resolution (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-5.2.1 | SSE gap listener | `k1/learning/gap_listener.py` — listen for `curiosity.intent.v1` from K0 SSE. |
| I-5.2.2 | CuriosityAgent | `k1/learning/curiosity_agent.py` — LLM-powered question formulation, user interaction, gap writing. |
| I-5.2.3 | Gap resolution tests | SSE trigger → CuriosityAgent spawn → question → answer → K0 command. |

### E-5.3: Learning Loop — System 2: Model Refinement (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-5.3.1 | FeedbackSignalCollector | `k1/learning/feedback_collector.py` — correction, validation, reformulation, abandonment, hedging signals. |
| I-5.3.2 | DriftDetector + AdvisoryEmitter | `k1/learning/drift_detector.py` — embedding relevance decay → FeedbackEnvelope → K0. |
| I-5.3.3 | Model refinement tests | Signal collection, drift detection, advisory emission, K0 integration. |

**MS-5 TOTALS: 3 epics, 10 issues**

---

## MS-6: Multi-Device Sync

**Goal:** Bridge can discover, authenticate, and sync with other family devices on LAN.
**Gating:** Two devices can sync SessionState changes via E2EE CRDT merge.

### E-6.1: Device Discovery & Certificates (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-6.1.1 | DeviceDiscovery | `bridge/sync/discovery.py` — mDNS scan for family devices on LAN. |
| I-6.1.2 | CertificateManager | `bridge/sync/certificates.py` — ED25519 device certificates, signing, verification. |
| I-6.1.3 | Discovery + cert tests | mDNS mock, certificate generation, device authentication. |

### E-6.2: CRDT Merge & E2EE (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-6.2.1 | CRDTMerge | `bridge/sync/crdt.py` — Last-Writer-Wins register merge for SessionState. |
| I-6.2.2 | E2EEncryption | `bridge/sync/e2ee.py` — AES256-GCM encryption for sync payloads. |
| I-6.2.3 | CRDT + E2EE tests | Merge conflicts, encryption/decryption, tamper detection. |

### E-6.3: Sync Port & Protocol (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-6.3.1 | ISyncPort Protocol | `bridge/sync/sync_port.py` — define sync interface + impl connecting to K0 P07. |
| I-6.3.2 | P2P tunnel (Phase 2) | `bridge/sync/p2p.py` — internet sync when not on same LAN. |
| I-6.3.3 | Sync integration tests | LAN sync, offline queue, reconnect, CRDT merge verification. |

**MS-6 TOTALS: 3 epics, 9 issues**

---

## MS-7: Central Kernel Bootstrap

**Goal:** Kernel lives in `k1/kernel/`. Two-tier bootstrap calls ALL 8 factories + BridgeClient in correct order. No POC dependencies.
**Gating:** `KernelService.startup()` + `create_session()` produces fully-wired session with all 50 ports. All existing tests pass. Zero `poc.k1_poc` imports.

### E-7.1: Kernel Runtime & Config (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-7.1.1 | KernelRuntime dataclass | `k1/kernel/runtime.py` — typed container for all 8 component refs + Bridge + shared infra. |
| I-7.1.2 | KernelConfig | `k1/kernel/config.py` — canonical config (shared + session tiers). Superset of all component configs. |
| I-7.1.3 | SessionInstance + SessionState enum | `k1/kernel/session_instance.py` — per-session state: CREATING→ACTIVE→IDLE→DESTROYING→DESTROYED. |

### E-7.2: Tier 1 Bootstrap — Shared Components (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-7.2.1 | KernelService skeleton + startup() | `k1/kernel/kernel_service.py` — loads config, creates shared components in order. |
| I-7.2.2 | ModelHub + SharedFabric creation | Step S2-S3: `ModelHubFactory.create_standalone()`, `FabricFactory.create_with_ports(NullState)`. |
| I-7.2.3 | Bridge + Orchestrator + Planner | Step S4-S6: `BridgeClient.connect()`, `OrchestratorFactory.create_production()`, `PlannerFactory.create_production()`, Orch↔Planner cross-wire. |
| I-7.2.4 | CapabilityRegistry + ModuleLoader | Step S7: Wire registries, load modules, populate capability index. |

### E-7.3: Tier 2 Bootstrap — Per-Session Components (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-7.3.1 | create_session() | Step P1-P3: `BusFactory.create_local()`, `SessionStateFactory.create_with_ports()`, `FabricFactory.create_with_ports(real SSM)`. |
| I-7.3.2 | Concierge + MemoryWriter session creation | Step P4-P5: `ConciergeFactory.create_session(8 ports)`, `MemoryWriterFactory.create_session(5 ports)`. |
| I-7.3.3 | Household hydration + registration | Step P6-P7: `bridge_client.query()` hydration, `sessions[sid] = SessionInstance`. |

### E-7.4: Kernel Lifecycle (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-7.4.1 | shutdown() | Reverse-order teardown: Sessions → Planner → Orch → Fabric → ModelHub → Bridge. |
| I-7.4.2 | destroy_session() | Single session drain + cleanup. Reverse: Concierge → MW → Fabric → SS → Bus. |
| I-7.4.3 | CLI runner | `k1/kernel/runner.py` — `python -m k1.kernel.runner`. Replaces `k1/concierge/kernel/runner.py`. |

### E-7.5: Kernel Integration Tests (5 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-7.5.1 | Tier 1 startup tests | All shared components created. Model injection. Cross-wiring. |
| I-7.5.2 | Tier 2 session lifecycle tests | Create/destroy multiple sessions. Isolation. Duplicate rejection. |
| I-7.5.3 | Full 50-port wiring smoke test | Start → create session → verify ALL 50 ports satisfied → destroy → shutdown. |
| I-7.5.4 | Multi-session isolation test | 3 concurrent sessions. Per-session Bus isolation. Shared ModelHub. |
| I-7.5.5 | Regression against all component tests | Run ALL existing tests with kernel-created instances instead of standalone factories. |

### E-7.6: Migration & Cleanup (3 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-7.6.1 | Backward-compat shim | `k1/concierge/kernel/__init__.py` re-exports from `k1/kernel/`. |
| I-7.6.2 | Remove POC dependency | Eliminate `from poc.k1_poc.main import boot`. Bootstrap uses factories directly. |
| I-7.6.3 | Dead code removal | Delete `k1/kernel/{loader.py stubs, hot_reload.py stubs, registries/ stubs}`. Clean `k1/concierge/kernel/`. |

**MS-7 TOTALS: 6 epics, 21 issues**

---

## EXECUTION ORDER & DEPENDENCY GRAPH

```
MS-0 (Full Code Scan + Architecture Docs)     ←── START HERE (53 issues, code scan + docs + conformance)
│
├── E-0.1..E-0.8: All 50 per-port issues     ←── ALL PARALLEL (no cross-deps)
├── E-0.9: Factory audits (8 issues)          ←── PARALLEL with port issues
└── E-0.10: Cross-component bridge tests      ←── AFTER per-port conformance
│
├─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
MS-1 (Concierge + MW Completion)              MS-2 (Bridge K1↔K0)
│  ← AFTER MS-0                               │  ← CAN START PARALLEL WITH MS-0
│                                              │
├── E-1.1: ConciergeFactory (4)               ├── E-2.1: Port formalization (4)
├── E-1.2: Adapter hardening (3)              ├── E-2.2: Query port (3)
└── E-1.3: MemoryWriter (5)                   ├── E-2.3: SSE port (3)
                                               ├── E-2.4: Connector gateway (3)
                                               ├── E-2.5: Offline awareness (3)
                                               ├── E-2.6: Codecs (2)
                                               ├── E-2.7: BridgeClient facade (3)
                                               └── E-2.8: Household (3)
│                                              │
├─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
MS-3 (IFL)                                    MS-4 (Contracts & Modules)
│  ← AFTER MS-2 E-2.4 (Connector Gateway)    │  ← AFTER MS-0
│                                              │
├── E-3.1: IFL gateway (3)                    ├── E-4.1: Runtime guards (5)
├── E-3.2: IFL core (3)                       ├── E-4.2: Module loader (4)
├── E-3.3: IFL schemas (2)                    └── E-4.3: Registry wiring (3)
├── E-3.4: Phase 1 adapters (4)
└── E-3.5: Phase 2 adapters (5)
│                                              │
├─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
MS-5 (Agents & Learning)                      MS-6 (Multi-Device Sync)
│  ← AFTER MS-4 (needs registries)            │  ← AFTER MS-2 (needs bridge)
│                                              │
├── E-5.1: Agent lifecycle (4)                ├── E-6.1: Discovery + certs (3)
├── E-5.2: Gap resolution (3)                ├── E-6.2: CRDT + E2EE (3)
└── E-5.3: Model refinement (3)              └── E-6.3: Sync port (3)
│                                              │
└──────────────────────────────┬───────────────┘
                               │
                          MS-7 (Central Kernel Bootstrap)
                          │  ← AFTER MS-1 + MS-2 + MS-4
                          │
                          ├── E-7.1: Runtime & config (3)
                          ├── E-7.2: Tier 1 bootstrap (4)
                          ├── E-7.3: Tier 2 bootstrap (3)
                          ├── E-7.4: Lifecycle (3)
                          ├── E-7.5: Integration tests (5)
                          └── E-7.6: Migration & cleanup (3)
```

### Critical Path

```
MS-0 (Code Scan + Docs, 53 issues)
  → MS-1 (Concierge+MW, 12 issues)
    → MS-7 (Kernel Bootstrap, 21 issues)

Parallel tracks:
  MS-0 → MS-4 (Contracts, 12 issues) → MS-5 (Agents, 10 issues) → MS-7
  MS-2 (Bridge, 33 issues) → MS-3 (IFL, 29 issues) → MS-7
  MS-2 → MS-6 (Sync, 9 issues)
```

---

## FULL PORT WIRING MATRIX — ALL 50 PORTS

### Bus (3 ports)

| Port | Protocol | What Kernel Injects | Notes |
|------|----------|-------------------|-------|
| `IBus` | Self | Per-session, `BusFactory.create_local(TracingMiddleware)` | Bus IS the port |
| `IMailbox` | Created | `router.register("actor_name", config)` | Front + Back mailboxes |
| `IMailboxRouter` | Created | `BusFactory.create_mailbox_router()` | WFQ routing |

### SessionState (5 ports)

| Port | Protocol | What Kernel Injects | Notes |
|------|----------|-------------------|-------|
| `IStoragePort` | ABC | `SQLiteStorageAdapter(db_path)` | LOCAL COLD |
| `IWriterPort` | ABC | `DirectWriterAdapter(manager, guard)` | POST-INJECT |
| `ILifecyclePort` | ABC | `StandaloneLifecycle(manager)` | POST-INJECT |
| `IEventPort` | ABC | `SessionBusAdapter(bus)` | Per-session Bus |
| `IK0SyncPort` | ABC | `NullSyncPort()` | V1 = null |

### Fabric (6 ports)

| Port | Protocol | Shared Injection | Per-Session Injection |
|------|----------|------------------|-----------------------|
| `ISessionStateReader` | Protocol | `TestSSReaderAdapter()` (Null) | `SSReaderAdapter(manager, sid)` |
| `IEventPort` | Protocol | `LocalEventAdapter(capture=True)` | `FabricBusAdapter(bus)` |
| `IBridgePort` | Protocol | `TestBridgeAdapter()` / real | Same as shared |
| `IDeltaBusPort` | Protocol | `TestDeltaBusAdapter()` | `FabricBusAdapter(bus)` |
| `IModelGatewayPort` | Protocol | `TestModelGatewayAdapter()` / real | Same as shared |
| `IPromptSystemPort` | Protocol | `TestPromptSystemAdapter()` / real | Same as shared |

### ModelHub (7 ports)

| Port | Protocol | What Kernel Injects | Notes |
|------|----------|-------------------|-------|
| `IModelHubPort` | Protocol | Self | Shared, stateless |
| `IEventPort` | Protocol | `EventBusAdapter(bus)` | Observability |
| `IHealthPort` | Protocol | `HealthReportAdapter()` | HEALTHY/DEGRADED/UNHEALTHY |
| `IConfigPort` | Protocol | `ConfigAdapter(config)` | Budgets, timeouts |
| `ICredentialPort` | Protocol | `CredentialStoreAdapter()` | API keys |
| `IStateReadPort` | Protocol | `SessionStateReadAdapter()` | Read-only (MH-01) |
| `IMetricsPort` | Protocol | `PrometheusAdapter()` | Fire-and-forget |

### Orchestrator (9 ports)

| Port | Protocol | What Kernel Injects | Notes |
|------|----------|-------------------|-------|
| `IMailboxPort` | Protocol | `MailboxAdapter(max_depth=100)` | WFQ priority |
| `IFabricGatewayPort` | Protocol | `FabricGatewayAdapter(shared_fabric)` | Through shared Fabric |
| `IPlannerPort` | Protocol | `MockPlanner → PlannerAdapter(mailbox, cb)` | Hot-swap |
| `IStateReadPort` | Protocol | `StateReadAdapter(reader)` | Read-only |
| `IBridgeWritePort` | Protocol | `BridgeWriteAdapter(bridge)` / Mock | Fire-and-forget K0 |
| `IDeltaEmitPort` | Protocol | `DeltaEmitAdapter(event, delta)` | Observability |
| `IEventSubscriptionPort` | Protocol | `EventSubscriptionAdapter(event)` | Bus subscription |
| `IWorkflowStoragePort` | Protocol | `WorkflowStorageAdapter(sqlite)` | Persistence |
| `IAdminPort` | Protocol | `AdminHttpAdapter(service, config)` | POST-INJECT |

### Planner (7 ports)

| Port | Protocol | What Kernel Injects | Notes |
|------|----------|-------------------|-------|
| `IMailboxPort` | Protocol | `MailboxAdapter(max_depth=5)` | MPSC+FIFO |
| `ILLMPort` | Protocol | `LLMGatewayAdapter(model_hub)` | Wraps ModelHub |
| `IFabricRetrievalPort` | Protocol | `FabricRetrievalAdapter(fabric)` | Discovery only |
| `IStateReadPort` | Protocol | `SnapshotStateReadAdapter()` | Read-only snapshot |
| `IBridgePort` | Protocol | `BridgeAdapter(bridge)` / TestBridge | Recall + persist |
| `IDeltaEmitPort` | Protocol | `DeltaBusAdapter(bus)` | Fire-and-forget |
| `IEventPort` | Protocol | `EventBusAdapter(bus)` | Bidirectional |

### Concierge (8 ports)

| Port | Protocol | What Kernel Injects | Notes |
|------|----------|-------------------|-------|
| `IInputPort` | Protocol | `BusInputAdapter(bus)` | User → FSM |
| `IOutputPort` | Protocol | `BusOutputAdapter(bus)` | FSM → SSE/WS |
| `IClassificationPort` | Protocol | `UltraBERTv4Adapter()` / Mock | Pre-LLM classification |
| `ILLMPort` | Protocol | `HubLLMAdapter(model_hub)` | Via ModelHub |
| `IStatePort` | Protocol | `SSMStateAdapter(ss)` | R+W via MutationGuard |
| `IDispatchPort` | Protocol | `FabricDispatchAdapter(fabric, orch)` | Tier routing |
| `IDeltaPort` | Protocol | `LocalDeltaAdapter(bus)` | Bus IS delta |
| `IMemoryPort` | Protocol | `RecallMemoryAdapter(recall_fn)` | K0 recall |

### MemoryWriter (5 ports)

| Port | Protocol | What Kernel Injects | Notes |
|------|----------|-------------------|-------|
| `ISessionReadPort` | Protocol | `SessionReadAdapter(ss_manager)` | Lock-free <1ms |
| `IBridgeCommandPort` | Protocol | `BridgeCommandAdapter(bridge)` | Fire-and-forget K0 (MW-03) |
| `IEventSubscriptionPort` | Protocol | `EventSubAdapter(bus)` | Subscribe turn.complete.v1 |
| `IModelHubPort` | Protocol | `ModelHubAdapter(hub)` | 2000 token budget (MW-06) |
| `IHealthPort` | Protocol | `HealthAdapter()` | Readiness/liveness |

---

## PLAN TOTALS

| Milestone | Epics | Issues | Focus |
|-----------|-------|--------|-------|
| MS-0: Full Code Scan + Architecture Docs | 11 | 53 | 9 ARCHITECTURE.md + K1_COMPONENT_MATRIX.md + conformance tests |
| MS-1: Concierge + MemoryWriter | 3 | 12 | Factory completion for 2 components |
| MS-2: Bridge K1↔K0 | 10 | 33 | Full bridge connectivity (5 ports + security core + offline + codecs) |
| MS-3: IFL Universal Connector Protocol | 8 | 29 | Manifest-driven adapter runtime + auto-registration |
| MS-4: Contracts & Modules | 3 | 12 | Runtime enforcement + module system |
| MS-5: Agents & Learning | 3 | 10 | Dynamic agents + learning loops |
| MS-6: Multi-Device Sync | 3 | 9 | Family mesh sync |
| MS-7: Central Kernel Bootstrap | 6 | 21 | THE kernel wiring everything |
| **TOTAL** | **47** | **179** | **End-to-end production K1** |

---

## KEY DESIGN DECISIONS PRESERVED

| Decision | Description |
|----------|-------------|
| SIM-D-04 | Component sharing: Shared (1/process) vs Per-session (N) |
| SIM-D-09 | ConciergeSession lifecycle wrapper |
| SIM-D-39 | Two-Tier Bootstrap (Tier 1 shared, Tier 2 per-session) |
| SIM-D-02 | SessionInstance per-session state container |
| D-1..D-16 | All whiteboard design decisions |
| ORCH-02 | No LLM in Orchestrator (rule-based only) |
| MW-01..MW-11 | MemoryWriter 11 invariants |
| MW-BOOT | MemoryWriter 3-layer bootstrap: Adapters (translate) → Factory (wire) → FabricRegistration (orchestrate). FabricRegistration resolves HealthAdapter circular dependency via forward-ref lambda. See E-1.3 gotcha note. |
| ADR-0017 | Single Writer (Concierge), Multi-Reader for SessionState |
| ADR-0018 | Memory limits: HOT 48KB + WARM 48KB = 96KB hard boundary |

---

## HOW TO USE THIS PLAN

1. **Pick a milestone** — MS-0 is the starting point (no deps)
2. **Pick an epic within it** — E-0.1..E-0.8 are all per-port, run in parallel
3. **Pick an issue** — each issue is a self-contained unit of work
4. **Execute** — code discovery + verification + tests per issue
5. **Mark complete** — move to next issue
6. **Milestone gate** — all issues in milestone must pass before moving to dependent milestones
7. **Parallel tracks** — MS-2 (Bridge) can start while MS-0 is in progress; MS-4 (Contracts) can start after MS-0

**The kernel working end-to-end = MS-7 completed with all dependencies satisfied.**
