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
| 7 | Concierge | 8 | ❌ NONE | 8+5 null | 8 | ⚠️ NO FACTORY |
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

## 8 MILESTONES → 47 EPICS → 179 ISSUES

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

## MS-1: Concierge + MemoryWriter Hexagonal Completion

**Goal:** Both remaining components get factories, session wrappers, and full adapter coverage.
**Gating:** `ConciergeFactory.create_session()` and `MemoryWriterFactory.create_session()` return working instances.

### E-1.1: ConciergeFactory + Session (4 issues)

| Issue | Title | Deliverable |
|-------|-------|-------------|
| I-1.1.1 | ConciergeFactory skeleton | `k1/concierge/factory.py` — `create_session(8 ports) → ConciergeSession`. Wires FSM, dispatchers, experience, delta, HITL. Pattern matches OrchestratorFactory. |
| I-1.1.2 | ConciergeSession lifecycle | `k1/concierge/session.py` — `start()`, `stop()`, `inject()`. Consumer loop, teardown, flush. |
| I-1.1.3 | ConciergeConfig extraction | `k1/concierge/config/concierge.py` — frozen dataclass. `from_legacy(KernelConfig)`. `with_overrides()` for tests. |
| I-1.1.4 | ConciergeFactory tests | Unit tests: factory wiring, session start/stop, port injection, config override. |

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
