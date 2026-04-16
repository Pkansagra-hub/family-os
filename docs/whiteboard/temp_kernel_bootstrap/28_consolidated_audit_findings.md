# Consolidated Audit Findings — All K1 Components

> Generated: 2026-04-14 · Sources: Docs 10–27 (Bus, SessionState, Fabric, ModelHub, Orchestrator, Planner, Concierge, MemoryWriter, Bridge, Kernel)

---

## Table of Contents

1. [CRITICAL Findings](#1-critical-findings)
2. [HIGH Findings](#2-high-findings)
3. [MEDIUM Findings](#3-medium-findings)
4. [LOW Findings](#4-low-findings)
5. [INFO Findings](#5-info-findings)
6. [Summary Statistics](#6-summary-statistics)

---

## 1. CRITICAL Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| C-1 | Planner / PlanStep | `safety_band_min` lost on event bus serialization | `PlanStep.to_dict()` omits `safety_band_min` (field 14). When `CommittedPlan` is serialized to event bus (`plan.ready.v1`) then deserialized by Orchestrator, `safety_band_min` is lost. DAGExecutor safety gate sees `None` instead of Planner's intended constraint. Fix: add to `to_dict()` in `k1/orchestrator/types.py`. | 15_planner_api, 15_xref |
| C-2 | Planner / PlannerStateAdapter | `reader=None` breaks Planner state reads | `PlannerStateAdapter(reader=None, session_id="__shared__")` — ToolCallRouter `state_read` tool always fails. Plans generated without session context. Fix: wire real `ISessionStateReader` in S6 or share Orch's state adapter. | 15_planner_api, 15_xref |

---

## 2. HIGH Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| H-1 | SessionState / SSM | SSM does NOT satisfy Concierge IStatePort | `SSM.get_snapshot()` returns `SessionSnapshot` dataclass, but Concierge `IStatePort.get_snapshot()` expects `dict[str, Any]`. Wiring doc 08 incorrectly claimed "SSM IS IStatePort — no wrapper needed" — `SSMStateAdapter` IS required. | 11_ss_audit |
| H-2 | SessionState / Adapters | 5 of 10 adapters are stubs (NotImplementedError) | `FabricLifecycleAdapter`, `DeltaBusAdapter`, `ConciergeWriterAdapter`, `BridgeStorageAdapter`, `BridgeSyncAdapter` all raise `NotImplementedError`. These represent the production wiring path for MS-2+. | 11_ss_audit |
| H-3 | Fabric / Providers | WORKFLOW and CONCIERGE provider deps not injected | `_create_workflow` needs `workflow_registry`, `capability_lookup`, `orchestrator`; `_create_concierge` needs `concierge_router`. None in `ProviderFactory` constructor — would raise `ValueError`. | 12_fabric_audit |
| H-4 | ModelHub / MemoryWriter | Duplicate IModelHubPort class name | Two `IModelHubPort` protocols with same name but different interfaces: ModelHub's has `execute()`, MemoryWriter's has `chat()`. Wrong import = silent protocol mismatch. | 13_modelhub_audit |
| H-5 | Orchestrator / PlannerAdapter | No Planner hot-swap mechanism | `_mailbox` set once in `__init__`, stored in `__slots__`. No setter/swap method. `__slots__` prevents monkey-patching. Phase 2 blocker. | 14_orch_audit |
| H-6 | Orchestrator / AdminHttpAdapter | isinstance bug in list_circuit_breakers() | Checks `isinstance` on `CircuitBreakerState` against a `CircuitBreaker` object — always returns empty dict. Code fix needed. | 14_orch_audit |
| H-7 | Orchestrator / IStateReadPort | MockStateReadAdapter wired in production | `MockStateReadAdapter()` is NEVER REPLACED — always returns empty. Safety band reads empty, `get_snapshot()` empty. No session context for planning. | 15_orch_api |
| H-8 | Orchestrator / TaskEnvelope | MEDIUM tier caps capabilities at max 2 | `TaskEnvelope` validation: MEDIUM tier requires non-empty capabilities list with max 2 entries. Could silently reject valid requests. | 14_orch_audit |
| H-9 | Planner / SessionStateReadAdapter | State read always fails in S6 wiring | `reader=None` placeholder means ToolCallRouter `state_read` tool always fails. Duplicate of C-2 — listed at HIGH for doc 15_planner_audit source. | 15_planner_audit |

---

## 3. MEDIUM Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| M-1 | Bus / Concurrency | Bus fully synchronous — no asyncio integration | Uses `threading.Lock/RLock/Condition` throughout. Async kernel needs `asyncio.to_thread()` wrapping. Design decision needed for MS-2. | 10_bus_audit |
| M-2 | Bus / TimingChain | create_local_ordered forced Python-only | Rust backend cannot be used with ordered delivery. `BusFactory.create_local_ordered()` defaults to `backend="python"`. | 10_bus_audit |
| M-3 | Bus / Architecture | Sync bus + async kernel bridging undefined | How to bridge synchronous bus with async kernel is undefined. Impacts performance and correctness. | 10_bus_audit |
| M-4 | SessionState / SSMStateAdapter | Wrapper required but underdocumented | `SSMStateAdapter` exists (~47 LOC) converting `SessionSnapshot → dict[str, Any]`, but wiring plan incorrectly omits it. | 11_ss_audit |
| M-5 | SessionState / DeltaBusAdapter | Stub blocks bus-SSM event bridging | Will replace `LocalEventAdapter` to bridge SSM events to Bus. Currently not functional. Blocks MS-2+. | 11_ss_audit |
| M-6 | SessionState / ConciergeWriterAdapter | Stub blocks FSM-routed mutations | Will route mutations through Concierge FSM, replacing `DirectWriterAdapter`. Currently not functional. | 11_ss_audit |
| M-7 | SessionState / FabricLifecycleAdapter | Stub blocks coordinated lifecycle | Will replace `StandaloneLifecycle` for Fabric-coordinated lifecycle. No signals protocol defined. | 11_ss_audit |
| M-8 | SessionState / Concurrency | SSM synchronous — same async bridging issue | Uses `threading.RLock` for writes, lock-free reads. Same sync-async bridge issue as Bus. | 11_ss_audit |
| M-9 | Fabric / Factory | Port params typed as `Any` in create_with_ports() | All 6 port args as `Any` instead of Protocol types. Defeats type-checker enforcement. | 12_fabric_audit |
| M-10 | Fabric / Ports | No formal IEmbeddingPort Protocol | Used with `_StubEmbeddingPort` but no formal Protocol definition. Implicit structural contract. | 12_fabric_audit |
| M-11 | Fabric + SessionState | ABC vs Protocol split — architectural inconsistency | SessionState ports use ABC (nominal), Fabric ports use Protocol (structural). Inconsistent DI pattern. | 12_fabric_audit |
| M-12 | Fabric / NullStateReader | NOT wired into any factory method | `NullSessionStateReaderAdapter` exists but unused by `create_standalone()` or `create_for_testing()`. No `create_shared()` method. | 12_fabric_audit |
| M-13 | Fabric / IBridgePort | Mixed sync/async in IBridgePort | 3 async + 2 sync methods. Mixed patterns complicate adapter implementation. | 12_fabric_audit |
| M-14 | Fabric / Wiring | WORKFLOW/CONCIERGE provider runtime injection undefined | How dependencies get injected at runtime for these providers is not defined. | 12_fabric_audit |
| M-15 | ModelHub / Adapters | 6 adapters are dev/test only (no production backend) | `SessionStateReadAdapter` (in-memory dict), `PrometheusAdapter` (in-memory counters), `EventBusAdapter` (in-memory pub/sub), `CredentialStoreAdapter` (env vars only), `ConfigAdapter` (in-memory dict). Not connected to real systems. | 13_modelhub_audit |
| M-16 | ModelHub / Factory | 6 secondary ports not wired in standalone | `create_standalone()` only wires CredentialStore + Health. Event, State, Metrics, Config ports unconnected. | 13_modelhub_audit |
| M-17 | ModelHub / BusEnvelopeDeserializer | Event loop ownership unclear | Needs event loop — open question: who owns it? Impacts async lifecycle. | 13_modelhub_audit |
| M-18 | ModelHub / MemoryWriter | Rename MemoryWriter's IModelHubPort recommended | Rename to `IMemoryWriterLLMPort` to eliminate same-name ambiguity. MS-3 task. | 13_modelhub_audit |
| M-19 | Orchestrator / IBridgeWritePort | Contains read methods — name violation | `read_wal()` and `list_wal_ids()` violate "write" name contract. Should rename to `IBridgePersistencePort`. | 14_orch_audit |
| M-20 | Orchestrator / IWorkflowStoragePort | save_run() and get_runs() use bare types | `save_run(manifest: object)`, `get_runs() → list` — no type safety (circular import dodge). | 14_orch_audit |
| M-21 | Orchestrator / IAdminPort | No mock/test adapter | Production adapter exists but no test double for integration tests. | 14_orch_audit |
| M-22 | Orchestrator / AdminHttpAdapter | Accesses 6 private OrchestratorService fields | Known boundary violation — "god adapter" accessing internals. | 14_orch_audit |
| M-23 | Orchestrator / ErrorRouter | HIGH→MEDIUM degradation not implemented | Classifies planner failures as `FALLBACK` but service doesn't act on it. | 15_orch_api |
| M-24 | Orchestrator / Shutdown | Force-compensate on shutdown is V1 no-op | Running DAGs may leave uncompensated side effects on crash/restart. | 15_orch_api |
| M-25 | Orchestrator / Shutdown | Persist triggers on shutdown is V1 no-op | Trigger state may be lost on restart. | 15_orch_api |
| M-26 | Orchestrator / Crash Recovery | Crash recovery depends on offline WAL | `crash_recovery()` calls `bridge_port.read_wal()` but `BridgeClientShim.read()` returns `None` → no-ops. | 15_orch_api |
| M-27 | Orchestrator / Workflow Save | Workflow save depends on offline WAL | `_save_workflow()` calls `bridge_port.read_wal()` → returns `None` → workflow save fails. | 15_orch_api |
| M-28 | Orchestrator / DeltaEmitAdapter | Kernel must inject TWO Fabric bus instances | Requires both `IEventPort` and `IDeltaBusPort`. Kernel wiring must provide two separate bus instances or verify one satisfies both. | 14_orch_audit |
| M-29 | Orchestrator / ExecutionMonitor | HIL override threshold undocumented | Post-wave guard triggers HIL override for "significant waves" (>3 steps or >5s) but thresholds not configurable. | 15_orch_api |
| M-30 | Orchestrator / MicroReplan | Max 1 micro-replan per DAG | `config.max_micro_replans=1` — complex failures may remain unrecovered. | 15_orch_api |
| M-31 | Orchestrator / ConstraintResolver | Auto-alternative max 3 cycles | Could be insufficient for complex plans. | 15_orch_api |
| M-32 | Orchestrator / BridgeClientShim | read() returns None (offline) | WAL reads fail → crash recovery no-ops, workflow save fails. | 15_orch_api |
| M-33 | Planner / PlanStep | `to_dict()` omits `safety_band_min` | Round-trip serialization loses field 14. Orchestrator's DAGExecutor may never see safety constraint. | 15_planner_api |
| M-34 | Planner / Adapters | No circuit breaker on internal LLM/Fabric/Bridge calls | Orchestrator protects itself from Planner (CB on IPlannerPort), but Planner has no CB protecting from LLM failures. | 15_planner_api, 15_xref |
| M-35 | Planner / PlannerStateAdapter | `session_id="__shared__"` prevents per-session state | When reader becomes real, all instances share one context. Per-request session_id not propagated. | 15_planner_api, 15_xref |
| M-36 | Planner / PlanRequest | No `to_dict()`/`from_dict()` prevents event bus usage | Cannot use event bus path — only direct call works. | 15_xref |
| M-37 | Planner / SessionStateReadAdapter | Sync reader call inside `async def` blocks event loop | `read_sections()` calls reader synchronously despite being `async def`. May block if reader is slow. | 15_planner_audit |
| M-38 | Planner / All Adapters | Constructor params typed `Any` not Protocol types | Type safety deferred to runtime for all 7 production adapters. | 15_planner_audit |
| M-39 | Planner / PlannerAgent | `start()` not called by factory | Factory creates agent but doesn't call `start()`. Caller must remember — easy to forget. | 15_planner_audit |
| M-40 | ModelHub / PrometheusAdapter | Integration timing unresolved | When to integrate real `prometheus_client` — MS-3 or later? | 13_modelhub_audit |

---

## 4. LOW Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| L-1 | Bus / TopicValidation | Soft validation only — unknown topics never dropped | Warns but never drops. Typo'd topics flow through silently. | 10_bus_audit |
| L-2 | Bus / Architecture | Shared bus vs per-session bus — undecided | Architecture decision pending for MS-2. | 10_bus_audit |
| L-3 | Bus / FabricBusAdapter | Scope unclear — shared or per-session | Affects memory and isolation. | 10_bus_audit |
| L-4 | Bus / MailboxRouter | Per-session scope unclear | Actor lifecycle management affected. | 10_bus_audit |
| L-5 | SessionState / Factory | Depends on poc.k1_poc.config.get_config() | Cross-dependency on POC config system. | 11_ss_audit |
| L-6 | SessionState / DeltaBusAdapter | Bus reference undefined | Which bus (shared vs per-session) not decided. | 11_ss_audit |
| L-7 | SessionState / ConciergeWriterAdapter | Potential circular dependency | Needs Concierge FSM reference — may create circular dependency. | 11_ss_audit |
| L-8 | SessionState / FabricLifecycleAdapter | Signals undefined | What signals Fabric sends for lifecycle transitions not defined. | 11_ss_audit |
| L-9 | SessionState / BridgeStorage | BridgeStorageAdapter stub — blocked on Bridge audit | Cannot sync to K0 cloud. | 11_ss_audit |
| L-10 | SessionState / BridgeSync | BridgeSyncAdapter stub — blocked on Bridge audit | Cannot sync to K0. | 11_ss_audit |
| L-11 | Fabric / NullStateReader | Location mismatch | Lives in `k1/concierge/adapters/` but implements Fabric's `ISessionStateReader`. | 12_fabric_audit |
| L-12 | Fabric / Adapters | Lazy bus imports in FA-A2 and FA-A3 | `Envelope`/`Priority` imported inside method bodies. Minor per-call overhead. | 12_fabric_audit |
| L-13 | Fabric / IModelGatewayPort | create_handle sync but returns async handle | Mixed sync/async in same port. | 12_fabric_audit |
| L-14 | Fabric / ModelInfo | capabilities uses List[str] not List[ModelCapability] | Loses type safety. | 12_fabric_audit |
| L-15 | Fabric / Architecture | Shared vs per-session adapter reuse undefined | Resource efficiency vs isolation undecided. | 12_fabric_audit |
| L-16 | Fabric / Architecture | EventPort + DeltaBus bus assignment undefined | Shared vs per-session bus for Fabric not decided. | 12_fabric_audit |
| L-17 | Fabric / Architecture | Missing create_shared() factory method | No factory convenience for shared Fabric scenario. | 12_fabric_audit |
| L-18 | ModelHub / EventBusAdapter | No unsubscribe() method | Stores subscriptions without removal support. | 13_modelhub_audit |
| L-19 | ModelHub / ConfigAdapter | get() ignores env overrides | Docstring says it checks env overrides but only reads in-memory dict. | 13_modelhub_audit |
| L-20 | Orchestrator / ports/__init__.py | Stale docstring says "8 ports", actually 9 | IAdminPort added later. | 14_orch_audit |
| L-21 | Orchestrator / PlannerAdapter | planner_mailbox typed as Any | Despite `IPlannerMailbox` Protocol existing in same file. | 14_orch_audit |
| L-22 | Orchestrator / TestMailboxAdapter | Missing reset() method | Must re-instantiate between tests. | 14_orch_audit |
| L-23 | Orchestrator / MockFabricAdapter | Unused cancel_log | Dead code. | 14_orch_audit |
| L-24 | Orchestrator / adapters/__init__.py | Stale docstring says "16 adapters", actually 17 | Count off by one. | 14_orch_audit |
| L-25 | Orchestrator / WorkflowStorageAdapter | Adapter-over-adapter wrapping pattern | Extra indirection, functional but unnecessary layer. | 14_orch_audit |
| L-26 | Orchestrator / StepRunner | Schema retry budget is only 1 | Output schema validation failures get only 1 retry before HARD_STOP. | 15_orch_api |
| L-27 | Orchestrator / PlanRequest | Field naming inconsistency | `PlanRequest.context` vs `snapshot` in API mapping doc. | 15_orch_api |
| L-28 | Planner / HILCoordinator | HIL handlers are V1 stubs | Planner cannot pause for user input yet. | 15_planner_api |
| L-29 | Planner / PlannerStateAdapter | `session_id="__shared__"` hardcoded | Per-request session_id not propagated. | 15_planner_api |
| L-30 | Planner / MicroReplanRequest | `to_dict()` exists but no `from_dict()` | Cannot deserialize micro-replan from event bus. | 15_planner_api, 15_xref |
| L-31 | Planner / PlanRequest | No `to_dict()`/`from_dict()` | Cannot serialize plan requests via bus. Currently passed as Python objects. | 15_planner_api |
| L-32 | Planner / LLMGatewayAdapter | Defines local `ILLMRequestBus` Protocol | Could be shared type, but isolation prevents circular imports. Minor duplication. | 15_planner_audit |
| L-33 | Planner / MailboxAdapter | `set_pipeline_controller()` post-construction injection | Two-phase init — risk of use-before-set. | 15_planner_audit |
| L-34 | Planner / Event Subscriptions | request/cancel events unused by Orchestrator | Planner subscribes to `plan.request.v1`/`plan.cancel.v1` but Orch uses direct call. Defense-in-depth. | 15_xref |
| L-35 | ModelHub / Sync-Async | Bridging not resolved for kernel wiring | Multiple ports have mixed sync/async signatures. | 13_modelhub_audit |

---

## ROUND 2 — Docs 16–20

### Additional CRITICAL Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| C-3 | Cross-component / FabricGatewayAdapter | `compensation_capability` AttributeError | `_contract_to_entry()` assumes `CapabilityContract` has `compensation_capability` field. May raise `AttributeError` if contract lacks it. ConstraintResolver compensation lookup fails. Fix: `getattr(contract, 'compensation_capability', None)`. | 17_fab_orch_planner_xref |
| C-4 | Cross-component / Shared Fabric | Shared Fabric has no session context | `NullSessionStateReaderAdapter` in shared Fabric → ContextBuilder builds empty context. PolicyEngine Affective/Cognitive scoring always 0. Provider decisions context-blind. | 17_fab_orch_planner_xref |
| C-5 | Cross-component / IEmbeddingPort | IEmbeddingPort not wired — Planner discovery broken | `IEmbeddingPort` not wired in kernel S4 for shared Fabric. `FabricRetrieval.discover_capabilities()` cannot embed queries. Planner's `fabric_search` tool non-functional. | 17_fab_orch_planner_xref |
| C-6 | Cross-component / Session State | Systemic session-state blindness (compound gap) | Three independent gaps: (1) Orch uses `MockStateReadAdapter()` — empty, (2) Planner uses `PlannerStateAdapter(reader=None)` — empty, (3) Fabric uses `NullSessionStateReaderAdapter` — empty. Entire Orch→Planner→Fabric pipeline operates without session awareness. | 17_fab_orch_planner_xref |

### Additional HIGH Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| H-10 | Concierge | Two parallel runtime types (~200 LOC duplicated) | `KernelRuntime` (mutable dataclass, 24+ fields) in bootstrap.py vs `ConciergeRuntime` (regular class, 19 params) in session.py. ~200 LOC duplicated. Must converge for MS-2. | 16_concierge_audit |
| H-11 | Concierge / bootstrap.py | Hard dependency on POC layer | `start_kernel()` calls `poc.k1_poc.main.boot()` — violates clean architecture boundary. | 16_concierge_audit |
| H-12 | Bridge | 4 of 5 ports have NO concrete implementation | `IKernelQueryPort`, `IKernelSSEPort`, `IKernelObsPort`, `IConnectorGatewayPort` are protocol-only. K1 cannot recall from K0, receive SSE, or send telemetry. | 18_bridge_audit |
| H-13 | Bridge | No online BridgeClient exists — system permanently offline | `SinkBridgeClient` IS the production client. No implementation actually connects to K0. All queries empty, SSE empty, IFL raises `NotImplementedError`. | 18_bridge_audit |
| H-14 | k1/kernel | Two "kernel" packages — dead vs real | `k1/kernel/` (100% stubs, 69 LOC, dead code) vs `k1/concierge/kernel/` (real composition root, ~1201 LOC). Real kernel inside Concierge. | 19_kernel_package_audit |
| H-15 | k1/kernel | `k1/kernel/` is 100% dead code | Nothing imports from `k1.kernel`. 69 LOC stubs misleading developers. | 19_kernel_package_audit |
| H-16 | k1/concierge/kernel/bootstrap | bootstrap.py imports `poc.k1_poc.main.boot()` | Production composition root depends on POC layer. Must eliminate for MS-2. | 19_kernel_package_audit |
| H-17 | Orchestrator / StateAdapter | MockStateReadAdapter wired in production — safety gate bypassed | `MockStateReadAdapter()` never replaced. `_check_safety_band()` always sees `safety_band=None` → defaults GREEN → safety gate ALWAYS PASSES. | 19_ss_xref |
| H-18 | Orchestrator+Planner | Systemic session-state blindness in planning pipeline | Context-blind planning: Orchestrator and Planner operate on empty state. Fabric has full context → asymmetry. | 19_ss_xref |
| H-19 | SessionState / Emergency | `emergency.activated` event has no subscriber | Critical for backpressure: SSM emergency mode should pause planning + throttle writes. No component subscribes. | 19_ss_xref |

### Additional MEDIUM Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| M-41 | Concierge / KernelConfig | No validation on tool_tier | Accepts any string. runner.py offers `MEDIUM`/`CRISIS` which don't match `ConciergeConfig`'s `{"LOW","MED","HIGH"}`. | 16_concierge_audit |
| M-42 | Concierge / KernelRuntime | Undeclared fields via setattr | `weave_batcher`, `weave_policy`, `activity_tracker` set via `setattr` but not in dataclass. | 16_concierge_audit |
| M-43 | Concierge / Runtimes | 24+ fields typed as `Any` | Both runtimes defeat static analysis entirely. | 16_concierge_audit |
| M-44 | Concierge / PortBundle | IFabricPort excluded from PortBundle | 8 ports in bundle, 9 in ports.py. `IFabricPort` passed separately as `fabric_port: Any`. | 16_concierge_audit |
| M-45 | Fabric / NullStateReader | Shared Fabric has no session context (FAB-GAP-01) | `NullSessionStateReaderAdapter` → PolicyEngine always 0. ContextBuilder empty. | 16_fabric_api |
| M-46 | Fabric / IEmbeddingPort | Not wired in kernel S4 (FAB-GAP-03) | RetrievalEngine cannot embed queries. Falls back to empty. | 16_fabric_api |
| M-47 | Fabric / WorkflowProvider | No IOrchestrator wired (FAB-GAP-06) | Cannot execute workflows. Guard rejects all workflow requests. Deferred M3. | 16_fabric_api |
| M-48 | Fabric / ConciergeProvider | IConciergeRouter not wired (FAB-GAP-07) | Cannot route state requests. Deferred to Concierge factory integration. | 16_fabric_api |
| M-49 | Fabric / PlanStep | Type collision across modules (FAB-GAP-08) | Fabric `PlanStep` (6 fields) vs Orchestrator `PlanStep` (14 fields). Same name, different types. | 16_fabric_api, 17_xref |
| M-50 | Cross-component | RegistryEntry lossy mapping — 26→6 fields | `_contract_to_entry()` drops 20 fields. ConstraintResolver cannot evaluate `required_inputs`, `output`, `cost_per_call`. | 17_fab_orch_planner_xref |
| M-51 | Cross-component | Fabric dispatcher concurrency conflict | Fabric max 10 concurrent vs Orch Semaphore(10). Combined load from Orch+Concierge can trigger shedding. | 17_fab_orch_planner_xref |
| M-52 | Cross-component | Planner FabricRetrievalAdapter 50ms timeout too aggressive | Discovery returns empty if pipeline exceeds 50ms. Should increase to 200ms. | 17_fab_orch_planner_xref |
| M-53 | MemoryWriter / FakeSessionReadPort | Missing `list_sections()` and `snapshot_all()` | Test fake incomplete — `AttributeError` on full contract use. | 17_mw_audit |
| M-54 | Bridge / SinkBridgeClient | `emit_obs` does NOT queue despite docstring | NORMAL/HIGH obs logged then dropped, not queued. Data loss. | 18_bridge_audit |
| M-55 | Bridge / Type Mismatch | `submit_command_batch` takes `list[dict]` but port takes `list[CommandEnvelope]` | Facade vs port type mismatch. | 18_bridge_audit |
| M-56 | SessionState / Adapters | 5 production stubs (confirmed again from SS API mapping) | Same 5 stubs confirmed in multiple audit docs. | 18_ss_api |
| M-57 | SessionState / K0SyncPort | Not wired (NullSyncPort always offline) | No cloud backup/restore. Reconstruction fallback dead code. | 18_ss_api |
| M-58 | SessionState / Events | SSM events emitted but no consumer subscribes | Events for mutation/eviction/emergency emitted but unused. | 19_ss_xref |
| M-59 | k1/concierge/kernel/chat_repl | Mutates runtime.model post-boot | Boots test_mode=True, swaps model after. Race condition window. | 19_kernel_audit |
| M-60 | k1/concierge/kernel/runner | tool_tier CLI/config mismatch | runner.py `MEDIUM`/`CRISIS` vs ConciergeConfig `LOW`/`MED`/`HIGH`. | 19_kernel_audit |
| M-61 | ModelHub / BusEnvelopeDeserializer | Only CHAT and TOOL_CALL typed payload builders | Other 13 capability types fall through to raw dict — no validation. | 19_mh_services_audit |
| M-62 | Concierge / HIGH Tier | HIGH tier is interface-only | `route_task_sync` creates TaskEnvelope but full Orch+Planner pipeline not implemented. | 20_concierge_api |
| M-63 | Concierge / Types | POC type divergence: `name` vs `capability_name` | `CapabilityRequest.name` vs Fabric `capability_name`. Bridge adapter converts. Maintenance burden. | 20_concierge_api |
| M-64 | Concierge / Factory | FabricDispatchAdapter not wired by factory | `IDispatchPort` adapter available but factory Step 14 wires differently. | 20_concierge_api |
| M-65 | Concierge / Deferred Ports | 5 HIGH-tier ports interface-only | `IPlannerPort`, `IWorkflowPort`, `IConnectorPort`, `IConstraintPort`, `ISagaPort` — no backend. | 20_concierge_api |
| M-66 | Orchestrator | No explicit session lifecycle handler | Doesn't know when sessions start/stop. | 19_ss_xref |
| M-67 | Planner | No explicit session lifecycle handler | No cleanup on session destruction. | 19_ss_xref |
| M-68 | SessionState / Orch | Orch wired to MockStateReadAdapter (confirmed in SS xref) | Safety band checks and snapshots always empty. | 19_ss_xref |

### Additional LOW Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| L-36 | Concierge | CO-T7 `create_test_bus()` returns real LocalBus, not test double | No call capture, no scripting, no assertion API. | 16_concierge_audit |
| L-37 | Concierge | 3 adapter files are pure re-exports | CO-A3, CO-A4, CO-A7 are thin shims, not real adapters. | 16_concierge_audit |
| L-38 | Concierge | 20+ deferred imports in factory.py | Heavy in-function imports for circular dep avoidance. Fragile. | 16_concierge_audit |
| L-39 | Concierge | `factory.py.bak` left in source tree | Dead backup file. | 16_concierge_audit |
| L-40 | Concierge | Placeholder packages empty | `affective/`, `empathy/`, `rhythm/`, `types/` have empty `__init__.py`. | 16_concierge_audit |
| L-41 | Concierge | `chat_repl.py` mutates runtime.model directly | Breaks encapsulation. | 16_concierge_audit |
| L-42 | Concierge | Config loader triple-indirection | `k1.concierge.config` → `poc.k1_poc.config` → `loader`. Unnecessary. | 16_concierge_audit |
| L-43 | Fabric | EmbeddingIndex rebuild O(N) | Full FAISS rebuild on every add/remove. OK for <10K but problematic with hot-registration. | 16_fabric_api |
| L-44 | Fabric | `capability_types/` directory empty | Vestigial. Constants in `types.py` sufficient. | 16_fabric_api |
| L-45 | Fabric | `module_registry/` directory empty | Registry logic in `core/`. Organizational noise. | 16_fabric_api |
| L-46 | Cross-component | Dead event handler for step.execute.v1 | Fabric wired for topic but Orch never publishes. | 17_xref |
| L-47 | Cross-component | Dead event handler for discovery.request.v1 | Fabric wired but Planner never publishes. | 17_xref |
| L-48 | Cross-component | Compensation capability registration dependency | Compensation capability must exist in Fabric registry at module load. | 17_xref |
| L-49 | MemoryWriter | HealthAdapter.last_extraction_ms hardcoded 0.0 | Placeholder — always shows 0ms. | 17_mw_audit |
| L-50 | MemoryWriter | No null adapters — all 5 ports mandatory | No graceful degradation path. | 17_mw_audit |
| L-51 | MemoryWriter | 4 of 5 adapters type deps as `Any` | `isinstance` checks compensate but no static analysis. | 17_mw_audit |
| L-52 | MemoryWriter | EventSubscriptionAdapter._sync_wrapper swallows errors | Silently drops events if no running asyncio loop. | 17_mw_audit |
| L-53 | MemoryWriter | No explicit Protocol inheritance on adapters | Structural subtyping valid but less visible. | 17_mw_audit |
| L-54 | MemoryWriter | No reset()/clear() on Fake test doubles | Must create new instances per test. | 17_mw_audit |
| L-55 | MemoryWriter | FakeModelHubPort returns tokens=0 | Per-field token counts incorrect in tests. | 17_mw_audit |
| L-56 | Bridge / SigningBackend | Not @runtime_checkable | Inconsistent with codebase convention. isinstance() checks fail. | 18_bridge_audit |
| L-57 | Bridge | `__status__ = "planning"` stale | Substantial implementation exists but status says "planning". | 18_bridge_audit |
| L-58 | Bridge | `codecs/` directory empty | No serialization layer despite architecture references. | 18_bridge_audit |
| L-59 | Bridge | `sync/__init__.py` exports 6 None symbols | `CertificateManager`, `CRDTMerge`, etc. all resolve to `None`. | 18_bridge_audit |
| L-60 | Bridge | StubBridgeClient in production client.py | Test double in prod module. | 18_bridge_audit |
| L-61 | Bridge | KernelCommandPort no Protocol conformance declaration | Structural subtyping but inconsistent with convention. | 18_bridge_audit |
| L-62 | Bridge | `adapters/` directory empty | Zero adapter files. | 18_bridge_audit |
| L-63 | Bridge | `connector/` directory empty | Deferred to MS-3 (IFL). | 18_bridge_audit |
| L-64 | SessionState | WARM sections sum 52KB but tier limit 48KB | 4KB overrun. Eviction may be imprecise. | 18_ss_api |
| L-65 | SessionState | narrative_active in demotion list but no WARM target | Wastes priority slot. | 18_ss_api |
| L-66 | SessionState | _eviction_in_progress is boolean, not lock | Potential race under extreme concurrent triggers. | 18_ss_api |
| L-67 | SessionState | Events via adapter only — raw manager bypasses emission | Silent observability gap in non-adapter paths. | 18_ss_api |
| L-68 | SessionState / HOT tier | Docstring says 48KB but actual is 52KB | Documentation drift. | 18_ss_api |
| L-69 | k1/kernel / chat_repl | Inconsistent CLI parsing | Manual sys.argv vs argparse. | 19_kernel_audit |
| L-70 | k1/kernel / registries | No type hints on any parameter | Every parameter untyped. | 19_kernel_audit |
| L-71 | k1/kernel / tool_registry | Comment says "versions" but none exist | Misleading comment. | 19_kernel_audit |
| L-72 | ModelHub / EventBusAdapter | No unsubscribe() (confirmed again) | Resource leak for long-lived processes. | 19_mh_services_audit |
| L-73 | ModelHub / ConfigAdapter | get() ignores env overrides (confirmed) | Docstring vs implementation mismatch. | 19_mh_services_audit |
| L-74 | ModelHub / CredentialStoreAdapter | refresh_key() identical to get_key() | No actual rotation mechanism. | 19_mh_services_audit |
| L-75 | ModelHub / SessionStateProdAdapter | manager typed as Any | Loses type-checking at boundary. | 19_mh_services_audit |
| L-76 | SessionState / Types | No schema validation at consumer boundary | Consumers trust dict shape — no validation. | 19_ss_xref |
| L-77 | Concierge / ToolContext | Uses `Any` extensively | 4 fields typed as `Any`. | 20_concierge_api |
| L-78 | Concierge / Runtime | ConciergeRuntime uses `Any` for optional ports | 4 more fields typed `Any`. | 20_concierge_api |
| L-79 | Concierge / Tools | submit_result event indirect via ToolResult.data stash | By design but non-obvious. | 20_concierge_api |

---

## ROUND 3 — Docs 21–27

### Additional HIGH Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| H-20 | Concierge ↔ Orchestrator ↔ Planner | HIGH tier not wired end-to-end | `route_task_sync(HIGH)` creates correct TaskEnvelope but full Orchestrator+Planner pipeline is interface-only. No code path exercises HIGH tier. | 21_concierge_xref |
| H-21 | Concierge ↔ Orchestrator | Type bridge needed for HIGH tier | POC `TaskEnvelope`/`AggregatedResult` must bridge to K1 `OrchestratorRequest`/`OrchestratorResult`. No bridge adapter exists. | 21_concierge_xref |
| H-22 | Concierge ↔ Orchestrator | Deferred orchestrator ports are interface-only | `IPlannerPort`, `IWorkflowPort`, `IConnectorPort`, `IConstraintPort`, `ISagaPort` — all interface-only, blocking HIGH-tier. | 21_concierge_xref |
| H-23 | ModelHub / Concierge | POC bridge bypasses full ModelHub pipeline | Concierge uses `ModelHubPOCBridge(GeminiConciergeAdapter)` not `ModelHubFactory`. Budget, caching, circuit breakers, rate limiting, fallback, audit, metrics ALL bypassed. | 22_mh_api, 23_mh_xref |
| H-24 | Concierge / MemoryWriter | `recall_memory` not wired — read path returns `[]` | `memory=None` in kernel PortBundle means `_null_recall` always returns empty list. Write path works but read path dead — system writes memories it can never retrieve. | 24_mw_api, 25_mw_xref |
| H-25 | MemoryWriter / HealthAdapter | `get_started` lambda always returns `False` | `HealthAdapter` initialized with `get_started=lambda: False` in kernel service.py P5. Health check never reflects actual MW running state. Masks operational failures. | 25_mw_xref |

### Additional MEDIUM Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| M-69 | Concierge (internal) | FabricDispatchAdapter unused by factory (confirmed in xref) | `PortBundle.dispatch: IDispatchPort` defined and implemented but factory Step 14 wires OrchestratorStub directly. IDispatchPort from PortBundle unused. | 21_concierge_xref |
| M-70 | Orchestrator ↔ SessionState | Orch SS read is stub — MockStateReadAdapter (confirmed in xref) | When HIGH-tier wires, a real SS read adapter is needed. | 21_concierge_xref |
| M-71 | Planner ↔ SessionState | Planner SS read partial — None placeholder (confirmed in xref) | `PlannerStateAdapter(reader=None)` placeholder; real reader not injected. | 21_concierge_xref |
| M-72 | Concierge ↔ Fabric | POC type divergence: name vs capability_name (confirmed in xref) | `CapabilityRequest.name` vs `capability_name`. Fragile translation layer in `_FabricGatewayAdapter`. | 21_concierge_xref |
| M-73 | ModelHub | Stream validation is stub (MH-10) | Stream validation invariant not actively validating streaming chunks. | 22_mh_api |
| M-74 | ModelHub | Manifest hot-reload is stub (MH-17) | Requires filesystem watcher implementation. Stubbed out. | 22_mh_api |
| M-75 | ModelHub | BusEnvelopeDeserializer not wired in kernel bootstrap | Exists but not wired — direct injection used instead. Production bus-driven path dead. | 22_mh_api, 23_mh_xref |
| M-76 | Concierge → ModelHub | Production bus path not wired | Intended path (Concierge → bus `k1.model_hub.execute.v1` → ModelHub 9-step pipeline) not implemented. Only direct injection (POC). | 23_mh_xref |
| M-77 | ModelHub → Kernel | Full ModelHubFactory not used in kernel bootstrap | Kernel bootstrap creates `ModelHubPOCBridge` or `TestModelHubBridge`, never full `ModelHubFactory.create_standalone()`. Only `chat_repl.py --model-hub` exercises it. | 23_mh_xref |
| M-78 | Orchestrator → Planner → ModelHub | Orchestrator has no direct ModelHub dependency | HIGH-tier pipeline (Orch→Planner→LLM) entirely unwired. | 23_mh_xref |
| M-79 | Concierge → ModelHub | POC path has zero budget/cache/CB/RL protections | 10 production pipeline features bypassed in POC Gemini path. | 23_mh_xref |
| M-80 | MemoryWriter / Pipeline | Accumulation Gate (Stage 1B) missing | Architecture documents Stage 1B with 6 triggers for batching. Currently each turn dispatched individually — loses multi-turn context windows. | 24_mw_api, 25_mw_xref |
| M-81 | MemoryWriter / PlaceResolver | PlaceResolver initialized with empty entity list | `MemoryWriterFactory` passes `PlaceResolver([])`. All place resolution returns `None` until entities populated at session start. | 24_mw_api, 25_mw_xref |
| M-82 | MemoryWriter / HealthAdapter | `last_extraction_ms` hardcoded to `0.0` (confirmed) | Not wired to actual extraction latency. Health observability degraded. | 24_mw_api |
| M-83 | Bus / RustMailboxAdapter | `receive()` keyword-only mismatch breaks `IMailbox` protocol | `RustMailboxAdapter.receive(*, timeout_ms)` is keyword-only but `IMailbox` declares positional. Callers using `receive(100)` get `TypeError`. | 26_bus_api, 27_bus_xref |
| M-84 | Bus / Topic Naming | `turn.complete.v1` lacks `k1.` namespace prefix | Inconsistent with every other topic. Should be `k1.session.turn.complete.v1`. | 27_bus_xref |
| M-85 | Bus / ModelHub Timing | `k1.model_hub` has no timing rule — RELAXED default | `k1.model_hub.execute.v1` used for bus RPC, may deliver out-of-order breaking request/response correlation. Needs STRICT rule. | 27_bus_xref |
| M-86 | SessionState / SessionBusAdapter | Double-nested topic naming | `sessionstate.mutation.requested` mapped to `k1.session.sessionstate.mutation.requested` — double-nested prefix. Should flatten to `k1.sessionstate.mutation.requested.v1`. | 27_bus_xref |

### Additional LOW Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| L-80 | Concierge (internal) | ToolContext typed as Any (confirmed in xref) | Optional port references in ToolContext and ConciergeRuntime are `Any` instead of protocol imports. | 21_concierge_xref |
| L-81 | ModelHub | EventBusAdapter is in-memory only | Not connected to K1 event bus. All 11 event topics stay local to ModelHub. | 22_mh_api |
| L-82 | ModelHub | CredentialStoreAdapter uses env-var lookup | `MH_KEY_<PROVIDER_ID>` env lookups; production target is Vault/keychain. | 22_mh_api |
| L-83 | ModelHub plugins | Anthropic plugin requires max_tokens explicitly | Inconsistency with other providers that use defaults. | 22_mh_api |
| L-84 | ModelHub plugins | OpenAI reasoning models need special handling | o3/o4-mini/o3-mini/o1 get `reasoning_effort`, no temperature, `developer` role for system prompt. | 22_mh_api |
| L-85 | Concierge → Orchestrator | Bus topics currently internal to Concierge | All `k1.orchestration.*` topics internal. When full K1 Orchestrator wired, cross-component contract enforcement needed. | 21_concierge_xref |
| L-86 | MemoryWriter / Docs | `ARCHITECTURE.md` stale — claims 37% implementation | Actual state much more complete. Documentation drift misleads contributors. | 24_mw_api |
| L-87 | Bus / RustBusAdapter | `drain()` returns cumulative — behavioral drift from LocalBus | Rust `drain()` returns cumulative captured without clearing. LocalBus clears. Inconsistent. | 26_bus_api |
| L-88 | Bus / impl | Inconsistent re-export layering | `LocalMailbox`, `LocalMailboxRouter`, Rust adapters not re-exported from `impl/__init__.py`. | 26_bus_api |
| L-89 | Bus / Timing | `k1.mw` prefix has no timing rule — RELAXED fallback | MemoryWriter telemetry topics have no explicit rule. Likely OK but should confirm. | 27_bus_xref |

### Additional INFO Findings

| # | Component | Title | Description | Source |
|---|-----------|-------|-------------|--------|
| I-1 | Concierge → Planner | No direct Concierge→Planner integration exists | Intended path is Concierge→Orch→Planner. Entire chain interface-only in POC — expected future work. | 21_concierge_xref |
| I-2 | ModelHub | 18 LLM consumers with per-consumer budgets (arch diagram) | Actual enforcement via global BudgetEnforcer ($5/day), not per-consumer. | 23_mh_xref |
| I-3 | ModelHub | 37 test files, 982 functions, zero unittest.mock imports | Comprehensive coverage. All 18 invariants have contract tests. | 22_mh_api |
| I-4 | ModelHub | 34 tracing phases defined | 27 pipeline + 5 lifecycle + 2 circuit breaker phases. Structured JSON + secret redaction. | 22_mh_api |
| I-5 | Concierge | 45 bus topics (35 STRICT + 10 RELAXED) | Large bus surface area. Central nervous system for async. | 21_concierge_xref |
| I-6 | Concierge | POC Fabric has 40 capabilities internally | `k1/concierge/fabric/` with 40 capabilities (7 demo, 31 family, 2 web). | 21_concierge_xref |
| I-7 | Concierge | 19 total adapters (8 prod + 3 bridge + 8 test) | Full adapter map at Concierge boundary. | 21_concierge_xref |
| I-8 | ModelHub | Budget: $5/day, $100/month defaults | Three-tier decision (ALLOW / ALLOW_DEGRADED / REJECT). 80% warning, 95% degraded thresholds. | 22_mh_api |
| I-9 | ModelHub | Supervision/Arbiter uses REALTIME priority | Safety/policy blocks pipeline with REALTIME priority (10s timeout). Highest urgency consumer. | 23_mh_xref |
| I-10 | MemoryWriter / K0 | UltraBERT validation is K0-only (MW-11) — by design | MW sends raw atoms; K0 P02 validates. Correct per architecture. | 25_mw_xref |
| I-11 | MemoryWriter / Kernel | MW created directly in kernel P5, not via Fabric | `MemoryWriterFabricRegistration.create_for_session()` exists but kernel creates directly. Fabric path unused. | 25_mw_xref |
| I-12 | Planner / MemoryWriter | Planner turns don't trigger MemoryWriter | Planner doesn't emit `turn.complete.v1`. Planning-phase turns never memory-extracted. | 25_mw_xref |
| I-13 | Orchestrator / MemoryWriter | Orchestrator has no direct MW dependency | Purely indirect — orch manages actors whose turns trigger MW via Concierge. | 25_mw_xref |
| I-14 | MemoryWriter / SessionState | MW reads 13 of 15 SS sections; skips telemetry, artifacts_warm | Read-only access, <1ms P99. Two phantom sections handled gracefully. | 24_mw_api |
| I-15 | MemoryWriter / ModelHub | MW owns its own IModelHubPort (distinct from K1's) | Anti-corruption layer. MW `chat()` vs K1 `execute(HubRequest)`. | 25_mw_xref |
| I-16 | Bus / async_bridge | Async handler errors fire-and-forget | `_wrap_async_handler` Future never awaited — async handler exceptions silently lost. | 26_bus_api |
| I-17 | Bus / config | `load_bus_config()` never raises — may mask config errors | Robust for prod but dev YAML typos silently swallowed. | 26_bus_api |
| I-18 | Bus / dead letter | `k1.internal.dead_letter.v1` topic defined but no publisher | Dead-letter constant exists but no middleware or publisher. Dead code / unimplemented. | 27_bus_xref |
| I-19 | Bus / RustBusAdapter | Rust adapter ignores middleware/timing chain | `TimingChain` and `MiddlewareChain` stored but NOT wired into Rust dispatch. Middleware bypassed with Rust backend. | 26_bus_api |

---

## 5. Summary Statistics

### By Severity

| Severity | Round 1 | Round 2 | Round 3 | Total |
|----------|---------|---------|---------|-------|
| CRITICAL | 2 | 4 | 0 | **6** |
| HIGH | 9 | 10 | 6 | **25** |
| MEDIUM | 40 | 28 | 18 | **86** |
| LOW | 35 | 44 | 10 | **89** |
| INFO | 0 | 0 | 19 | **19** |
| **Total** | **86** | **86** | **53** | **225** |

### By Component

| Component | CRIT | HIGH | MED | LOW | INFO | Total |
|-----------|------|------|-----|-----|------|-------|
| Orchestrator | 0 | 2 | 8 | 4 | 0 | 14 |
| Planner | 0 | 1 | 6 | 3 | 1 | 11 |
| Fabric | 1 | 0 | 10 | 5 | 0 | 16 |
| SessionState | 0 | 2 | 8 | 8 | 0 | 18 |
| Bus | 0 | 0 | 6 | 5 | 4 | 15 |
| Concierge | 0 | 5 | 10 | 10 | 5 | 30 |
| ModelHub | 0 | 1 | 8 | 7 | 5 | 21 |
| MemoryWriter | 0 | 2 | 6 | 5 | 4 | 17 |
| Bridge | 0 | 2 | 3 | 9 | 0 | 14 |
| Kernel (k1/kernel) | 0 | 3 | 3 | 3 | 0 | 9 |
| Cross-component | 5 | 7 | 18 | 10 | 0 | 40 |
| **Total** | **6** | **25** | **86** | **69** | **19** | **225** |

### Top 5 Compound Gaps (Cross-Component)

1. **Systemic session-state blindness** — Orch (MockStateReadAdapter), Planner (reader=None), Fabric (NullSessionStateReaderAdapter) all operate without session context. (C-4, C-6, H-17, H-18, M-56, M-66-68, M-70-71)
2. **HIGH-tier pipeline entirely unwired** — Concierge→Orch→Planner→Fabric chain is interface-only. 5 deferred ports have no backend. (H-20, H-21, H-22, M-65, M-78)
3. **ModelHub POC bypass** — Production 9-step pipeline with all protections not exercised. Budget, caching, circuit breakers, rate limiting all bypassed. (H-23, M-76, M-77, M-79)
4. **Bridge permanently offline** — 4 of 5 ports unimplemented, no online client. K1 cannot communicate with K0. (H-12, H-13, L-56-63)
5. **Memory recall loop broken** — MemoryWriter writes succeed but `recall_memory` not wired — reads always return empty. (H-24)

---

*Generated: Consolidated from 27 audit documents (docs 10–27) in `docs/whiteboard/temp_kernel_bootstrap/`*
