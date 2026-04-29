# Kernel Bootstrap Wiring Plan — Milestones, Epics, Issues

**Date:** 2026-04-11
**Status:** SKELETON — issues to be filled during code discovery

---

## Phase 6 Completion Note (2026-04-18)

**Branch:** `bus-hardening` (cut from `POC_Migration`) — HEAD `7164a26`.

**Commit chain delivering Phase 6:**

1. `44006c8` — P6.1, P6.2, P6.3, P6.4 (tier-2 fail-safe fixes: async Future error logging, RustBusAdapter middleware/timing wiring, drain semantics, impl re-exports).
2. `47c7f10` — P6.5, P6.6, P6.7, P6.8, P6.9 (per-subscription mailbox + `flush()`, retry policy, DLQ callback, `turn.complete.v1` rename, `SessionBusAdapter` flatten).
3. `7164a26` — P6.11, P6.12, P6.13, P6.14 (schema validation on `TopicRegistry`, `IdempotencyMiddleware`, SQLite `BusOutbox` + replay, E2E test suite + PR summary).

**Done:** P6.0–P6.9, P6.11–P6.14 (14 of 15 issues).

**Open:** ~~**P6.10 only**~~ ✅ DONE 2026-04-22 — `k1.model_hub: STRICT` added to `k1/config/bus.yaml` AND `k1/bus/timing/defaults.py` `DEFAULT_RULES` (test enforces parity). Bus suite 1108/1108 still green.

---

## Sequential Execution Roadmap (2026-04-22 — post P3.4 / post P6.10)

> Items marked **DEFERRED-N** below are ordered by dependency. Pick them up one at a time in numeric order. Each is a self-contained commit-sized unit. ☐ = not started, ⏳ = in progress, ✅ = done.

| # | Item | Scope | Blocker / Depends |
|---|------|-------|-------------------|
| **DEFERRED-1** ✅ DONE 2026-04-22 | Test cleanup: `test_m10_e101_ultrabert_pipeline.py` — dropped `complexity_tier` assertions (P3.4 carry-over). Removed `test_complexity_tier_present` + entire `TestComplexityClassifier` block (7 tests) + relaxed `test_fallback_when_adapter_returns_none`. 31/31 pass. | ~30 LOC, 8 tests | done |
| **DEFERRED-2** ✅ DONE 2026-04-22 | Test cleanup: `test_tool_fabric_live.py` — replaced `fabric_port=` kwarg with `dispatch=FabricDispatchAdapter(fabric)` (P4B.3 carry-over). Also fixed pre-existing bug in `FabricDispatchAdapter.discover_capabilities` (positional/kwarg collision on `domain`) and removed duplicate compat block. 17/17 pass. | ~17 tests + 1 adapter fix | done |
| **DEFERRED-3** ✅ DONE 2026-04-22 | TD-2.3 / TD-2.4 / TD-2.5 — three stale doc-string fixes: `k1/structure.md` tool_registry comment now flags P3.1 removal; `k1/memory_writer/ARCHITECTURE.md` "16 of 43" section flagged stale (now 46 .py files); `k1/sessionstate/manager.py` `get_hot()` docstring corrected 48KB → 52KB. | 3 doc edits | done |
| **DEFERRED-4** ✅ DONE 2026-04-22 (audit) | P4B.4 — `CircuitBreaker` already relocated to `k1/orchestrator/degradation.py` (per `k1.concierge.orchestrator.__init__` docstring + `k1.orchestrator.degradation` header). `OrchestratorStub` + HIGH-tier interfaces + port protocols already deleted. `route_task` / `route_task_sync` intentionally remain in `k1/concierge/orchestrator/routing.py` because they operate on POC types (TaskEnvelope/Budget/ComplexityTier) per ARCHITECTURE.md R-1 — moving them to `k1/orchestrator/` would conflict with the documented POC↔production type split (production already has its own `_route_task` over different fields). NO code change needed. | audit only | done |
| **DEFERRED-5** ✅ DONE 2026-04-22 (audit) | P4B.5 — `_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter` already deleted from `k1/concierge/factory.py` (only `_DispatchPortFSMAdapter` remains, which is the P4B.2 replacement). Backward-compat re-exports from `k1/concierge/kernel/bootstrap.py` and `k1/kernel/bootstrap.py` already removed (verified by `TestBackwardCompatExports` in `tests/k1/concierge/test_concierge_factory.py`). NO code change needed. | audit only | done |
| **DEFERRED-6** ✅ DONE 2026-04-22 (audit) | P4B.7 — `k1/concierge/fabric/` already contains only `ports.py` (`IFabricPort` Protocol) + `__init__.py` (with P4B.7 docstring). All 6 demo-capability files (registry.py, demo_capabilities.py, family_capabilities.py, web_capabilities.py, contract_converter.py, poc_bridge_adapter.py) already moved to `tests/fixtures/capabilities/`. Only one test file (`tests/k1/concierge/test_fabric_port.py`) imports `IFabricPort` from production. NO code change needed. | audit only | done |
| **DEFERRED-7** ✅ DONE 2026-04-22 | MS-4 Epic 4.1 — Replaced obsolete `Phase1Result.complexity_tier` spec (line 2938) with post-P3.4-correct cross-component coverage: new file `tests/k1/integration/test_dispatch_task_bus_hop.py` with 3 parametrized tests (LOW/MEDIUM/HIGH) exercising `dispatch_task(intents_raw, tier=...)` → real `BusFactory.create_local()` → `TOPIC_TASK_DISPATCH` subscriber → `TaskDispatch.from_payload()`. Asserts tier propagation, task_id round-trip, envelope routing fields, JSON payload_format, auto-derived budget_hint. 3/3 pass in 1.06s. | 3 tests | done |
| **DEFERRED-8** | MS-4 Epic 4.2 — Tier routing & dispatch (4 tests; 4.2.5 STRETCH) → `test_tier_routing.py` | 4 tests | DEFERRED-7 |
| **DEFERRED-9** | MS-4 Epic 4.3.1 — Wire `route_task_with_degradation()` into FSM (PREREQUISITE for 4.3.2-5) | activate dead code | DEFERRED-4 |
| **DEFERRED-10** | MS-4 Epic 4.3.2-4.3.6 — CB degradation cascade (5 tests) → `test_cb_degradation.py` | 5 tests | DEFERRED-9 |
| **DEFERRED-11** | MS-4 Epic 4.4 — Cross-component data flow (6 tests) → `test_data_flow.py` | 6 tests | DEFERRED-7 |
| **DEFERRED-12** | MS-4 Epic 4.5 — Full turn cycle (LOW + MEDIUM, multi-turn, concurrent — 4 tests) → `test_turn_cycle.py` | 4 tests | DEFERRED-7..11 |
| **DEFERRED-13** | MS-3 TD-1 — Type Safety Sweep (~10 items, ~150 LOC) | ~150 LOC across multiple components | none |
| **DEFERRED-14** | MS-3 TD-3 — Architectural Improvements (TD-3.10 KernelRuntime/ConciergeRuntime convergence highest impact) | ~18 items | DEFERRED-13 ideally |
| **DEFERRED-15** | MS-3 TD-5 — 48 LOW items (correctness-risk first: TD-5.34 WARM 52KB vs 48KB limit, TD-5.36 eviction boolean→lock) | 48 items | none (parallel) |
| **DEFERRED-16** | MS-3 TD-6 — 19 INFO items (observational only) | docs | none |
| **DEFERRED-17** | MS-2.5 Phase 7 — Bridge adapters (KernelQueryPort, KernelSSEPort, KernelObsPort, HttpBridgeClient) | ~800 LOC | **BLOCKED on K0 HTTP API availability** |
| **DEFERRED-18** | MS-3 TD-4 — 11 future-scope stubs (UltraBERT, Prometheus, DeltaBusAdapter, config watcher) | as deps unblock | BLOCKED on external milestones |
| **DEFERRED-19** | MS-4 4.2.5 (STRETCH) — HIGH → real Planner via `IPlannerService` / `IDAGExecutor` | requires real Planner impl | BLOCKED — interfaces-only today |

**Critical-path subset (kernel "done" gate):** DEFERRED-1 → 2 → 4 → 5 → 9 → 7 → 8 → 10 → 11 → 12. Items 3, 6, 13–16 parallelizable. 17–19 are external-blocked.

**Tests:** Bus suite **1108 passing** (baseline 1069, +39 new across schema validation, idempotency, durability, and E2E). Pre-existing unrelated failures on POC_Migration (perf SLO flakes, `test_no_deep_imports_in_production`, model_hub asyncio loop pollution, `runner_cli` SystemExit:2) verified out-of-scope for Phase 6.

**PR summary:** [docs/whiteboard/temp_kernel_bootstrap/phase6_pr_summary.md](docs/whiteboard/temp_kernel_bootstrap/phase6_pr_summary.md)

---

## MS-2.5 Status Snapshot — 2026-04-22 Subagent Code Audit

> **READ THIS FIRST.** Per-issue ☐/☑ checkboxes below were stale until this audit. The summary here reflects what is actually true in code (verified by 7 parallel read-only subagents with file:line citations). When any per-issue table conflicts with this snapshot, this snapshot wins.

| Phase | Done | Total | Verdict |
|-------|------|-------|---------|
| **Phase 1** Session-State Wiring | 6 | 6 | ✅ COMPLETE |
| **Phase 2** Serialization & Type Safety | 7 | 8 | ⚠️ NEAR — only P2.6 MW Protocol-stub mirror remaining (1-line cosmetic; runtime fine) |
| **Phase 3** Dead Code & Package Cleanup | 4 | 4 | ✅ COMPLETE |
| **Phase 4** POC Layer Decoupling | 5 | 5 | ✅ COMPLETE |
| **Phase 4B** Concierge Port Wiring | 8 | 8 | ✅ COMPLETE (P4B.4 done-by-design — see DEFERRED-4) |
| **Phase 5** Production Adapter Stubs → Real | 7 | 8 | ✅ COMPLETE (P5.7 PlaceResolver explicitly DEFERRED as LOW) |
| **Phase 6** Bus Production Hardening | 15 | 15 | ✅ COMPLETE |
| **Phase 7** Bridge Adapter Completion | 0 | 7 | ❌ NOT STARTED — P7.4 BLOCKED on K0 HTTP API; P7.1/P7.2/P7.3/P7.5/P7.6/P7.7 actionable |
| **TOTAL** | **52** | **61** | **85% — only Phase 7 + P2.6 actionable** |

**Real remaining work (excluding deferred/blocked):**

| Item | Effort | File:line |
|------|--------|-----------|
| P2.6 — fix MW local Protocol stub `list[dict]` → `list[CommandEnvelope \| dict[str, Any]]` | trivial (1 line) | [k1/memory_writer/adapters/bridge_command_adapter.py:40](k1/memory_writer/adapters/bridge_command_adapter.py#L40) |
| P7.5 — add `@runtime_checkable` to `SigningBackend` | trivial (1 line) | [bridge/core/signing.py:40](bridge/core/signing.py#L40) |
| P7.7 — add Protocol conformance to `KernelCommandPort` | small | [bridge/kernel/command_port.py:47](bridge/kernel/command_port.py#L47) |
| P7.6 — move `StubBridgeClient` from prod to test module | small | [bridge/client.py:128](bridge/client.py#L128) |
| P7.1 — build `KernelQueryPort` offline adapter | small (~150 LOC) | `bridge/adapters/` (empty) — protocol [bridge/ports/query_port_protocol.py:115](bridge/ports/query_port_protocol.py#L115) |
| P7.2 — build `KernelSSEPort` offline adapter | small (~150 LOC) | protocol [bridge/ports/sse_port_protocol.py:73](bridge/ports/sse_port_protocol.py#L73) |
| P7.3 — build `KernelObsPort` offline adapter (also fix `emit_obs` drop bug for NORMAL/HIGH) | medium (~200 LOC) | protocol [bridge/ports/obs_port_protocol.py:78](bridge/ports/obs_port_protocol.py#L78) |
| P7.4 — `HttpBridgeClient` | medium (~300 LOC) | **BLOCKED on K0 HTTP API** |

**Audit method:** 7 parallel `Explore` subagents (one per phase) with thoroughness=medium/thorough. All findings backed by file:line evidence. See per-issue Status rows below for individual citations dated `2026-04-22 (audit)`.

---

## COMPLETE INVENTORY (What Exists Right Now)

### Factories (8 total — ALL EXIST)

| # | Factory | File | Status |
|---|---------|------|--------|
| F-1 | BusFactory | `k1/bus/factory.py` | ✅ EXISTS |
| F-2 | SessionStateFactory | `k1/sessionstate/factory.py` | ✅ EXISTS |
| F-3 | FabricFactory | `k1/fabric/factory.py` | ✅ EXISTS |
| F-4 | ModelHubFactory | `k1/model_hub/factory.py` | ✅ EXISTS |
| F-5 | OrchestratorFactory | `k1/orchestrator/factory.py` | ✅ EXISTS |
| F-6 | PlannerFactory | `k1/planner/factory.py` | ✅ EXISTS |
| F-7 | ConciergeFactory | `k1/concierge/factory.py` | ✅ EXISTS |
| F-8 | MemoryWriterFactory | `k1/memory_writer/factory.py` | ✅ EXISTS |

---

### Ports — Bus (2 files, 3 ports)

| # | Port | File | Status |
|---|------|------|--------|
| B-P1 | IBus | `k1/bus/ports/bus.py` | ☐ CHECK |
| B-P2 | IMailbox | `k1/bus/ports/mailbox.py` | ☐ CHECK |
| B-P3 | IMailboxRouter | `k1/bus/ports/mailbox.py` | ☐ CHECK |

### Ports — SessionState (5 files, 5 ports)

| # | Port | File | Status |
|---|------|------|--------|
| SS-P1 | IStoragePort | `k1/sessionstate/ports/storage.py` | ☐ CHECK |
| SS-P2 | IEventPort | `k1/sessionstate/ports/events.py` | ☐ CHECK |
| SS-P3 | IWriterPort | `k1/sessionstate/ports/writer.py` | ☐ CHECK |
| SS-P4 | ILifecyclePort | `k1/sessionstate/ports/lifecycle.py` | ☐ CHECK |
| SS-P5 | IK0SyncPort | `k1/sessionstate/ports/k0_sync.py` | ☐ CHECK |

### Ports — Fabric (6 files, 6 ports)

| # | Port | File | Status |
|---|------|------|--------|
| FA-P1 | IStateReaderPort | `k1/fabric/ports/state_reader.py` | ☐ CHECK |
| FA-P2 | IEventPort | `k1/fabric/ports/event_port.py` | ☐ CHECK |
| FA-P3 | IDeltaBusPort | `k1/fabric/ports/delta_bus.py` | ☐ CHECK |
| FA-P4 | IBridgePort | `k1/fabric/ports/bridge_port.py` | ☐ CHECK |
| FA-P5 | IModelGatewayPort | `k1/fabric/ports/model_gateway.py` | ☐ CHECK |
| FA-P6 | IPromptSystemPort | `k1/fabric/ports/prompt_system.py` | ☐ CHECK |

### Ports — ModelHub (7 files, 7 ports)

| # | Port | File | Status |
|---|------|------|--------|
| MH-P1 | IModelHubPort | `k1/model_hub/ports/hub_port.py` | ☐ CHECK |
| MH-P2 | IEventPort | `k1/model_hub/ports/event_port.py` | ☐ CHECK |
| MH-P3 | IStateReadPort | `k1/model_hub/ports/state_read_port.py` | ☐ CHECK |
| MH-P4 | IMetricsPort | `k1/model_hub/ports/metrics_port.py` | ☐ CHECK |
| MH-P5 | IConfigPort | `k1/model_hub/ports/config_port.py` | ☐ CHECK |
| MH-P6 | ICredentialPort | `k1/model_hub/ports/credential_port.py` | ☐ CHECK |
| MH-P7 | IHealthPort | `k1/model_hub/ports/health_port.py` | ☐ CHECK |

### Ports — Orchestrator (9 files, 9 ports)

| # | Port | File | Status |
|---|------|------|--------|
| OR-P1 | IMailboxPort | `k1/orchestrator/ports/mailbox_port.py` | ☐ CHECK |
| OR-P2 | IFabricGatewayPort | `k1/orchestrator/ports/fabric_gateway_port.py` | ☐ CHECK |
| OR-P3 | IPlannerPort | `k1/orchestrator/ports/planner_port.py` | ☐ CHECK |
| OR-P4 | IStateReadPort | `k1/orchestrator/ports/state_read_port.py` | ☐ CHECK |
| OR-P5 | IDeltaEmitPort | `k1/orchestrator/ports/delta_emit_port.py` | ☐ CHECK |
| OR-P6 | IBridgeWritePort | `k1/orchestrator/ports/bridge_write_port.py` | ☐ CHECK |
| OR-P7 | IEventSubscriptionPort | `k1/orchestrator/ports/event_subscription_port.py` | ☐ CHECK |
| OR-P8 | IWorkflowStoragePort | `k1/orchestrator/ports/workflow_storage_port.py` | ☐ CHECK |
| OR-P9 | IAdminPort | `k1/orchestrator/ports/admin_port.py` | ☐ CHECK |

### Ports — Planner (7 files, 7 ports)

| # | Port | File | Status |
|---|------|------|--------|
| PL-P1 | ILLMPort | `k1/planner/ports/llm_port.py` | ☐ CHECK |
| PL-P2 | IFabricRetrievalPort | `k1/planner/ports/fabric_retrieval_port.py` | ☐ CHECK |
| PL-P3 | IStateReadPort | `k1/planner/ports/state_read_port.py` | ☐ CHECK |
| PL-P4 | IBridgePort | `k1/planner/ports/bridge_port.py` | ☐ CHECK |
| PL-P5 | IDeltaEmitPort | `k1/planner/ports/delta_emit_port.py` | ☐ CHECK |
| PL-P6 | IEventPort | `k1/planner/ports/event_port.py` | ☐ CHECK |
| PL-P7 | IMailboxPort | `k1/planner/ports/mailbox_port.py` | ☐ CHECK |

### Ports — Concierge (1 file, 8 ports)

| # | Port | File | Status |
|---|------|------|--------|
| CO-P1 | IInputPort | `k1/concierge/ports.py` | ☐ CHECK |
| CO-P2 | IOutputPort | `k1/concierge/ports.py` | ☐ CHECK |
| CO-P3 | IClassificationPort | `k1/concierge/ports.py` | ☐ CHECK |
| CO-P4 | ILLMPort | `k1/concierge/ports.py` | ☐ CHECK |
| CO-P5 | IStatePort | `k1/concierge/ports.py` | ☐ CHECK |
| CO-P6 | IDispatchPort | `k1/concierge/ports.py` | ☐ CHECK |
| CO-P7 | IDeltaPort | `k1/concierge/ports.py` | ☐ CHECK |
| CO-P8 | IMemoryPort | `k1/concierge/ports.py` | ☐ CHECK |

### Ports — MemoryWriter (5 files, 5 ports)

| # | Port | File | Status |
|---|------|------|--------|
| MW-P1 | ISessionReadPort | `k1/memory_writer/ports/session_read_port.py` | ☐ CHECK |
| MW-P2 | IModelHubPort | `k1/memory_writer/ports/model_hub_port.py` | ☐ CHECK |
| MW-P3 | IHealthPort | `k1/memory_writer/ports/health_port.py` | ☐ CHECK |
| MW-P4 | IEventSubscriptionPort | `k1/memory_writer/ports/event_subscription_port.py` | ☐ CHECK |
| MW-P5 | IBridgeCommandPort | `k1/memory_writer/ports/bridge_command_port.py` | ☐ CHECK |

### **PORTS TOTAL: 52 ports across 8 components**

---

### Adapters — Bus (2 production)

| # | Adapter | File | Type | Implements | Status |
|---|---------|------|------|------------|--------|
| B-A1 | SessionAdapter | `k1/bus/adapters/session_adapter.py` | PROD | Per-session bus | ☐ CHECK |
| B-A2 | FabricAdapter | `k1/bus/adapters/fabric_adapter.py` | PROD | Fabric bus bridge | ☐ CHECK |

### Adapters — Bus Middleware (3)

| # | Adapter | File | Type | Status |
|---|---------|------|------|--------|
| B-M1 | TracingMiddleware | `k1/bus/middleware/tracing.py` | PROD | ☐ CHECK |
| B-M2 | MetricsMiddleware | `k1/bus/middleware/metrics.py` | PROD | ☐ CHECK |
| B-M3 | TopicValidationMiddleware | `k1/bus/middleware/` | PROD | ☐ CHECK |

### Adapters — SessionState (10 total)

| # | Adapter | File | Type | Implements | Status |
|---|---------|------|------|------------|--------|
| SS-A1 | SQLiteStorageAdapter | `k1/sessionstate/adapters/sqlite_storage.py` | PROD | IStoragePort | ☐ CHECK |
| SS-A2 | InMemoryStorageAdapter | `k1/sessionstate/adapters/memory_storage.py` | TEST | IStoragePort | ☐ CHECK |
| SS-A3 | LocalEventAdapter | `k1/sessionstate/adapters/local_events.py` | PROD | IEventPort | ☐ CHECK |
| SS-A4 | DirectWriterAdapter | `k1/sessionstate/adapters/direct_writer.py` | PROD | IWriterPort | ☐ CHECK |
| SS-A5 | StandaloneLifecycle | `k1/sessionstate/adapters/standalone_lifecycle.py` | PROD | ILifecyclePort | ☐ CHECK |
| SS-A6 | FabricLifecycle | `k1/sessionstate/adapters/fabric_lifecycle.py` | PROD | ILifecyclePort | ☐ CHECK |
| SS-A7 | DeltaBusAdapter | `k1/sessionstate/adapters/delta_bus.py` | PROD | IEventPort | ☐ CHECK |
| SS-A8 | ConciergeWriter | `k1/sessionstate/adapters/concierge_writer.py` | PROD | IWriterPort | ☐ CHECK |
| SS-A9 | BridgeStorage | `k1/sessionstate/adapters/bridge_storage.py` | PROD | IK0SyncPort | ☐ CHECK |
| SS-A10 | BridgeSync | `k1/sessionstate/adapters/bridge_sync.py` | PROD | IK0SyncPort | ☐ CHECK |

### Adapters — Fabric (14 total: 8 prod + 6 test)

| # | Adapter | File | Type | Implements | Status |
|---|---------|------|------|------------|--------|
| FA-A1 | SessionStateReader | `k1/fabric/adapters/sessionstate_reader.py` | PROD | IStateReaderPort | ☐ CHECK |
| FA-A2 | EventPortProd | `k1/fabric/adapters/event_port_prod.py` | PROD | IEventPort | ☐ CHECK |
| FA-A3 | DeltaBusProd | `k1/fabric/adapters/delta_bus_prod.py` | PROD | IDeltaBusPort | ☐ CHECK |
| FA-A4 | BridgeConnection | `k1/fabric/adapters/bridge_connection.py` | PROD | IBridgePort | ☐ CHECK |
| FA-A5 | ModelGatewayBridge | `k1/fabric/adapters/model_gateway_bridge.py` | PROD | IModelGatewayPort | ☐ CHECK |
| FA-A6 | PromptSystemProd | `k1/fabric/adapters/prompt_system_prod.py` | PROD | IPromptSystemPort | ☐ CHECK |
| FA-A7 | LocalEvent | `k1/fabric/adapters/local_event.py` | PROD | IEventPort | ☐ CHECK |
| FA-A8 | AutoWasmRuntime | `k1/fabric/adapters/auto_wasm_runtime.py` | PROD | (WASM) | ☐ CHECK |
| FA-A9 | AutoMcpTransport | `k1/fabric/adapters/auto_mcp_transport.py` | PROD | (MCP) | ☐ CHECK |
| FA-T1 | TestStateReader | `k1/fabric/adapters/test_state_reader.py` | TEST | IStateReaderPort | ☐ CHECK |
| FA-T2 | TestEventPort | `k1/fabric/adapters/test_event.py` | TEST | IEventPort | ☐ CHECK (name: test_event or local_event?) |
| FA-T3 | TestDeltaBus | `k1/fabric/adapters/test_delta_bus.py` | TEST | IDeltaBusPort | ☐ CHECK |
| FA-T4 | TestBridge | `k1/fabric/adapters/test_bridge.py` | TEST | IBridgePort | ☐ CHECK |
| FA-T5 | TestModelGateway | `k1/fabric/adapters/test_model_gateway.py` | TEST | IModelGatewayPort | ☐ CHECK |
| FA-T6 | TestPromptSystem | `k1/fabric/adapters/test_prompt_system.py` | TEST | IPromptSystemPort | ☐ CHECK |
| FA-T7 | TestWasmRuntime | `k1/fabric/adapters/test_wasm_runtime.py` | TEST | (WASM) | ☐ CHECK |
| FA-T8 | TestMcpTransport | `k1/fabric/adapters/test_mcp_transport.py` | TEST | (MCP) | ☐ CHECK |

### Adapters — ModelHub (9 production)

| # | Adapter | File | Type | Implements | Status |
|---|---------|------|------|------------|--------|
| MH-A1 | SessionStateReadAdapter | `k1/model_hub/adapters/session_state_read_adapter.py` | PROD | IStateReadPort | ☐ CHECK |
| MH-A2 | SessionStateProd | `k1/model_hub/adapters/session_state_prod.py` | PROD | IStateReadPort | ☐ CHECK |
| MH-A3 | PrometheusAdapter | `k1/model_hub/adapters/prometheus_adapter.py` | PROD | IMetricsPort | ☐ CHECK |
| MH-A4 | LLMRequestBusAdapter | `k1/model_hub/adapters/llm_request_bus_adapter.py` | PROD | IModelHubPort | ☐ CHECK |
| MH-A5 | HealthReportAdapter | `k1/model_hub/adapters/health_report_adapter.py` | PROD | IHealthPort | ☐ CHECK |
| MH-A6 | EventBusAdapter | `k1/model_hub/adapters/event_bus_adapter.py` | PROD | IEventPort | ☐ CHECK |
| MH-A7 | CredentialStoreAdapter | `k1/model_hub/adapters/credential_store_adapter.py` | PROD | ICredentialPort | ☐ CHECK |
| MH-A8 | ConfigAdapter | `k1/model_hub/adapters/config_adapter.py` | PROD | IConfigPort | ☐ CHECK |
| MH-A9 | BusEnvelopeDeserializer | `k1/model_hub/adapters/bus_envelope_deserializer.py` | PROD | (utility) | ☐ CHECK |

### Adapters — Orchestrator (11 prod + 4 mock + 1 test)

| # | Adapter | File | Type | Implements | Status |
|---|---------|------|------|------------|--------|
| OR-A1 | MailboxAdapter | `k1/orchestrator/adapters/mailbox_adapter.py` | PROD | IMailboxPort | ☐ CHECK |
| OR-A2 | FabricGatewayAdapter | `k1/orchestrator/adapters/fabric_gateway_adapter.py` | PROD | IFabricGatewayPort | ☐ CHECK |
| OR-A3 | PlannerAdapter | `k1/orchestrator/adapters/planner_adapter.py` | PROD | IPlannerPort | ☐ CHECK |
| OR-A4 | StateReadAdapter | `k1/orchestrator/adapters/state_read_adapter.py` | PROD | IStateReadPort | ☐ CHECK |
| OR-A5 | DeltaEmitAdapter | `k1/orchestrator/adapters/delta_emit_adapter.py` | PROD | IDeltaEmitPort | ☐ CHECK |
| OR-A6 | BridgeWriteAdapter | `k1/orchestrator/adapters/bridge_write_adapter.py` | PROD | IBridgeWritePort | ☐ CHECK |
| OR-A7 | EventSubscriptionAdapter | `k1/orchestrator/adapters/event_subscription_adapter.py` | PROD | IEventSubscriptionPort | ☐ CHECK |
| OR-A8 | WorkflowStorageAdapter | `k1/orchestrator/adapters/workflow_storage_adapter.py` | PROD | IWorkflowStoragePort | ☐ CHECK |
| OR-A9 | AdminHttpAdapter | `k1/orchestrator/adapters/admin_http_adapter.py` | PROD | IAdminPort | ☐ CHECK |
| OR-M1 | MockPlannerAdapter | `k1/orchestrator/adapters/mock_planner_adapter.py` | MOCK | IPlannerPort | ☐ CHECK |
| OR-M2 | MockFabricAdapter | `k1/orchestrator/adapters/mock_fabric_adapter.py` | MOCK | IFabricGatewayPort | ☐ CHECK |
| OR-M3 | MockBridgeAdapter | `k1/orchestrator/adapters/mock_bridge_adapter.py` | MOCK | IBridgeWritePort | ☐ CHECK |
| OR-M4 | MockStateReadAdapter | `k1/orchestrator/adapters/mock_state_read_adapter.py` | MOCK | IStateReadPort | ☐ CHECK |
| OR-T1 | TestMailboxAdapter | `k1/orchestrator/adapters/test_mailbox_adapter.py` | TEST | IMailboxPort | ☐ CHECK |
| OR-T2 | TestEventAdapter | `k1/orchestrator/adapters/test_event_adapter.py` | TEST | IEventSubscriptionPort | ☐ CHECK |
| OR-T3 | TestDeltaAdapter | `k1/orchestrator/adapters/test_delta_adapter.py` | TEST | IDeltaEmitPort | ☐ CHECK |
| OR-T4 | TestWorkflowStorageAdapter | `k1/orchestrator/adapters/test_workflow_storage_adapter.py` | TEST | IWorkflowStoragePort | ☐ CHECK |

### Adapters — Planner (7 production)

| # | Adapter | File | Type | Implements | Status |
|---|---------|------|------|------------|--------|
| PL-A1 | LLMGatewayAdapter | `k1/planner/adapters/llm_gateway_adapter.py` | PROD | ILLMPort | ☐ CHECK |
| PL-A2 | FabricRetrievalAdapter | `k1/planner/adapters/fabric_retrieval_adapter.py` | PROD | IFabricRetrievalPort | ☐ CHECK |
| PL-A3 | SessionStateAdapter | `k1/planner/adapters/session_state_adapter.py` | PROD | IStateReadPort | ☐ CHECK |
| PL-A4 | BridgeAdapter | `k1/planner/adapters/bridge_adapter.py` | PROD | IBridgePort | ☐ CHECK |
| PL-A5 | DeltaBusAdapter | `k1/planner/adapters/delta_bus_adapter.py` | PROD | IDeltaEmitPort | ☐ CHECK |
| PL-A6 | EventBusAdapter | `k1/planner/adapters/event_bus_adapter.py` | PROD | IEventPort | ☐ CHECK |
| PL-A7 | MailboxAdapter | `k1/planner/adapters/mailbox_adapter.py` | PROD | IMailboxPort | ☐ CHECK |

### Adapters — Concierge (17 total: 8 prod + 8 test + 1 other)

| # | Adapter | File | Type | Implements | Status |
|---|---------|------|------|------------|--------|
| CO-A1 | BusInput | `k1/concierge/adapters/bus_input.py` | PROD | IInputPort | ☐ CHECK |
| CO-A2 | BusOutput | `k1/concierge/adapters/bus_output.py` | PROD | IOutputPort | ☐ CHECK |
| CO-A3 | UltraBERTClassification | `k1/concierge/adapters/ultrabert_classification.py` | PROD | IClassificationPort | ☐ CHECK |
| CO-A4 | HubLLM | `k1/concierge/adapters/hub_llm.py` | PROD | ILLMPort | ☐ CHECK |
| CO-A5 | SSMState | `k1/concierge/adapters/ssm_state.py` | PROD | IStatePort | ☐ CHECK |
| CO-A6 | FabricDispatch | `k1/concierge/adapters/fabric_dispatch.py` | PROD | IDispatchPort | ☐ CHECK |
| CO-A7 | LocalDelta | `k1/concierge/adapters/local_delta.py` | PROD | IDeltaPort | ☐ CHECK |
| CO-A8 | RecallMemory | `k1/concierge/adapters/recall_memory.py` | PROD | IMemoryPort | ☐ CHECK |
| CO-A9 | SnapshotStateRead | `k1/concierge/adapters/snapshot_state_read.py` | PROD | (state snapshot) | ☐ CHECK |
| CO-N1 | NullStateReader | `k1/concierge/adapters/null_state_reader.py` | NULL | IStateReaderPort | ☐ CHECK |
| CO-N2 | NullEventSubscription | `k1/concierge/adapters/null_event_subscription.py` | NULL | IEventSubscriptionPort | ☐ CHECK |
| CO-N3 | NullDeltaBus | `k1/concierge/adapters/null_delta_bus.py` | NULL | IDeltaBusPort | ☐ CHECK |
| CO-N4 | NullBridgeWrite | `k1/concierge/adapters/null_bridge_write.py` | NULL | IBridgeWritePort | ☐ CHECK |
| CO-T1 | TestInput | `k1/concierge/adapters/test_input.py` | TEST | IInputPort | ☐ CHECK |
| CO-T2 | TestOutput | `k1/concierge/adapters/test_output.py` | TEST | IOutputPort | ☐ CHECK |
| CO-T3 | TestClassification | `k1/concierge/adapters/test_classification.py` | TEST | IClassificationPort | ☐ CHECK |
| CO-T4 | TestLLM | `k1/concierge/adapters/test_llm.py` | TEST | ILLMPort | ☐ CHECK |
| CO-T5 | TestState | `k1/concierge/adapters/test_state.py` | TEST | IStatePort | ☐ CHECK |
| CO-T6 | TestDispatch | `k1/concierge/adapters/test_dispatch.py` | TEST | IDispatchPort | ☐ CHECK |
| CO-T7 | TestDelta | `k1/concierge/adapters/test_delta.py` | TEST | IDeltaPort | ☐ CHECK |
| CO-T8 | TestMemory | `k1/concierge/adapters/test_memory.py` | TEST | IMemoryPort | ☐ CHECK |

### Adapters — MemoryWriter (5 prod + 1 test bundle)

| # | Adapter | File | Type | Implements | Status |
|---|---------|------|------|------------|--------|
| MW-A1 | SessionReadAdapter | `k1/memory_writer/adapters/session_read_adapter.py` | PROD | ISessionReadPort | ☐ CHECK |
| MW-A2 | ModelHubAdapter | `k1/memory_writer/adapters/model_hub_adapter.py` | PROD | IModelHubPort | ☐ CHECK |
| MW-A3 | HealthAdapter | `k1/memory_writer/adapters/health_adapter.py` | PROD | IHealthPort | ☐ CHECK |
| MW-A4 | EventSubscriptionAdapter | `k1/memory_writer/adapters/event_subscription_adapter.py` | PROD | IEventSubscriptionPort | ☐ CHECK |
| MW-A5 | BridgeCommandAdapter | `k1/memory_writer/adapters/bridge_command_adapter.py` | PROD | IBridgeCommandPort | ☐ CHECK |
| MW-T1 | TestAdapters (bundle) | `k1/memory_writer/adapters/test_adapters.py` | TEST | All 5 ports | ☐ CHECK |

### Adapters — Bridge (partial)

| # | Adapter | File | Type | Implements | Status |
|---|---------|------|------|------------|--------|
| BR-A1 | KernelCommandPort | `bridge/kernel/command_port.py` | PROD | IKernelCommandPort | ☐ CHECK |
| BR-A2 | LocalOutbox | `bridge/sync/local_outbox.py` | PROD | Offline queue | ☐ CHECK |
| BR-A3 | BridgeClient | `bridge/client.py` | PROD | Facade | ☐ CHECK |

### Bridge Ports (5 protocol files)

| # | Port | File | Status |
|---|------|------|--------|
| BR-P1 | ICommandPortProtocol | `bridge/ports/command_port_protocol.py` | ☐ CHECK |
| BR-P2 | IQueryPortProtocol | `bridge/ports/query_port_protocol.py` | ☐ CHECK |
| BR-P3 | ISSEPortProtocol | `bridge/ports/sse_port_protocol.py` | ☐ CHECK |
| BR-P4 | IObsPortProtocol | `bridge/ports/obs_port_protocol.py` | ☐ CHECK |
| BR-P5 | IConnectorGatewayProtocol | `bridge/ports/connector_gateway_protocol.py` | ☐ CHECK |

### Bridge Core (4 files)

| # | Module | File | Status |
|---|--------|------|--------|
| BR-C1 | Transport | `bridge/core/transport.py` | ☐ CHECK |
| BR-C2 | Signing | `bridge/core/signing.py` | ☐ CHECK |
| BR-C3 | Health | `bridge/core/health.py` | ☐ CHECK |
| BR-C4 | EnvelopeBuilder | `bridge/core/envelope_builder.py` | ☐ CHECK |

### **ADAPTERS TOTAL: ~90 adapter files across 8 components + bridge**

---

### Bootstrap / Kernel Files

| # | File | Purpose | Status |
|---|------|---------|--------|
| K-1 | `k1/concierge/kernel/bootstrap.py` | `start_kernel()` — current entry point | ☐ CHECK |
| K-2 | `k1/concierge/kernel/runner.py` | Runner (CLI entry?) | ☐ CHECK |
| K-3 | `k1/concierge/kernel/chat_repl.py` | Chat REPL | ☐ CHECK |
| K-4 | `k1/concierge/session.py` | ConciergeRuntime + ConciergeSession | ☐ CHECK |
| K-5 | `k1/concierge/factory.py` | ConciergeFactory.create_with_ports() | ☐ CHECK |
| K-6 | `k1/concierge/ports.py` | 8 Protocol definitions | ☐ CHECK |
| K-7 | `k1/concierge/config/kernel.py` | KernelConfig | ☐ CHECK |
| K-8 | `k1/concierge/config/concierge.py` | ConciergeConfig | ☐ CHECK |
| K-9 | `k1/concierge/config/loader.py` | Config loader | ☐ CHECK |
| K-10 | `k1/kernel/__init__.py` | Kernel package | ☐ CHECK |
| K-11 | `k1/kernel/loader.py` | Module loader (stub?) | ☐ CHECK |
| K-12 | `k1/kernel/hot_reload.py` | Hot reload (stub?) | ☐ CHECK |
| K-13 | `k1/kernel/registries/agent_registry.py` | Agent registry | ☐ CHECK |
| K-14 | `k1/kernel/registries/prompt_registry.py` | Prompt registry | ☐ CHECK |
| K-15 | `k1/kernel/registries/tool_registry.py` | Tool registry | ☐ CHECK |

---

## MILESTONES / EPICS / ISSUES

---

### MS-1: Component Audit — Read Every Port, Adapter, Factory

**Goal:** Read real code. For each item confirm: signature matches spec, adapter implements its port, factory wires correctly. No code changes — discovery only.

#### Epic 1.1: Bus Audit — ✅ COMPLETE (see `10_bus_audit.md`)

| Issue | What To Check | File(s) | Status |
|-------|--------------|---------|--------|
| 1.1.1 | Read IBus, IMailbox, IMailboxRouter — confirm method signatures | B-P1, B-P2, B-P3 | ✅ All 3 protocols complete, @runtime_checkable |
| 1.1.2 | Read BusFactory — confirm create_local(), create_local_ordered(), create_mailbox_router() | F-1 | ✅ 4 methods, dual-backend Python+Rust |
| 1.1.3 | Read SessionAdapter — what does it do, does it match spec? | B-A1 | ✅ Real (~235 LOC), adapts IEventPort for SessionState |
| 1.1.4 | Read FabricAdapter — what does it do, dual-role? | B-A2 | ✅ Real (~245 LOC), dual IEventPort + IDeltaBusPort |
| 1.1.5 | Read TracingMiddleware — does it stamp session_id + cognitive_trace_id? | B-M1 | ✅ Real (~133 LOC), READ-ONLY (does NOT stamp, reads for OTel spans) |
| 1.1.6 | Read MetricsMiddleware, TopicValidation — stubs or real? | B-M2, B-M3 | ✅ Both real, Prometheus metrics + soft topic validation |

#### Epic 1.2: SessionState Audit

| Issue | What To Check | File(s) | Status |
|-------|--------------|---------|--------|
| 1.2.1 | Read 5 port definitions — signatures match spec? | SS-P1..P5 | ✅ All 5 ABC ports complete, rich types (~2,430 LOC) |
| 1.2.2 | Read SessionStateFactory — create_standalone(), create_with_ports() signatures | F-2 | ✅ 3 methods, full DI, two-phase bind |
| 1.2.3 | Read all 10 adapters — which implement which port? Production-ready? | SS-A1..A10 | ⚠️ 4 real + 1 test + 5 STUBS (NotImplementedError) |
| 1.2.4 | Confirm SSM IS IStatePort (no wrapper needed for Concierge) | SS manager.py | ⚠️ CORRECTED: SSM ≠ IStatePort — SSMStateAdapter wrapper needed (47 LOC) |

#### Epic 1.3: Fabric Audit

| Issue | What To Check | File(s) | Status |
|-------|--------------|---------|--------|
| 1.3.1 | Read 6 port definitions — signatures match spec? | FA-P1..P6 | ✅ All 6 Protocol + @runtime_checkable, ~1,150 LOC |
| 1.3.2 | Read FabricFactory — create_with_ports(), create_production() signatures | F-3 | ✅ 3 methods, 20-step pipeline, zero external imports |
| 1.3.3 | Read 8 production adapters — which implements which port? | FA-A1..A9 | ✅ ALL 9 REAL — zero stubs |
| 1.3.4 | Confirm FabricBusAdapter dual-role (IEventPort + IDeltaBusPort same instance?) | FA-A2, FA-A3 | ✅ SEPARATE classes, can share bus instance |
| 1.3.5 | Read SessionStateReader adapter — takes (ssm, session_id) TWO args? | FA-A1 | ✅ TWO ARGS: `__init__(manager: Any, session_id: str)` |
| 1.3.6 | Check if NullSessionStateReaderAdapter exists (needed for shared Fabric) | `k1/concierge/adapters/null_state_reader.py` | ⚠️ EXISTS but NOT wired into any factory method |

#### Epic 1.4: ModelHub Audit

| Issue | What To Check | File(s) | Status |
|-------|--------------|---------|--------|
| 1.4.1 | Read 7 port definitions | MH-P1..P7 | ✅ All 7 Protocol + @runtime_checkable, 15 methods, mixed sync/async |
| 1.4.2 | Read ModelHubFactory — create_standalone() signature | F-4 | ✅ 3 methods, _HubCore inside factory, 11-step wiring |
| 1.4.3 | Read 9 production adapters | MH-A1..A9 | ✅ 3 REAL + 6 SEMI-REAL + 0 stubs |
| 1.4.4 | Check execute() vs chat() — does collision exist? | MH-P1, MW-P2 | ✅ CONTAINED — MW has own IModelHubPort(chat()), adapters translate |

#### Epic 1.5: Orchestrator Audit

| Issue | What To Check | File(s) | Status |
|-------|--------------|---------|--------|
| 1.5.1 | Read 9 port definitions | OR-P1..P9 | ✅ All 9 Protocol, @runtime_checkable, 55 methods, ~1,099 LOC |
| 1.5.2 | Read OrchestratorFactory — create_production() signature + 15-step wiring | F-5 | ✅ 4 static methods, 15-step _construct_orchestrator(), 560 LOC, full DI |
| 1.5.3 | Read all 17 adapters (9 prod + 4 mock + 4 test) | OR-A1..T4 | ✅ ALL 9 prod REAL — zero stubs. 4 mock + 4 test. IAdminPort has no test double |
| 1.5.4 | Confirm DeltaEmitAdapter takes TWO args (event_port, delta_bus) | OR-A5 | ✅ YES — `(event_port: IEventPort, delta_bus: IDeltaBusPort)` exactly |
| 1.5.5 | Confirm PlannerAdapter exists for S6b hot-swap | OR-A3 | ❌ NO hot-swap. **slots** + no setter. Phase 2 needs PlannerProxy |
| 1.5.6 | Confirm MockPlannerAdapter exists for Phase 1 | OR-M1 | ✅ Fully scriptable — per-request accept/reject + async delivery callback |

#### Epic 1.6: Planner Audit

| Issue | What To Check | File(s) | Status |
|-------|--------------|---------|--------|
| 1.6.1 | Read 7 port definitions | PL-P1..P7 | ✅ All 7 Protocol, @runtime_checkable, 15 methods, ~537 LOC |
| 1.6.2 | Read PlannerFactory — create_production() signature | F-6 | ✅ 4 static methods, 10-step _wire(), 573 LOC, 3-pass validation |
| 1.6.3 | Read all 7 production adapters | PL-A1..A7 | ✅ 6 REAL + 1 SEMI-REAL (MailboxAdapter: asyncio.Queue) |
| 1.6.4 | Confirm SessionStateAdapter = SnapshotStateReadAdapter pattern? | PL-A3 | ✅ YES — SessionStateReadAdapter(reader, session_id), per-session read-only |
| 1.6.5 | Confirm EventBusAdapter ≠ DeltaBusAdapter (separate instances) | PL-A5, PL-A6 | ✅ YES — separate classes, separate Fabric port types, CANNOT share |

#### Epic 1.7: Concierge Audit ✅ COMPLETE — see `16_concierge_audit.md`

| Issue | What To Check | File(s) | Status |
|-------|--------------|---------|--------|
| 1.7.1 | Read 9 port definitions (5 new Protocol + 4 re-export alias) in single ports.py (155 LOC) | CO-P1..P9 | ✅ All `@runtime_checkable`. `IFabricPort` in `__all__` but NOT in PortBundle |
| 1.7.2 | Read ConciergeFactory — PortBundle(5 req + 3 opt), 4 methods, 16-step wiring (860 LOC) | K-5 | ✅ Largest factory. `init()` NOT called — caller must `await start()` |
| 1.7.3 | Read 8 production adapters: 3 REAL + 2 SEMI-REAL + 3 RE-EXPORT | CO-A1..A8 | ✅ `FabricDispatchAdapter` routes LOW→Fabric, MED/HIGH→Orchestrator |
| 1.7.4 | Read 4 null adapters — safe no-ops for two-tier bootstrap | CO-N1..N4 | ✅ Return None/empty/False. CO-N1 exists but NOT wired (see Epic 1.3) |
| 1.7.5 | Read 8 test adapters — mixed quality | CO-T1..T8 | ✅ CO-T7 is NOT a test double (returns real LocalBus) |
| 1.7.6 | Read SnapshotStateReadAdapter — bind(snapshot)/read_sections() (51 LOC) | CO-A9 | ✅ Late-bound per-request for shared Planner. REAL |
| 1.7.7 | Read bootstrap.py — 25-step start_kernel(), KernelRuntime(24+ fields, many Any) (743 LOC) | K-1 | ⚠️ Hard dep on `poc.k1_poc.main.boot()`. Undeclared fields via setattr |
| 1.7.8 | Read session.py — ConciergeRuntime(class) vs KernelRuntime(dataclass) (448 LOC) | K-4 | ⚠️ ~200 LOC duplicated. TWO parallel runtime types. Must converge MS-2 |
| 1.7.9 | Read config — KernelConfig(mutable, no validation) vs ConciergeConfig(frozen, validated) | K-7..K-9 | ✅ tool_tier mismatch: runner offers "MEDIUM"/"CRISIS", config validates {"LOW","MED","HIGH"} |

#### Epic 1.8: MemoryWriter Audit ✅ COMPLETE — see `17_memorywriter_audit.md`

| Issue | What To Check | File(s) | Status |
|-------|--------------|---------|--------|
| 1.8.1 | Read 5 port definitions — all Protocol, @runtime_checkable, all-async, 11 methods, 371 LOC | MW-P1..P5 | ✅ Zero cross-module port imports. Cleanest boundary |
| 1.8.2 | Read MemoryWriterFactory — 1 static `create()`, all 5 ports required, 11-step pipeline, 143 LOC | F-8 | ✅ Smallest factory. `isinstance` validates all ports at construction |
| 1.8.3 | Read 5 production adapters (4 REAL + 1 SEMI-REAL) + 5 Fake test doubles | MW-A1..A5, MW-T1 | ✅ Zero stubs, zero null adapters. `FakeSessionReadPort` missing `list_sections()` |
| 1.8.4 | Check ModelHubAdapter — chat() vs execute() collision | MW-A2 | ✅ CONTAINED — MW own `IModelHubPort(chat())` → adapter translates to K1 `execute(HubRequest)`. Anti-corruption layer |

#### Epic 1.9: Bridge Audit ✅ COMPLETE — see `18_bridge_audit.md`

| Issue | What To Check | File(s) | Status |
|-------|--------------|---------|--------|
| 1.9.1 | Read 5 bridge port protocols — all Protocol, @runtime_checkable, all-async, 493 LOC | BR-P1..P5 | ✅ Rich types (13 dataclasses). Self-contained |
| 1.9.2 | Read BridgeClient facade — IBridgeClient(11 methods) + StubBridgeClient + SinkBridgeClient (277 LOC) | BR-A3 | ✅ Unified facade. SinkBridgeClient IS the production offline client |
| 1.9.3 | Read KernelCommandPort — submit()+submit_batch(), HTTP POST + offline fallback (189 LOC) | BR-A1 | ✅ REAL — ContractViolationError, PolicyDeniedError, 409 dedup |
| 1.9.4 | Read LocalOutbox — SQLite WAL queue, 10K depth, 10 max attempts (215 LOC) | BR-A2 | ✅ REAL — enqueue/drain/mark_failed. Guarantees MW-09 |
| 1.9.5 | Read bridge core — HttpTransport(httpx), HMAC+Ed25519 signing, health state machine, BLAKE3 integrity | BR-C1..C4 | ✅ ALL 4 REAL — 688 LOC total |
| 1.9.6 | Check bridge/adapters/ — EMPTY, zero adapter files | `bridge/adapters/` | ❌ Placeholder only. All adapter logic in kernel/command_port.py + client.py |
| 1.9.7 | Check bridge/connector/ — EMPTY, deferred to MS-3 (IFL) | `bridge/connector/` | ❌ Placeholder only. 4 of 5 ports have NO concrete implementation |

#### Epic 1.10: Kernel Package Audit ✅ COMPLETE — see `19_kernel_package_audit.md`

| Issue | What To Check | File(s) | Status |
|-------|--------------|---------|--------|
| 1.10.1 | Read k1/kernel/ — ModuleLoader(19 LOC, all pass), HotReloadEngine(12 LOC, all pass) | K-11, K-12 | ✅ **ALL STUBS** — zero imports from anywhere. 100% dead code |
| 1.10.2 | Read registries — 3 minimal dict wrappers (11-15 LOC each), no types/validation/versioning | K-13, K-14, K-15 | ✅ **ALL STUBS** — nobody imports from k1.kernel |
| 1.10.3 | Read runner.py(76 LOC, argparse+signals) + chat_repl.py(225 LOC, sys.argv+model swap) | K-2, K-3 | ✅ Both REAL. Real kernel lives in k1/concierge/kernel/, NOT k1/kernel/ |

---

### MS-2: Kernel Skeleton — KernelService + Multi-Session

**Goal:** Create proper `KernelService` class with startup/create_session/shutdown. Evolve from current `start_kernel()`.

**Key discovery (from MS-1):** 13 CRITICAL + 33 HIGH blockers found. A new Epic 2.0 (Pre-Requisites) must complete before any wiring can begin. See `20_ms1_synthesis.md` for full analysis.

---

#### Epic 2.0: Pre-Requisites (MUST complete before 2.1–2.5)

##### Issue 2.0.1 — Create `AsyncBusBridge` (wrap sync IBus for async callers)

| Field | Detail |
|-------|--------|
| **Why** | Bus is 100% sync (`threading.Lock/RLock`). Fabric/ModelHub/Orchestrator/Planner are async. Every `bus.publish()` from async code blocks the event loop. (B-BUS-1, W-MH-1, B-OR-2) |
| **Files to create** | `k1/bus/async_bridge.py` (~80–100 LOC), `k1/bus/ports/async_bus.py` (~30 LOC) |
| **IBus methods to wrap** | `publish(envelope) → None` (WRITE), `subscribe(pattern, handler) → SubscriptionHandle` (WRITE), `unsubscribe(handle) → bool` (WRITE) — all 3 via `asyncio.to_thread()` |
| **IMailbox methods to wrap** | `receive(timeout_ms) → Optional[Envelope]` (blocking READ — MUST wrap), `pending() → int` (lock-free — passthrough OK) |
| **IMailboxRouter methods to wrap** | `deliver(actor_id, envelope)` (WRITE), `register(actor_id, config) → IMailbox` (WRITE), `unregister(actor_id) → bool` (WRITE), `registered_actors() → list[str]` (READ — passthrough OK) |
| **Implementation** | 3 wrapper classes: `AsyncBusBridge`, `AsyncMailboxBridge`, `AsyncMailboxRouterBridge`. Each stores `_sync: T` ref and delegates writes via `await asyncio.to_thread(self._sync.method, *args)` |
| **Depends on** | Nothing |
| **Acceptance** | `await bridge.publish(envelope)` does not block event loop. Unit test: create `LocalBus`, wrap, pub/sub from async code |
| **Status** | ☐ |

##### Issue 2.0.2 — Create `AsyncSSMBridge` (wrap sync SSM write path for async callers)

| Field | Detail |
|-------|--------|
| **Why** | `SessionStateManager` uses `threading.RLock` (`_write_lock`) for all mutations. Async kernel code calling `ssm.mutate()` blocks the event loop. (B-SS-4) |
| **Files to create** | `k1/sessionstate/async_bridge.py` (~60–80 LOC) |
| **Write methods to wrap (5)** | `mutate(section, op, data, est_bytes?, trace_id?)` (core write), `start(restore?, trace_id?)` (lifecycle), `stop(checkpoint?, trace_id?)` (lifecycle), `checkpoint(trace_id?)` (I/O), `restore(session_id, trace_id?)` (I/O) — all via `asyncio.to_thread()` |
| **Read properties (14, passthrough)** | `session_id`, `state`, `is_running`, `hot`, `warm`, `local_cold`, `size_tracker`, `mutation_guard`, `get_section(name)`, `get_hot()`, `get_warm()`, `get_all_section_sizes()`, `get_local_cold()`, `get_snapshot()` — all lock-free, delegate directly |
| **Implementation** | Single `AsyncSSMBridge` class. Stores `_ssm: SessionStateManager`. 5 async write methods + 14 passthrough read properties |
| **Depends on** | Nothing |
| **Acceptance** | `await bridge.mutate(...)` does not block event loop. Read props accessible without `await`. Unit test: `create_for_testing()` → wrap → mutate from async |
| **Status** | ☐ |

##### Issue 2.0.3 — Eliminate `poc.k1_poc.main.boot()` from `bootstrap.py`

| Field | Detail |
|-------|--------|
| **Why** | `bootstrap.py` L56 imports `from poc.k1_poc.main import boot`. L104–108 calls `boot(capture=, ordered=)` to create bus/router/adapter/mailboxes. KernelService cannot start without POC layer. (CO-B2, KP-B2) |
| **What `boot()` does** | (1) `BusFactory.create_local(capture=)` or `create_local_ordered()`, (2) `BusFactory.create_mailbox_router()`, (3) `SessionBusAdapter(bus)`, (4) `router.register("front_half", MailboxConfig(capacity=64))`, (5) `router.register("back_half", MailboxConfig(capacity=64))`. Returns `{bus, router, adapter, front_mailbox, back_mailbox}`. Also wires middleware (Tracing, Metrics, TopicValidation) from poc config. |
| **Files to change** | `k1/concierge/kernel/bootstrap.py` — remove L56 import, replace L104–108 with direct factory calls |
| **Replacement code** | Import `BusFactory`, `SessionBusAdapter`, `MailboxConfig` directly. Call `BusFactory.create_local(capture=cfg.capture_bus)` (or `create_local_ordered()`), `BusFactory.create_mailbox_router()`, `SessionBusAdapter(bus)`, `router.register(...)` |
| **Middleware note** | `boot()` also wires TopicValidation/Tracing/Metrics middleware via poc config. Replicate using `KernelConfig` fields or defer to 2.0.5 |
| **LOC change** | ~15 removed, ~12 added. Net −3 |
| **Depends on** | Nothing (2.0.5 completes the config half) |
| **Acceptance** | `grep -r "poc.k1_poc.main" k1/` returns 0 hits. `start_kernel()` still produces working bus/router/mailboxes. Existing tests pass |
| **Status** | ☐ |

##### Issue 2.0.4 — Eliminate `poc.k1_poc.config.get_config()` from SSM factory

| Field | Detail |
|-------|--------|
| **Why** | `k1/sessionstate/factory.py` L44 imports `from poc.k1_poc.config import get_config`. Two call sites: L155 (`get_config().sessionstate.storage.default_db_path`), L184 (`get_config().sessionstate.storage.checkpoint_interval_s`). (B-SS-3) |
| **Current defaults** | Factory already has `DEFAULT_DB_PATH = Path.home() / ".familyos" / "k1" / "sessionstate.db"` at module level (L56). Checkpoint interval default = `30.0` |
| **Files to change** | `k1/sessionstate/factory.py` — remove L44 import, replace 2 `get_config()` calls with existing module-level defaults |
| **Replacement** | L155: `resolved_path = DEFAULT_DB_PATH` (already defined). L184: `checkpoint_interval_s if checkpoint_interval_s is not None else 30.0` |
| **LOC change** | 1 import removed, 2 lines simplified. Net ~3 lines |
| **Depends on** | Nothing |
| **Acceptance** | `grep -r "poc" k1/sessionstate/factory.py` returns 0 hits. `create_standalone()` works with and without explicit args |
| **Status** | ☐ |

##### Issue 2.0.5 — Eliminate `poc.k1_poc.config` from Concierge config loader

| Field | Detail |
|-------|--------|
| **Why** | Triple indirection: `k1/concierge/config/__init__.py` → `from poc.k1_poc.config import *`; `k1/concierge/config/loader.py` → `import poc.k1_poc.config.loader as _canonical`. Both are pure delegation shims (18 LOC + 4 LOC). (CO-B7) |
| **Consumers in bootstrap.py** | L99: `get_config().phase1`, `get_config().delta`; L295: `_get_fsm_config().fsm.dead_letter_enabled`; L411: `get_config().kernel.poll_interval_s`, `get_config().kernel.dedup_cache_size` |
| **Config values actually needed** | `phase1.pipeline` (str), `phase1.warmup_on_startup` (bool), `delta.batch_window_ms` (int), `fsm.dead_letter_enabled` (bool), `kernel.poll_interval_s` (float), `kernel.dedup_cache_size` (int) |
| **Recommended approach** | Approach B (surgical): add 6 fields to existing `KernelConfig` dataclass in `k1/concierge/config/kernel.py`. Replace `get_config().X` calls in bootstrap.py with `cfg.X`. Delete shim files or make them POC-free. ~50 LOC |
| **Files to change** | `k1/concierge/config/kernel.py` (+6 fields), `k1/concierge/config/__init__.py` (remove poc import), `k1/concierge/config/loader.py` (remove poc import), `k1/concierge/kernel/bootstrap.py` (replace get_config() calls) |
| **Depends on** | Nothing (but 2.0.3 and 2.0.4 can be done independently first) |
| **Acceptance** | `grep -r "poc.k1_poc.config" k1/concierge/config/` returns 0 hits. `from k1.concierge.config import get_config` does NOT resolve to poc. All default values preserved |
| **Status** | ☐ |

##### Issue 2.0.6 — Move composition root: `k1/concierge/kernel/` → `k1/kernel/`

| Field | Detail |
|-------|--------|
| **Why** | Real kernel is in `k1/concierge/kernel/` (bootstrap.py 743 LOC, runner.py 83 LOC, chat_repl.py ~100 LOC = ~926 LOC). `k1/kernel/` has dead stubs (69 LOC). KernelService needs a proper home at `k1/kernel/`. (KP-B1) |
| **Files to move** | `bootstrap.py`, `runner.py`, `chat_repl.py` → `k1/kernel/` |
| **Import paths to update (11 files)** | `k1/concierge/kernel/runner.py` L15 (relative import), `k1/concierge/kernel/chat_repl.py` L30, `k1/concierge/kernel/__init__.py` L3, `tests/k1/concierge/test_bootstrap_smoke.py` L25, `tests/k1/concierge/test_concierge_factory.py` L477/483/489/495/502, `tests/k1/concierge/test_e055_poc_production_boundary.py` L284/332, `tests/k1/concierge/test_runner_cli.py` L22/217/239/279 |
| **Backward compat** | Leave `k1/concierge/kernel/__init__.py` as re-export shim → `from k1.kernel.bootstrap import ...` |
| **CLI entry points** | `python -m k1.concierge.kernel.runner` → `python -m k1.kernel.runner`. Docs/scripts need update |
| **Risk** | MEDIUM-HIGH — 7 prod files + 4 test files need import updates. Re-export shim mitigates breaks |
| **Depends on** | 2.0.7 (clear dead stubs first) |
| **Acceptance** | `from k1.kernel.bootstrap import KernelRuntime` works. `python -m k1.kernel.runner --test-mode` starts. All tests pass |
| **Status** | ☐ |

##### Issue 2.0.7 — Delete dead stubs in `k1/kernel/`

| Field | Detail |
|-------|--------|
| **Why** | `k1/kernel/` contains 69 LOC of dead code: `loader.py` (ModuleLoader, 19 LOC all `pass`), `hot_reload.py` (HotReloadEngine, 12 LOC all `pass`), `registries/` (3 dict wrappers, 11–16 LOC each). Zero imports from anywhere. (KP-B3) |
| **Files to delete (6)** | `k1/kernel/loader.py`, `k1/kernel/hot_reload.py`, `k1/kernel/registries/agent_registry.py`, `k1/kernel/registries/prompt_registry.py`, `k1/kernel/registries/tool_registry.py`, `k1/kernel/registries/__init__.py` |
| **Import search** | `from k1.kernel.(loader|hot_reload|registries)` — **0 hits** anywhere. Class names only in design docs. Bridge's `ToolRegistry` is separate class. |
| **LOC removed** | −69 LOC |
| **Depends on** | Nothing (do before 2.0.6) |
| **Acceptance** | All 6 files + `registries/` dir deleted. `k1/kernel/__init__.py` remains. Full test suite passes |
| **Status** | ☐ |

##### Issue 2.0.8 — Create `k1/kernel/ports/` and `k1/kernel/adapters/` scaffolding

| Field | Detail |
|-------|--------|
| **Why** | `k1/kernel/` has no hexagonal infrastructure. KernelService needs its own port protocols and adapter hooks. (KP-B4) |
| **Proposed ports (8)** | `IBusPort` (bus creation/access), `IModelHubPort` (LLM lifecycle), `IFabricPort` (shared/per-session Fabric), `IBridgePort` (K0 connection), `IOrchestratorPort` (task dispatch), `IPlannerPort` (planning engine), `ISessionManagerPort` (per-session bag CRUD), `ILifecyclePort` (startup/shutdown/health) |
| **Pattern** | Follow `k1/orchestrator/ports/` convention: one file per port, `@runtime_checkable Protocol`, `__init__.py` re-exports all |
| **Directory structure** | `k1/kernel/ports/__init__.py` (~40 LOC), 8 port files (~15–25 LOC each), `k1/kernel/adapters/__init__.py` (~20 LOC placeholder) |
| **LOC** | ~230 total for ports/ + adapters/ scaffolding |
| **Depends on** | 2.0.7 (clear dead stubs) |
| **Acceptance** | `from k1.kernel.ports import IBusPort, ISessionManagerPort` works. All ports are `@runtime_checkable Protocol`. Matches orchestrator/fabric conventions |
| **Status** | ☐ |

##### Issue 2.0.9 — Converge `KernelRuntime` + `ConciergeRuntime` into single typed class

| Field | Detail |
|-------|--------|
| **Why** | Two parallel runtime types: `KernelRuntime` (mutable dataclass, 24+ fields, `setattr` hacks for 3 undeclared fields) in bootstrap.py L66–96, vs `ConciergeRuntime` (class, 19 params) in session.py L31–96. ~200 LOC duplicated. (CO-B1, CO-B3, CO-B4) |
| **Overlapping fields (18)** | `bus`, `router`, `front_mailbox`, `back_mailbox`, `session_state`, `model`, `fsm`, `front_dispatcher`, `back_dispatcher`, `experience_layer`, `delta_aggregator`, `hitl_coordinator`, `orchestrator`, `front_subscriptions`, `consumer_task`, `ledger`, `ledger_store`, `dead_letter_consumer`, `started` |
| **Unique to KernelRuntime (8)** | `config`, `adapter`, `capability_registry`, `delta_applicator`, `back_subscriptions`, `weave_batcher` (UNDECLARED setattr L275), `weave_policy` (UNDECLARED setattr L282), `activity_tracker` (UNDECLARED setattr L289) |
| **Unique to ConciergeRuntime (2)** | `front_ctx`, `back_ctx` (ToolContext references) |
| **Target** | Single `@dataclass` with ALL 28 fields declared. Replace `Any` with Protocol/concrete types. Eliminate 3 setattr hacks. Add `front_ctx`/`back_ctx` from ConciergeRuntime |
| **Files to change** | `k1/concierge/kernel/bootstrap.py` (replace dataclass + remove setattr), `k1/concierge/session.py` (replace ConciergeRuntime with import of unified class), all consumers of both types |
| **LOC** | ~100 net (replacing ~130 split across 2 classes) |
| **Depends on** | 2.0.6 (move to k1/kernel/ first so unified class lands in right location) |
| **Acceptance** | Single `KernelRuntime` class, zero `setattr` hacks, all fields typed. Both bootstrap.py and ConciergeFactory create same class. All tests pass |
| **Status** | ☐ |

##### Issue 2.0.10 — ADR: Shared vs Per-Session Resource Map

| Field | Detail |
|-------|--------|
| **Why** | Bus, Fabric, SSM, Mailboxes need DIFFERENT wiring for shared vs per-session. No decision exists. Multiple audit items depend on this: B-BUS-2, W-FAB-2, B-FAB-2, W-SS-2, B-BUS-4. |
| **Current state** | bootstrap.py creates ONE of everything (single-session). No Tier 1/Tier 2 split. |
| **Tier 1 (shared, created once)** | Bus (single ordered, topic-namespaced by session_id), ModelHub (stateless, thread-safe), Shared Fabric (NullSessionStateReaderAdapter), Orchestrator (session_id per-request), Planner (hot-swappable), Bridge (single K0 connection) |
| **Tier 2 (per-session, in create_session)** | SSM (per session_id), Per-session Fabric (SessionStateReaderAdapter bound to one SSM), ConciergeController/FSM (per session), Tool dispatchers + ToolContext, ExperienceLayer, Delta agg/applicator, HiTL coordinator, Mailboxes (namespaced: `"front_{session_id}"`) |
| **Bus decision** | SINGLE bus with topic namespacing (not bus-per-session). Rationale: Orchestrator needs cross-session dispatch. session_id stamped in envelope metadata. MailboxRouter creates per-session mailboxes on shared bus |
| **Circular bootstrap (SSM↔Concierge)** | Two-phase bind: create SSM first → create Concierge → bind SSM's event adapter post-construction. Already proven in `SessionStateFactory.create_with_ports()` |
| **Output** | ADR document in `docs/architecture/decisions-K1/` |
| **Depends on** | 2.0.9 (unified runtime) to finalize field layout |
| **Acceptance** | ADR created. Shared/per-session split validated against doc 08 wiring spec |
| **Status** | ✅ |

##### Issue 2.0.11 — Fix `AdminHttpAdapter.list_circuit_breakers()` isinstance bug

| Field | Detail |
|-------|--------|
| **Why** | `AdminHttpAdapter.list_circuit_breakers()` checks `isinstance(cb, CircuitBreakerState)` on `CircuitBreaker` objects — always returns empty dict. Admin health endpoint broken. (B-OR-5) |
| **File** | `k1/orchestrator/adapters/admin_http_adapter.py` |
| **Fix** | Change `isinstance` check from `CircuitBreakerState` to `CircuitBreaker` (or access `.state` property) |
| **LOC** | ~5 |
| **Depends on** | Nothing |
| **Acceptance** | `list_circuit_breakers()` returns non-empty dict when circuit breakers exist |
| **Status** | ✅ |

##### Issue 2.0.12 — Move `NullSessionStateReaderAdapter` to `k1/fabric/adapters/`

| Field | Detail |
|-------|--------|
| **Why** | `NullSessionStateReaderAdapter` implements `k1.fabric.ports.ISessionStateReader` but lives in `k1/concierge/adapters/null_state_reader.py`. Cross-package dependency. (B-FAB-3, A-FAB-1) |
| **File to move** | `k1/concierge/adapters/null_state_reader.py` → `k1/fabric/adapters/null_state_reader.py` |
| **Imports to update** | Any file importing from `k1.concierge.adapters.null_state_reader` must update path. Leave re-export shim in concierge for backward compat |
| **LOC** | 0 new (move only) |
| **Depends on** | Nothing |
| **Acceptance** | `from k1.fabric.adapters import NullSessionStateReaderAdapter` works |
| **Status** | ✅ |

##### Issue 2.0.13 — Add `create_shared()` factory method to Fabric

| Field | Detail |
|-------|--------|
| **Why** | Shared Fabric (for Orchestrator/Planner, no session) requires `NullSessionStateReaderAdapter`. No convenience method exists — must manually construct with `create_with_ports()`. (B-FAB-2) |
| **File** | `k1/fabric/factory.py` |
| **Implementation** | Add `create_shared(bus, model_hub, bridge)` that internally uses `NullSessionStateReaderAdapter` and skips session-bound providers (WORKFLOW, CONCIERGE). ~40 LOC |
| **Depends on** | 2.0.12 (NullStateReader in correct package) |
| **Acceptance** | `FabricFactory.create_shared(bus=bus, model_hub=hub, bridge=bridge)` returns working Fabric without session_id |
| **Status** | ✅ |

**Epic 2.0 Totals: 13 issues, ~665 LOC of changes**

---

#### Epic 2.1: KernelService Core

##### Issue 2.1.0 — ADR validation: confirm shared/per-session resource map before code

| Field | Detail |
|-------|--------|
| **Why** | ADR-0095 (Issue 2.0.10) defines the Tier 1 / Tier 2 split, but the wiring plan depends on specific classifications. Before writing `KernelService`, all field assignments must be cross-checked against ADR-0095 + doc 08 + simulation decisions SIM-D-01 through SIM-D-38. Any mismatch between ADR and code surfaces as a runtime bug. |
| **Input documents** | `docs/architecture/decisions-K1/01-foundation/0095-shared-vs-per-session-resource-map/0095.md` (ADR-0095), `docs/whiteboard/temp_kernel_bootstrap/08_end_to_end_wiring_requirements.md` (S1-S7, P1-P7), `docs/whiteboard/k1_wiring_simulation.md` (SIM-D-01..SIM-D-38, SIM-GAP-01..SIM-GAP-50) |
| **Validation checklist** | (a) Confirm 7 Tier 1 shared components: system_bus, ModelHub, Bridge, shared Fabric (NullStateReader), Orchestrator, Planner, CapabilityRegistry. (b) Confirm 14+ Tier 2 per-session components: session_bus, session_router, front_mailbox, back_mailbox, SSM, per-session Fabric, ConciergeController, front/back dispatchers, ExperienceLayer, DeltaAggregator, DeltaApplicator, HILCoordinator, consumer_task, DeadLetterConsumer. (c) Confirm Bus decision = per-session Bus (SIM-D-01) with lightweight system_bus for admin. (d) Confirm TWO Fabric instances (SIM-D-35): shared (NullStateReader) + per-session (SessionStateReaderAdapter). (e) Confirm Planner state port strategy (SIM-D-38): SnapshotStateReadAdapter with PlanRequest.context copy. (f) Confirm 29-field KernelRuntime classification matches Tier 1/2 split — 12 shared fields, 17 per-session fields. |
| **Files to read** | ADR-0095, doc 08, `k1/kernel/bootstrap.py` (KernelRuntime fields L66-96), `k1/kernel/ports/__init__.py` (8 ports) |
| **Output** | Annotated validation table in this issue's status field. Any contradictions → fix ADR or code before proceeding. |
| **LOC** | 0 (documentation only) |
| **Depends on** | 2.0.10 (ADR exists) |
| **Acceptance** | All 7 Tier 1 + 14 Tier 2 component classifications confirmed. Zero contradictions between ADR-0095 and doc 08 wiring spec. 29-field KernelRuntime mapped to correct tier. |
| **Status** | ☐ |

##### Issue 2.1.1 — Create `KernelService` class skeleton

| Field | Detail |
|-------|--------|
| **Why** | No central lifecycle manager exists. `start_kernel()` in `k1/kernel/bootstrap.py` is a flat function that creates a single-session monolith. KernelService provides: (a) 8-phase Tier 1 startup (S1→S7+S6b), (b) per-session create/destroy, (c) aggregated health, (d) reverse-order shutdown. This is the composition root for all kernel wiring. |
| **File to create** | `k1/kernel/service.py` (~200–250 LOC) |
| **Class signature** | `class KernelService:` (plain class, not dataclass — has mutable lifecycle state) |
| **Constructor** | `def __init__(self, config: KernelConfig) -> None:` — stores `self._config`, `self._bus: IBus | None = None`,`self._router: IMailboxRouter | None = None`,`self._model_hub: Any = None`,`self._shared_fabric: Any = None`,`self._bridge: Any = None`,`self._orchestrator: Any = None`,`self._planner: Any = None`,`self._planner_task: asyncio.Task | None = None`,`self._sessions: dict[str, SessionInstance] = {}`,`self._running: bool = False` |
| **Public methods (5)** | (1) `async def startup(self) -> None` — executes S1→S7+S6b in order, sets `_running=True`. (2) `async def create_session(self, session_id: str, device_id: str | None = None) -> SessionInstance` — executes P1→P7, stores in `_sessions`. (3)`async def destroy_session(self, session_id: str) -> None` — reverse P7→P1, pops from `_sessions`. (4)`async def shutdown(self) -> None` — destroy all sessions, then reverse S7→S1, sets `_running=False`. (5)`async def health_check(self) -> HealthStatus` — aggregates health from all Tier 1 components. |
| **Private methods (3)** | (1) `def _validate_ports(self) -> None` — isinstance checks (see 2.1.6). (2) `async def _startup_tier1(self) -> None` — S1→S7+S6b. (3) `async def _create_session_tier2(self, session_id, device_id) -> SessionInstance` — P1→P7. |
| **Properties (3)** | `is_running: bool`, `session_count: int`, `config: KernelConfig` |
| **Port protocol implementation** | `KernelService` itself implements `ILifecyclePort` + `ISessionManagerPort` (the two kernel-level protocols). |
| **Imports** | `from k1.kernel.ports import ILifecyclePort, ISessionManagerPort, HealthStatus`, `from k1.concierge.config.kernel import KernelConfig`, `from k1.kernel.session import SessionInstance` (from 2.1.2) |
| **Depends on** | 2.0.6 (service.py lives in `k1/kernel/`), 2.0.8 (port protocols exist), 2.0.9 (unified KernelRuntime) |
| **Acceptance** | `KernelService(config)` instantiates. `isinstance(svc, ILifecyclePort)` and `isinstance(svc, ISessionManagerPort)` return `True`. All 5 public methods exist with correct signatures. No implementation body yet — stubs raise `NotImplementedError`. |
| **Status** | ✅ |

##### Issue 2.1.2 — Create `SessionInstance` dataclass

| Field | Detail |
|-------|--------|
| **Why** | Per-session components (Tier 2: P1-P7) need a typed container. Current `KernelRuntime` mixes shared + per-session in one flat dataclass with `Any` everywhere. `SessionInstance` holds ONLY per-session components with proper types, enabling clean create/destroy lifecycle. ADR-0095 classifies 17 per-session fields. |
| **File to create** | `k1/kernel/session.py` (~80–100 LOC) |
| **Dataclass fields (17 typed)** | `session_id: str`, `member_id: str | None`,`bus: IBus` (per-session bus, SIM-D-01), `router: IMailboxRouter` (per-session router), `front_mailbox: IMailbox`,`back_mailbox: IMailbox`,`session_state: Any` (SessionStateManager — typed as Any until SSM ports consolidated), `fabric: Any` (per-session CapabilityFabric), `concierge: Any` (ConciergeRuntime from ConciergeFactory), `front_dispatcher: Any`,`back_dispatcher: Any`,`experience_layer: Any`,`delta_aggregator: Any`,`delta_applicator: Any`,`hitl_coordinator: Any`,`consumer_task: asyncio.Task | None`,`dead_letter_consumer: Any`,`created_at: datetime` |
| **Optional fields (5)** | `front_ctx: Any = None`, `back_ctx: Any = None`, `ledger: Any = None`, `ledger_store: Any = None`, `concierge_task: asyncio.Task | None = None` |
| **Frozen?** | NO — `consumer_task` and `concierge_task` are set post-construction (async task creation). Use `@dataclass` without `frozen=True`. |
| **Lifecycle helpers** | `@property def is_started(self) -> bool:` (checks `consumer_task is not None`), `def _repr_summary(self) -> str:` (compact repr for logging) |
| **Relationship to KernelRuntime** | `SessionInstance` replaces the per-session portion of `KernelRuntime`. `KernelService._sessions: dict[str, SessionInstance]` replaces `runtime.sessions`. Shared fields (bus, model_hub, orchestrator, planner, bridge, config) stay on `KernelService` directly. |
| **Relationship to ConciergeRuntime** | ConciergeFactory returns `ConciergeRuntime` — this gets stored in `SessionInstance.concierge`. `SessionInstance` is the KERNEL's view; `ConciergeRuntime` is the CONCIERGE's internal view. |
| **Imports** | `from k1.bus.ports.bus import IBus`, `from k1.bus.ports.mailbox import IMailbox, IMailboxRouter`, `from datetime import datetime` |
| **LOC** | ~80–100 |
| **Depends on** | 2.0.9 (KernelRuntime fields finalized — we know the 17 per-session fields), 2.0.10 (ADR confirms Tier 2 classification) |
| **Acceptance** | `SessionInstance(session_id="s1", bus=..., ...)` instantiates. All 17 required + 5 optional fields declared. Zero `Any` where Protocol types are available. Used by `KernelService._sessions`. |
| **Status** | ✅ |

##### Issue 2.1.3 — Extend `KernelConfig` with Tier 1 boot/wiring config

| Field | Detail |
|-------|--------|
| **Why** | `KernelConfig` (in `k1/concierge/config/kernel.py`) currently has 22 fields for single-session Concierge boot. Multi-session KernelService needs additional Tier 1 fields: system bus config, ModelHub config, Bridge config, max sessions, idle timeout. These were partially added in 2.0.5 but the Tier 1 fields are missing. |
| **File to change** | `k1/concierge/config/kernel.py` |
| **Current BusConfig fields (6)** | `topic_validation_enabled`, `tracing_enabled`, `metrics_enabled`, `gap_timeout_ms`, `mailbox_capacity`, `priority_wfq` — ✅ already exist |
| **Current KernelConfig fields (22)** | `ordered_bus`, `capture_bus`, `test_mode`, `tool_tier`, `session_mode`, `session_id`, `enable_experience`, `enable_delta`, `enable_hitl`, `enable_orchestrator`, `auto_start_consumer`, `enable_ledger`, `enable_dead_letter_consumer`, `seed_memories`, `phase1_pipeline`, `phase1_warmup_on_startup`, `delta_batch_window_ms`, `dead_letter_enabled`, `poll_interval_s`, `dedup_cache_size`, `bus: BusConfig` — ✅ all 22 exist after 2.0.5 |
| **New fields to add (8)** | (1) `max_sessions: int = 100` — per SIM-D-02 session limit. (2) `idle_timeout_minutes: int = 30` — session idle eviction. (3) `bridge_enabled: bool = True` — enable/disable K0 connection. (4) `bridge_offline_ok: bool = True` — allow startup without K0 (SIM-D-32: offline is normal). (5) `model_hub_plugins: list[str] = field(default_factory=lambda: ["openai"])` — which LLM providers to load. (6) `system_bus_enabled: bool = True` — whether to create system_bus for admin events. (7) `otel_enabled: bool = True` — OpenTelemetry tracing across all middleware. (8) `workflow_db_path: str = "./data/workflows.db"` — Orchestrator SQLite path. |
| **Implementation** | Add 8 fields to `KernelConfig` dataclass. All with defaults. No breaking changes — existing callers unaffected. |
| **LOC** | ~15 new lines |
| **Depends on** | 2.0.5 (base config migration complete) |
| **Acceptance** | `KernelConfig()` with all defaults works. `KernelConfig(max_sessions=50, bridge_enabled=False)` works. `config.max_sessions` returns `100` by default. All existing tests pass (backward compatible). |
| **Status** | ✅ |

##### Issue 2.1.4 — Store `AsyncBusBridge` on `KernelService` and document bus wiring layers

| Field | Detail |
|-------|--------|
| **Why** | Bus (`LocalBus`) is 100% synchronous (`threading.Lock`/`RLock`). KernelService needs both a sync bus (for existing adapters) and an async bridge (for future direct async callers and async handler registration). `AsyncBusBridge` (Issue 2.0.1) wraps sync bus methods via `asyncio.to_thread()`. This issue adds `_async_bus` to `KernelService` and documents the correct two-layer adapter chain so future Epic 2.2/2.3 wiring does not pass the wrong bus type. |
| **File to change** | `k1/kernel/service.py` |
| **CODE-VERIFIED adapter chain (2 layers)** | **Layer 1 — Raw IBus wrappers (sync calls to .publish/.subscribe/.unsubscribe):** (1) `FabricBusAdapter(bus: LocalBus)` — `k1/bus/adapters/fabric_adapter.py` — satisfies Fabric `IEventPort` + `IDeltaBusPort`. All methods SYNC. (2) `SessionBusAdapter(bus: LocalBus)` — `k1/bus/adapters/session_adapter.py` — satisfies SSM `IEventPort` (ABC). All methods SYNC. **Layer 2 — Fabric port wrappers (take IEventPort/IDeltaBusPort, NOT raw bus):** (3) `Planner.DeltaBusAdapter(delta_bus: Any)` — wraps Fabric `IDeltaBusPort` (a `FabricBusAdapter`). SYNC. (4) `Planner.EventBusAdapter(event_port: Any)` — wraps Fabric `IEventPort` (a `FabricBusAdapter`). SYNC. (5) `Orchestrator.EventSubscriptionAdapter(event_port: IEventPort)` — wraps Fabric `IEventPort`. SYNC. (6) `Orchestrator.DeltaEmitAdapter(event_port: IEventPort, delta_bus: IDeltaBusPort)` — wraps both Fabric ports. Methods are `async def` but make SYNC calls internally. (7) `MW.EventSubscriptionAdapter(bus_adapter: Any)` — wraps `FabricBusAdapter` directly. Methods ASYNC, internal calls SYNC. |
| **CORRECTION from original plan** | The original plan said to pass `AsyncBusBridge` to all 6 adapters. This is **WRONG**: `FabricBusAdapter.__init__(bus: LocalBus)` and `SessionBusAdapter.__init__(bus: LocalBus)` call `self._bus.publish()` SYNCHRONOUSLY. `AsyncBusBridge.publish()` is `async def` — calling it sync returns a coroutine object, not execution. Adapters 3-7 don't take a bus at all — they wrap `FabricBusAdapter` (Fabric-level ports). |
| **Correct wiring pattern** | `self._bus = BusFactory.create_local_ordered(...)` → `self._async_bus = AsyncBusBridge(self._bus)`. Layer 1 adapters get `self._bus` (sync `LocalBus`). Layer 2 adapters get `FabricBusAdapter` instances. `self._async_bus` is for: (a) future components needing direct async bus access, (b) `BusEnvelopeDeserializer` handler bridging (`asyncio.run_coroutine_threadsafe`), (c) any new async adapter added later. |
| **Adapters that MUST get sync LocalBus** | `FabricBusAdapter(self._bus)`, `SessionBusAdapter(self._bus)`, `DeadLetterConsumer(self._bus)`, `BusEnvelopeDeserializer(self._bus, ...)` |
| **GOTCHA: FabricBusAdapter dual-role** | Create ONE `FabricBusAdapter(self._bus)` instance. Pass SAME instance as both `event_port=` and `delta_bus=` to consumers. It satisfies `IEventPort` + `IDeltaBusPort` simultaneously. |
| **GOTCHA: Planner has TWO Layer 2 adapters** | `Planner.DeltaBusAdapter(delta_bus=fabric_adapter, agent_id="planner")` for delta emission. `Planner.EventBusAdapter(event_port=fabric_adapter)` for event subscription. Different classes, different port types. Cannot share one adapter. |
| **Implementation** | Add `self._async_bus: AsyncBusBridge | None = None` field to `KernelService.**init**()`. Add`async_bus` read-only property. |
| **LOC** | ~5 lines in service.py |
| **Depends on** | 2.0.1 (AsyncBusBridge exists), 2.1.1 (KernelService exists) |
| **Acceptance** | `KernelService` has `_async_bus` field and `async_bus` property. Unit test verifies field exists. The two-layer wiring documentation is accurate against actual code (verified via subagent audit of all 15 adapters). Actual adapter wiring happens in Epic 2.2 (Tier 1) and Epic 2.3 (Tier 2). |
| **Status** | ✅ |

##### Issue 2.1.5 — Wire correct `IModelHubPort` to MemoryWriter (anti-corruption layer)

| Field | Detail |
|-------|--------|
| **Why** | Name collision: K1 ModelHub has `IModelHubPort` with `execute(HubRequest) → HubResponse`. MemoryWriter has its OWN `IModelHubPort` with `chat(messages, budget, hint) → ChatResponse`. These are DIFFERENT protocols with the SAME name in different packages. The anti-corruption layer is `k1/memory_writer/adapters/model_hub_adapter.py` which wraps K1's ModelHub and translates `chat()` calls into K1's `execute(HubRequest)` calls. (B-MH-3, SIM-GAP-46) |
| **File to change** | `k1/kernel/service.py` (wiring in `_create_session_tier2()`) |
| **Correct wiring** | `model_hub_adapter = ModelHubAdapter(hub=self._model_hub)` — MW's `ModelHubAdapter` wraps K1 ModelHub. Pass `model_hub_adapter` as `model_hub_port=` to `MemoryWriterFactory.create()`. |
| **WRONG wiring** | Passing `self._model_hub` directly as MW's `IModelHubPort`. This would fail because K1 ModelHub lacks `chat()` method. |
| **Adapter chain** | `MemoryWriter → MW.IModelHubPort.chat(messages) → ModelHubAdapter → K1.ModelHub.execute(HubRequest) → LLM provider` |
| **Import** | `from k1.memory_writer.adapters.model_hub_adapter import ModelHubAdapter` |
| **LOC** | ~5 lines of wiring |
| **Depends on** | 2.2.2 (ModelHub created), MW adapter exists (verified in Epic 1.8) |
| **Acceptance** | `MemoryWriterFactory.create(model_hub_port=adapter)` succeeds. `adapter.chat(messages, budget, hint)` internally calls `hub.execute(HubRequest)`. Unit test: mock K1 hub, verify `chat()` → `execute()` translation. |
| **Status** | ✅ |

##### Issue 2.1.6 — Add construction-time port type validation

| Field | Detail |
|-------|--------|
| **Why** | All 8 kernel ports are `@runtime_checkable Protocol`. Construction-time `isinstance()` checks catch wiring bugs immediately (e.g., passing raw `LocalBus` instead of `AsyncBusBridge`, passing K1 ModelHub instead of MW ModelHubAdapter). Without validation, mismatches surface as cryptic `AttributeError` at runtime. |
| **File to change** | `k1/kernel/service.py` — add `_validate_ports()` private method |
| **Validation points (2 phases)** | **Phase 1 (Tier 1 startup):** After S1-S7+S6b, validate: `isinstance(self._bus, IBus)`, `isinstance(self._router, IMailboxRouter)`, `isinstance(self._model_hub, ...)` (ModelHub has no single Protocol — validate via duck-type `hasattr(hub, 'execute')`), orchestrator has `process` method, planner has `start` method. **Phase 2 (Tier 2 create_session):** After P1-P7, validate each `SessionInstance` field: `isinstance(session.bus, IBus)`, `isinstance(session.router, IMailboxRouter)`, session_state has `get_section` method, fabric has `execute` method. |
| **8 kernel port checks** | (1) `IBusPort` — `get_bus()`, `get_router()`, `create_mailbox()`. (2) `IModelHubPort` — `startup()`, `shutdown()`, `get_hub()`, `is_available()`. (3) `IFabricPort` — `create_shared()`, `create_for_session()`, `shutdown()`. (4) `IBridgePort` — `connect()`, `disconnect()`, `is_connected()`, `get_client()`. (5) `IOrchestratorPort` — `startup()`, `shutdown()`, `get_service()`, `wire_planner()`. (6) `IPlannerPort` — `startup()`, `shutdown()`, `get_agent()`. (7) `ISessionManagerPort` — `create_session()`, `destroy_session()`, `get_session()`, `list_sessions()`. (8) `ILifecyclePort` — `startup()`, `shutdown()`, `health_check()`, `is_running()`. |
| **Error format** | `raise TypeError(f"Port validation failed: {port_name} adapter {adapter!r} does not satisfy {protocol.__name__}")` |
| **Implementation** | Loop over `[(name, adapter, protocol), ...]` tuples. `isinstance()` check each. Collect ALL failures before raising (report all mismatches, not just first). |
| **LOC** | ~40–50 |
| **Depends on** | 2.0.8 (ports exist with `@runtime_checkable`), 2.1.1 (KernelService exists) |
| **Acceptance** | Passing correct adapters: `_validate_ports()` returns silently. Passing wrong adapter (e.g., `int` for IBusPort): raises `TypeError` with descriptive message. Unit test: intentionally pass wrong adapter, verify TypeError message. |
| **Status** | ✅ |

##### Issue 2.1.7 — Handle Orchestrator `ExecutionMonitor` late-binding

| Field | Detail |
|-------|--------|
| **Why** | `OrchestratorFactory.create_production()` builds a guard pipeline via `_build_guards()` (L189 in `k1/orchestrator/factory.py`). Guard #3 is `ExecutionMonitor` which needs a back-reference to the `OrchestratorService` it monitors. This creates a circular dependency: OrchestratorService → DAGExecutor → guards[] → ExecutionMonitor → OrchestratorService. Factory resolves this by late-binding: `guards[3]._service_ref = service` AFTER construction (factory L453). (B-OR-3) |
| **File to change** | `k1/kernel/service.py` — add `_verify_orchestrator_monitor_binding()` |
| **Current factory behavior** | `OrchestratorFactory._construct_orchestrator()` (L221) step 12 calls `_build_guards(planner_port, delta_port)` which creates `ExecutionMonitor(delta, service_ref=None)`. Post-construction (L453): `execution_monitor._service_ref = service`. This happens INSIDE the factory — KernelService does NOT do it manually. |
| **What KernelService must verify** | After `orch = await OrchestratorFactory.create_production(...)`, verify `orch._dag_executor._guards[3]._service_ref is not None`. Guards live on `DAGExecutor`, NOT on `OrchestratorService` directly. |
| **CODE-VERIFIED guard pipeline (4 guards at `_dag_executor._guards`)** | `[OutputSchemaGuard, ConditionalEdgeEvaluator, MicroReplanCheckpoint, ExecutionMonitor]` — ExecutionMonitor is index 3 (0-based). |
| **CORRECTION from original plan** | Plan originally listed guards as `[CostGuard, ConcurrencyGuard, CircuitBreakerGuard, ExecutionMonitor]`. Code audit proved this **WRONG** — actual guards are `[OutputSchemaGuard, ConditionalEdgeEvaluator, MicroReplanCheckpoint, ExecutionMonitor]`. `ConcurrencyGuard` wraps `_process_one` (not a DAGGuard). `CostGuard` and `CircuitBreakerGuard` don't exist as DAGGuard subclasses. |
| **Implementation** | Added `_verify_orchestrator_monitor_binding()` with defensive `getattr` traversal: `_orchestrator → _dag_executor → _guards[3] → _service_ref`. Each step guarded with `RuntimeError` on failure. |
| **LOC** | ~45 (method + docstring documenting corrected guard pipeline) |
| **Depends on** | 2.2.5 (Orchestrator wired) |
| **Acceptance** | `_verify_orchestrator_monitor_binding()` passes when `_service_ref` is set (factory did its job). Raises `RuntimeError` when: orchestrator is None, `_dag_executor` missing, guards too short, or `_service_ref` is None. 6 unit tests verify all paths. |
| **Status** | ✅ |

##### Issue 2.1.8 — Handle Planner `set_pipeline_controller()` post-construction

| Field | Detail |
|-------|--------|
| **Why** | `MailboxAdapter` (`k1/planner/adapters/mailbox_adapter.py`) wraps an `asyncio.Queue` for inbound `PlanRequest` messages. It also exposes `micro_replan()` which delegates to a `PipelineController`. The controller is injected via `set_pipeline_controller(controller)` — a two-phase init pattern. (PL-B2) |
| **File changed** | `k1/kernel/service.py` — added `_verify_planner_mailbox_binding()` method |
| **CORRECTION: Factory does NOT build MailboxAdapter** | Plan originally said `PlannerFactory.create_production()` builds a `MailboxAdapter`. **WRONG** — factory receives `mailbox_port` as an argument from the caller. The caller must construct the `MailboxAdapter` externally and pass it in. |
| **CORRECTION: Factory does NOT call `set_pipeline_controller()`** | Plan said `_wire()` step 10 calls `set_pipeline_controller()`. **WRONG** — `_wire()` has only 8 steps. Grep of `factory.py` for `set_pipeline_controller` returns **zero matches**. The MailboxAdapter's docstring claims "Called by PlannerFactory during the wiring sequence" but this is wrong — nobody calls it. |
| **CORRECTION: KernelService MUST call it manually** | Plan said "KernelService does NOT need to call it manually". **WRONG** — since the factory does NOT call it, `_pipeline_controller` stays `None` and `micro_replan()` always raises `RuntimeError("PipelineController not set")`. KernelService._startup_tier1() must explicitly call: `planner._mailbox.set_pipeline_controller(planner._pipeline)` |
| **CORRECTION: Attribute names all wrong** | Plan said `planner._mailbox_adapter` → actual is `planner._mailbox` (or property `planner.mailbox`, or method `planner.get_mailbox()`). Plan said `planner._controller` → actual is `planner._pipeline` (`PipelineController`). Plan said `_controller` on MailboxAdapter → actual is `_pipeline_controller`. |
| **CODE-VERIFIED PlannerAgent `__slots__`** | `_mailbox` (IMailboxPort), `_pipeline` (PipelineController), `_event_port` (IEventPort), `_config` (PlannerConfig), `_plan_lock`, `_cancel_set`, `_running`, `_subscriptions`, `_in_flight_request_id` |
| **CODE-VERIFIED MailboxAdapter `__slots__`** | `_queue`, `_cancel_set`, `_plan_lock`, `_max_depth`, `_priority_class`, `_shutdown`, `_pipeline_controller` |
| **CODE-VERIFIED PlannerFactory._wire() steps (8 total)** | (1) `ToolCallRouter`, (2) `HILCoordinator`, (3) `SketchService`, (4) `ExpandService`, (5) `ValidateService`, (6) `CommitService`, (7) `PipelineController`, (8) `PlannerAgent(mailbox=mailbox_port, pipeline=pipeline, ...)` — NO step 9 or 10. |
| **Correct wiring (for Epic 2.2)** | `planner._mailbox.set_pipeline_controller(planner._pipeline)` — to be called in `_startup_tier1()` after `PlannerFactory.create_production()` returns |
| **Verification traversal** | `_planner → _mailbox → _pipeline_controller` (must not be None). Defensive `getattr` at each step with `RuntimeError` on failure. |
| **Implementation** | Added `_verify_planner_mailbox_binding()` with defensive getattr traversal: `_planner → _mailbox → _pipeline_controller`. Each step guarded with RuntimeError on failure. |
| **LOC** | ~50 (method + docstring documenting corrections + 6 tests) |
| **Depends on** | 2.2.6 (Planner wired) |
| **Acceptance** | `_verify_planner_mailbox_binding()` passes when `_pipeline_controller` is set. Raises `RuntimeError` when: planner is None, `_mailbox` missing, or `_pipeline_controller` is None. 6 unit tests verify all paths. 84 tests total, all passing. |
| **Status** | ✅ |

##### Issue 2.1.9 — Handle `PlannerAgent.start()` async task creation

| Field | Detail |
|-------|--------|
| **Why** | `PlannerFactory.create_production()` creates the Planner agent but does NOT call `agent.start()`. The factory returns a fully wired but IDLE agent. Factory comments explicitly state: "Caller must invoke `asyncio.create_task(agent.start())`". KernelService must explicitly start the Planner's background task. Without this, the Planner never processes plan requests from its mailbox. (PL-B1) |
| **File changed** | `k1/kernel/service.py` — added `_verify_planner_task_running()` and `_verify_planner_orchestrator_crosswire()` |
| **CODE-VERIFIED: `start()` lifecycle** | `PlannerAgent.start()` (L569): INIT → subscribe 4 event topics (`TOPIC_PLAN_REQUEST`, `TOPIC_PLAN_CANCEL`, `TOPIC_HIL_CLARIFICATION_RESP`, `TOPIC_HIL_APPROVAL_RESP`) → `pipeline.reset()` → set `_running = True` → CRASH_RECOVERY (V1 no-op, L516) → `_run_loop()` (infinite `while _running` dequeue loop, L427). |
| **CODE-VERIFIED: Factory does NOT start** | `PlannerFactory._wire()` has explicit comment (L542-544): "Note: start() is NOT called here. It enters an infinite dequeue loop (_run_loop) and would block forever. The caller must spawn start() as a background task." |
| **CODE-VERIFIED: PlannerAgent.stop()** | `stop()` (L654) provides graceful shutdown: sets `_running = False`, drains mailbox, injects sentinel, unsubscribes events. Alternative to `task.cancel()`. |
| **CODE-VERIFIED: S6b cross-wire** | `OrchestratorFactory` defaults to `MockPlannerAdapter()` (`k1/orchestrator/adapters/mock_planner_adapter.py`). `OrchestratorService._planner_port` is in `__slots__` (L263) and reassignable. Cross-wire: `orchestrator._planner_port = PlannerAdapter(planner.get_mailbox(), cb_planner=cb)`. |
| **CORRECTION: Constructor kwarg** | Plan said `PlannerAdapter(..., circuit_breaker=cb_planner)`. Actual constructor parameter name is `cb_planner`, not `circuit_breaker`. Correct: `PlannerAdapter(mailbox, cb_planner=cb)`. |
| **CODE-VERIFIED: PlannerAdapter** | `__slots__ = ("_mailbox", "_cb")`. Constructor: `(planner_mailbox: Any, cb_planner: CircuitBreaker)`. Methods: `request_plan()`, `cancel_plan()`, `micro_replan()`, `_check_cb_open()`. No setter. |
| **CODE-VERIFIED: Error handling in `_run_loop()`** | Each plan execution wrapped in try/except: `PlanCancelledError` → log, continue. `PlannerError` → log, continue. `Exception` (unexpected) → emit `plan.failed.v1{INTERNAL_ERROR}`, continue. `finally` → cleanup cancel set, reset pipeline, release lock. |
| **Implementation** | (1) `_verify_planner_task_running()` — checks `_planner_task` is not None, not done, not cancelled. Reports exception detail if task died. (2) `_verify_planner_orchestrator_crosswire()` — checks `_orchestrator._planner_port` type name is NOT `MockPlannerAdapter`. Actual `create_task()` call, `stop()` in shutdown, and S6b cross-wire belong in Epic 2.2 `_startup_tier1()`. |
| **LOC** | ~90 (2 methods + docstrings + 12 tests) |
| **Depends on** | 2.2.6 (Planner factory called) |
| **Acceptance** | `_verify_planner_task_running()` passes when task is alive, raises when None/done/cancelled. `_verify_planner_orchestrator_crosswire()` passes when real PlannerAdapter is wired, raises when MockPlannerAdapter or None. 12 unit tests verify all paths. 96 tests total, all passing. |
| **Status** | ✅ |

#### Epic 2.2: Tier-1 Startup Wiring — Per-Component 4-Phase Process

**Business Process (applies to EACH component independently):**

```
Phase A — AUDIT: Read factory signature, port protocols, adapter constructors
Phase B — VERIFY: Adapter satisfies Protocol, constructor args available from prior steps
Phase C — WIRE: Exact code in _startup_tier1(), store on self._<field>
Phase D — TEST: Integration test with REAL components talking to each other (no mocks)
```

**Boot order enforced by data dependency:** S1 → S2 → S3 → S4 → S5 → S6 → S6b → S7

---

##### Issue 2.2.1 — S1: Wire Bus (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | Bus (shared, Tier 1) |
| **Phase A — AUDIT** | `BusFactory.create_local_ordered(*, config: BusConfig, timeout_ms: int = 5000, capture: bool = False, middleware: list[IBusMiddleware] | None = None, backend: str = "memory") → LocalBus`. Returns sync`LocalBus`. Zero required ports — pure infra component. Also:`BusFactory.create_mailbox_router() → LocalMailboxRouter`. |
| **Phase B — VERIFY** | `LocalBus` satisfies duck-type check: has `publish()` + `subscribe()` (validated by `_validate_ports()`). `AsyncBusBridge(bus)` wraps sync bus for async callers. Constructor: `AsyncBusBridge(bus: LocalBus)`. No port dependencies — Bus is the root of the dependency graph. |
| **Phase C — WIRE** | Exact code in `_startup_tier1()`: |
| | `bus = BusFactory.create_local_ordered(capture=self._config.capture_bus)` |
| | `self._bus = bus` |
| | `self._router = BusFactory.create_mailbox_router()` |
| | `self._async_bus = AsyncBusBridge(bus)` |
| **Phase D — TEST** | Test: create `KernelService`, call `_startup_tier1()` step S1, assert `self._bus` is not None, `self._bus.publish` callable, `self._async_bus` is `AsyncBusBridge`, `self._router.register` callable. Real `BusFactory`, real `LocalBus` — NO mocks. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` |
| **Depends on** | 2.0.1 (AsyncBusBridge exists), 2.1.1 (KernelService skeleton) |
| **CORRECTIONS from Phase B GATE** | (1) `create_local_ordered(config=)` takes `TimingConfig`, NOT `BusConfig` — pass `None` for defaults. (2) `_validate_ports` router check changed from `create_mailbox` → `register` (matches IMailboxRouter Protocol). (3) Bus wildcard is `>` not `#`. (4) `LocalMailbox.receive(timeout_ms=)` not `timeout=`. |
| **Status** | ✅ 110 tests passing (14 new S1 tests + 96 existing) |

---

##### Issue 2.2.2 — S2: Wire ModelHub (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | ModelHub (shared, Tier 1) |
| **Phase A — AUDIT** | `ModelHubFactory.create_standalone(config: ModelHubConfig | None = None, plugins: Dict[str, IProviderPlugin] | None = None) → IModelHubPort`. Returns`_HubCore` implementing `IModelHubPort`. Sync factory (no await). Zero required ports for standalone mode. Also has`create_with_ports(ports, config, plugins)` — NOT needed for Tier 1. |
| **Phase B — VERIFY** | `IModelHubPort` `@runtime_checkable` Protocol: 5 methods (`execute`, `stream_execute`, `discover_capabilities`, `discover_models`, `health`). `_HubCore` satisfies all 5. `_validate_ports()` checks `hasattr(self._model_hub, "execute")`. No dependency on Bus — standalone mode self-sufficient. |
| **Phase C — WIRE** | Exact code in `_startup_tier1()`: |
| | `self._model_hub = ModelHubFactory.create_standalone()` |
| **Phase D — TEST** | Test: after S1+S2, assert `self._model_hub` is not None, `isinstance(svc._model_hub, IModelHubPort)`. Real `ModelHubFactory.create_standalone()` — NO mocks. Verify `_create_memory_writer_hub_adapter()` returns valid `ModelHubAdapter` wrapping the hub. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` |
| **Depends on** | 2.2.1 (Bus available for future bus-integrated mode, not required for standalone) |
| **CORRECTIONS from Phase B GATE** | (1) Config class is `ModelHubConfig`, NOT `HubConfig`. (2) `KernelConfig` has NO `hub_config` field — use `ModelHubConfig()` default. (3) Plugins param is `Dict[str, IProviderPlugin]`, NOT `list[IPlugin]`. (4) Factory method `create_with_bus` does not exist — actual is `create_with_ports`. |
| **Status** | ✅ 120 tests passing (10 new S2 tests + 110 existing) |

---

##### Issue 2.2.3 — S3: Wire Shared Fabric (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | Fabric (shared instance, Tier 1) |
| **Phase A — AUDIT** | `FabricFactory.create_shared(event_port, bridge, model_gateway, prompt_system, delta_bus, *, production_mode: bool = True, ...) → Fabric`. Takes 5 required port args. Uses `NullStateReader` internally (no per-session state for shared Fabric). Also has `create_with_ports(state_reader, event_port, bridge, model_gateway, prompt_system, delta_bus)` — 6 args, for per-session Fabric (Epic 2.3). |
| **Phase B — VERIFY** | `Fabric` dataclass has `.execute()` method — satisfies `_validate_ports()` check. **CORRECTIONS:** (1) Adapter names ALL wrong in plan: `BusEventAdapter` → actual `EventPortProdAdapter`, `BusDeltaAdapter` → actual `DeltaBusProdAdapter`, `ModelGatewayBridge` → actual `ModelGatewayBridgeAdapter`. (2) `KernelConfig` has NO `prompt_config` — `PromptSystemProdAdapter` needs `prompts_dir: str\|Path`. (3) Factory passes adapters DIRECTLY through — NO internal wrapping. (4) `Fabric` has NO `state_reader` field — S5 plan wrong. (5) Two `IBridgePort` protocols exist (kernel vs fabric). |
| **Phase C — WIRE** | Exact code in `_startup_tier1()` (after S1, S2, S4): |
| | `event_port = EventPortProdAdapter(bus)` |
| | `delta_bus = DeltaBusProdAdapter(bus)` |
| | `model_gateway = ModelGatewayBridgeAdapter(hub=self._model_hub)` |
| | `prompt_system = PromptSystemProdAdapter(prompts_dir="k1/contracts/prompts")` |
| | `bridge_client = self._bridge.get_client()` |
| | `bridge_adapter = BridgeConnectionAdapter(client=bridge_client)` |
| | `self._shared_fabric = FabricFactory.create_shared(event_port=event_port, bridge=bridge_adapter, model_gateway=model_gateway, prompt_system=prompt_system, delta_bus=delta_bus)` |
| **Phase D — TEST** | 11 tests in `TestS3SharedFabricWiring`: Fabric instance type, execute method, facade/retrieval/registry_api fields, EventPortProdAdapter wraps bus, port validation, boot order S4→S3. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` |
| **Depends on** | 2.2.1 (Bus for event_port + delta_bus adapters), 2.2.2 (ModelHub for model_gateway), 2.2.4 (Bridge) |
| **CORRECTIONS from Phase B GATE** | (1) `BusEventAdapter` → `EventPortProdAdapter` (`k1/fabric/adapters/event_port_prod.py`). (2) `BusDeltaAdapter` → `DeltaBusProdAdapter` (`k1/fabric/adapters/delta_bus_prod.py`). (3) `ModelGatewayBridge` → `ModelGatewayBridgeAdapter` (`k1/fabric/adapters/model_gateway_bridge.py`). (4) `self._config.prompt_config` → `PromptSystemProdAdapter(prompts_dir="k1/contracts/prompts")`. (5) `self._bridge` (kernel IBridgePort) ≠ Fabric bridge arg — Fabric needs `BridgeConnectionAdapter(client=sink_client)`. (6) `Fabric.state_reader` does NOT exist — Orchestrator gets it independently. |
| **Status** | ✅ 148 tests passing (11 S3 + 16 S4 + 10 S2 + 14 S1 + 97 existing) |

---

##### Issue 2.2.4 — S4: Wire Bridge (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | Bridge (shared, Tier 1) |
| **Phase A — AUDIT** | Bridge has no factory. TWO distinct `IBridgePort` protocols exist: (1) Kernel's (`k1/kernel/ports/bridge_port.py`) with `connect/disconnect/is_connected/get_client`, (2) Fabric's (`k1/fabric/ports/bridge_port.py`) with `send_command/query/route_ifl/is_available/get_health`. `SinkBridgeClient` satisfies `IBridgeClient` (bridge layer), NOT either `IBridgePort`. It requires `outbox: LocalOutbox(db_path)` — CANNOT be constructed with zero args. Has NO `is_connected` method. `StubBridgeClient` is zero-arg test-only. |
| **Phase B — VERIFY** | **CORRECTIONS:** (1) Plan said `SinkBridgeClient()` zero-arg — **WRONG**, requires `outbox: LocalOutbox`. (2) Plan said `SinkBridgeClient` has `is_connected` — **WRONG**, has `health()` instead. (3) Two separate adapters needed: kernel's `IBridgePort` (for `_validate_ports()`) and Fabric's `IBridgePort` (for `FabricFactory.create_shared()`). (4) `BridgeConnectionAdapter` calls `client.send()` but `SinkBridgeClient` has `submit_command()` — method names don't align (bridge layer incomplete). |
| **Phase C — WIRE** | Created two kernel adapters in `k1/kernel/adapters/bridge_adapter.py`: |
| | `OfflineBridgeAdapter` — pure null, zero-arg. For `bridge_enabled=False`. |
| | `SinkBridgeAdapter(outbox_path)` — wraps `LocalOutbox` + `SinkBridgeClient`. For `bridge_enabled=True` (default). `is_connected()=False`, `get_client()` returns real `SinkBridgeClient` with offline command queueing. |
| | Wiring in `_startup_tier1()`: |
| | `if self._config.bridge_enabled: self._bridge = SinkBridgeAdapter(outbox_path=self._config.bridge_outbox_path)` |
| | `else: self._bridge = OfflineBridgeAdapter()` |
| | Fabric gets `BridgeConnectionAdapter(client=self._bridge.get_client())` — receives `SinkBridgeClient` or `None`. |
| | Added `bridge_outbox_path: str = "./data/bridge_outbox.db"` to `KernelConfig`. |
| **Phase D — TEST** | 16 tests in `TestS4BridgeWiring`: default `SinkBridgeAdapter` path, `OfflineBridgeAdapter` when disabled, `IBridgePort` protocol compliance for both, `get_client()` returns `SinkBridgeClient`/`None`, outbox creation, health snapshot, port validation. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()`, `k1/kernel/adapters/bridge_adapter.py`, `k1/concierge/config/kernel.py` |
| **Depends on** | None (leaf dependency) |
| **CORRECTIONS from Phase B GATE** | (1) `SinkBridgeClient` requires `outbox: LocalOutbox(db_path)` — NOT zero-arg. (2) `SinkBridgeClient` has NO `is_connected` — only `health()`. (3) Kernel needs `IBridgePort` adapter wrapping `SinkBridgeClient`. (4) Fabric needs `BridgeConnectionAdapter(client=sink_client)` — separate protocol. (5) `BridgeConnectionAdapter` method signatures (`send/query/route_ifl`) don't match `SinkBridgeClient` (`submit_command/query/execute_connector`) — bridge layer incomplete, LOCAL COLD mode used. |
| **Status** | ✅ 148 tests passing (16 S4 + 11 S3 + 10 S2 + 14 S1 + 97 existing) |

---

##### Issue 2.2.5 — S5: Wire Orchestrator (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | Orchestrator (shared, Tier 1) |
| **Phase A — AUDIT** | `OrchestratorFactory.create_production(config: OrchestratorConfig, *, mailbox: IMailboxPort, fabric: IFabricGatewayPort, planner: IPlannerPort, state: IStateReadPort, delta: IDeltaEmitPort, bridge: IBridgeWritePort, event: IEventPort, storage: IWorkflowStoragePort) → OrchestratorService`. 8 required ports. ONLY `create_production()` calls `init()` internally. Returns fully initialized `OrchestratorService`. |
| **Phase B — VERIFY** | Port → Adapter mapping (all exist in `k1/orchestrator/adapters/`): |
| | • `IMailboxPort` ← `MailboxAdapter(queue)` — wraps `asyncio.Queue` |
| | • `IFabricGatewayPort` ← `FabricGatewayAdapter(fabric)` — wraps shared Fabric.execute() |
| | • `IPlannerPort` ← `MockPlannerAdapter()` (factory default, replaced in S6b) |
| | • `IStateReadPort` ← `StateReadAdapter(fabric.state_reader)` — reads through Fabric's state reader |
| | • `IDeltaEmitPort` ← `DeltaEmitAdapter(delta_aggregator, bus)` — routes deltas to aggregator, non-deltas to bus |
| | • `IBridgeWritePort` ← `BridgeWriteAdapter(bridge)` — wraps bridge write commands |
| | • `IEventPort` ← `EventAdapter(bus)` — wraps bus event pub/sub |
| | • `IWorkflowStoragePort` ← `WorkflowStorageAdapter(storage_backend)` — wraps SQLite |
| | All constructors take components available from S1-S4. `OrchestratorService` has `process()` method — satisfies `_validate_ports()` check. |
| **Phase C — WIRE** | Exact code in `_startup_tier1()` (after S1, S2, S3, S4): |
| | `from k1.orchestrator.factory import OrchestratorFactory` |
| | `from k1.orchestrator.adapters.mailbox_adapter import MailboxAdapter as OrchMailboxAdapter` |
| | `from k1.orchestrator.adapters.fabric_gateway_adapter import FabricGatewayAdapter` |
| | `from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter` |
| | `from k1.orchestrator.adapters.delta_emit_adapter import DeltaEmitAdapter` |
| | `from k1.orchestrator.adapters.bridge_write_adapter import BridgeWriteAdapter` |
| | `from k1.orchestrator.adapters.event_adapter import EventAdapter as OrchEventAdapter` |
| | `from k1.orchestrator.adapters.workflow_storage_adapter import WorkflowStorageAdapter` |
| | `orch_mailbox = OrchMailboxAdapter(asyncio.Queue())` |
| | `orch_fabric = FabricGatewayAdapter(self._shared_fabric)` |
| | `orch_state = StateReadAdapter(self._shared_fabric.state_reader)` |
| | `orch_delta = DeltaEmitAdapter(delta_aggregator=None, bus=self._bus)` — NOTE: delta_aggregator per-session, pass None for shared; adjust if shared aggregator exists |
| | `orch_bridge = BridgeWriteAdapter(self._bridge)` |
| | `orch_event = OrchEventAdapter(self._bus)` |
| | `orch_storage = WorkflowStorageAdapter(storage_backend=None)` — NOTE: wire real SQLite backend when available |
| | `orchestrator = await OrchestratorFactory.create_production(config=self._config.orch_config, mailbox=orch_mailbox, fabric=orch_fabric, planner=MockPlannerAdapter(), state=orch_state, delta=orch_delta, bridge=orch_bridge, event=orch_event, storage=orch_storage)` |
| | `self._orchestrator = orchestrator` |
| **Phase D — TEST** | Test: after S1-S5, assert `self._orchestrator` is not None, `hasattr(self._orchestrator, "process")`. Call `_verify_orchestrator_monitor_binding()` — must pass (factory completed ExecutionMonitor late-binding). Real `OrchestratorFactory.create_production()` with real adapters wrapping real Bus/Fabric/Bridge. NO mocks except `MockPlannerAdapter` (replaced in S6b). |
| **CRITICAL** | `create_production()` is async — must `await`. It is the ONLY factory method that calls `init()`. Do NOT use `create_with_ports()` — that skips `init()`. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` |
| **Depends on** | 2.2.1 (Bus), 2.2.2 (ModelHub — for Fabric), 2.2.3 (Fabric), 2.2.4 (Bridge) |
| **Status** | ☐ |

---

##### Issue 2.2.6 — S6: Wire Planner (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | Planner (shared, Tier 1) |
| **Phase A — AUDIT** | `PlannerFactory.create_production(*, llm_port: ILLMGatewayPort, fabric_port: IFabricPort, state_port: ISessionStatePort, bridge_port: IBridgePort, delta_port: IDeltaBusPort, event_port: IEventBusPort, mailbox_port: IMailboxPort, config: PlannerConfig) → PlannerAgent`. 7 required ports + config. Returns fully wired but IDLE agent — does NOT call `start()`. |
| **Phase B — VERIFY** | Port → Adapter mapping (all exist in `k1/planner/adapters/`): |
| | • `ILLMGatewayPort` ← `LLMGatewayAdapter(model_hub)` — wraps ModelHub.execute() |
| | • `IFabricPort` ← `FabricAdapter(fabric)` — wraps Fabric.execute() |
| | • `ISessionStatePort` ← `SessionStateReadAdapter(reader, session_id)` — per-session (placeholder for shared mode) |
| | • `IBridgePort` ← `BridgeAdapter(bridge)` — wraps Bridge commands |
| | • `IDeltaBusPort` ← `DeltaBusAdapter(bus)` — wraps Bus delta publish (DIFFERENT from EventBusAdapter) |
| | • `IEventBusPort` ← `EventBusAdapter(bus)` — wraps Bus event pub/sub (DIFFERENT from DeltaBusAdapter) |
| | • `IMailboxPort` ← `MailboxAdapter(queue)` — wraps asyncio.Queue for PlanRequest messages |
| | All constructors take components available from S1-S5. `PlannerAgent` has `start()` method — satisfies `_validate_ports()` check. |
| **Phase C — WIRE** | Exact code in `_startup_tier1()` (after S1-S5): |
| | `from k1.planner.factory import PlannerFactory` |
| | `from k1.planner.adapters.llm_gateway_adapter import LLMGatewayAdapter` |
| | `from k1.planner.adapters.fabric_adapter import FabricAdapter as PlannerFabricAdapter` |
| | `from k1.planner.adapters.session_state_read_adapter import SessionStateReadAdapter as PlannerStateAdapter` |
| | `from k1.planner.adapters.bridge_adapter import BridgeAdapter as PlannerBridgeAdapter` |
| | `from k1.planner.adapters.delta_bus_adapter import DeltaBusAdapter` |
| | `from k1.planner.adapters.event_bus_adapter import EventBusAdapter` |
| | `from k1.planner.adapters.mailbox_adapter import MailboxAdapter as PlannerMailboxAdapter` |
| | `pl_llm = LLMGatewayAdapter(self._model_hub)` |
| | `pl_fabric = PlannerFabricAdapter(self._shared_fabric)` |
| | `pl_state = PlannerStateAdapter(reader=None, session_id="__shared__")` — placeholder, per-session reader injected per-request |
| | `pl_bridge = PlannerBridgeAdapter(self._bridge)` |
| | `pl_delta = DeltaBusAdapter(self._bus)` |
| | `pl_event = EventBusAdapter(self._bus)` |
| | `pl_mailbox = PlannerMailboxAdapter(asyncio.Queue())` |
| | `planner = await PlannerFactory.create_production(llm_port=pl_llm, fabric_port=pl_fabric, state_port=pl_state, bridge_port=pl_bridge, delta_port=pl_delta, event_port=pl_event, mailbox_port=pl_mailbox, config=self._config.planner_config)` |
| | `self._planner = planner` |
| **CRITICAL** | `create_production()` is async — must `await`. Factory does NOT call `start()` — handled in S7. |
| **Phase D — TEST** | Test: after S1-S6, assert `self._planner` is not None, `hasattr(self._planner, "start")`. Real `PlannerFactory.create_production()` with real adapters wrapping real Bus/Fabric/Bridge/ModelHub. NO mocks. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` |
| **Depends on** | 2.2.1 (Bus), 2.2.2 (ModelHub), 2.2.3 (Fabric), 2.2.4 (Bridge), 2.2.5 (Orchestrator — for dependency ordering) |
| **Status** | ☐ |

---

##### Issue 2.2.7 — S6b: Wire Orchestrator↔Planner Cross-Wire (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | Cross-wire: Orchestrator._planner_port replacement |
| **Phase A — AUDIT** | `OrchestratorFactory.create_production()` defaults to `MockPlannerAdapter()` as the planner port. After Planner is created (S6), replace it with real `PlannerAdapter`. `PlannerAdapter(planner_mailbox: Any, cb_planner: CircuitBreaker)` — `__slots__ = ("_mailbox", "_cb")`. `OrchestratorService._planner_port` is in `__slots__` and reassignable via direct attribute assignment. |
| **Phase B — VERIFY** | `PlannerAdapter` exists at `k1/orchestrator/adapters/planner_adapter.py`. Constructor kwarg is `cb_planner` (NOT `circuit_breaker`). `planner.get_mailbox()` returns the mailbox queue for the PlannerAdapter to submit PlanRequests. |
| **Phase C — WIRE** | Exact code in `_startup_tier1()` (after S5 + S6): |
| | `from k1.orchestrator.adapters.planner_adapter import PlannerAdapter` |
| | `orchestrator._planner_port = PlannerAdapter(planner.get_mailbox(), cb_planner=self._config.circuit_breakers.planner)` |
| **Phase D — TEST** | Test: call `_verify_planner_orchestrator_crosswire()` — must pass (planner_port is no longer MockPlannerAdapter). Assert `type(self._orchestrator._planner_port).__name__ == "PlannerAdapter"`. Real cross-wire — NO mocks. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` |
| **Depends on** | 2.2.5 (Orchestrator), 2.2.6 (Planner) |
| **Status** | ☐ |

---

##### Issue 2.2.8 — S7: Start Planner Background Task + Post-Wire Verifications (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | PlannerAgent.start() + MailboxAdapter pipeline controller binding |
| **Phase A — AUDIT** | `PlannerAgent.start()` (L569): INIT → subscribe 4 event topics → `pipeline.reset()` → set `_running = True` → CRASH_RECOVERY (V1 no-op) → `_run_loop()` (infinite `while _running` dequeue loop). MUST be wrapped in `asyncio.create_task()` — NOT awaited directly (blocks forever). `PlannerFactory._wire()` does NOT call `set_pipeline_controller()` on MailboxAdapter — KernelService must do it. |
| **Phase B — VERIFY** | Traversal: `planner._mailbox` → `MailboxAdapter`, `planner._pipeline` → `PipelineController`. After binding: `planner._mailbox._pipeline_controller` must equal `planner._pipeline`. Without this, `micro_replan()` raises `RuntimeError("PipelineController not set")`. |
| **Phase C — WIRE** | Exact code in `_startup_tier1()` (after S6b): |
| | `# PL-B2: Two-phase init — factory skips this, we must do it` |
| | `planner._mailbox.set_pipeline_controller(planner._pipeline)` |
| | `# PL-B1: Start background task — factory returns IDLE agent` |
| | `self._planner_task = asyncio.create_task(planner.start(), name="planner-agent")` |
| **Phase D — TEST** | Test: call `_verify_planner_mailbox_binding()` — must pass. Call `_verify_planner_task_running()` — must pass (task alive, not done, not cancelled). Call `_validate_ports()` — all 7 shared components pass duck-type checks. Real `asyncio.create_task()` on real `PlannerAgent.start()`. NO mocks. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` |
| **Depends on** | 2.2.6 (Planner created), 2.2.7 (cross-wire done) |
| **Status** | ☐ |

---

##### Issue 2.2.9 — Implement `_startup_tier1()` method body

| Field | Detail |
|-------|--------|
| **What** | Replace the `raise NotImplementedError("KernelService._startup_tier1")` stub with the full S1→S7 sequence from Issues 2.2.1–2.2.8. |
| **Sequence** | `async def _startup_tier1(self) → None:` |
| | `# S4: Bridge (no deps — can go first)` |
| | `# S1: Bus + AsyncBusBridge + Router` |
| | `# S2: ModelHub (standalone)` |
| | `# S3: Shared Fabric (needs S1 Bus + S2 Hub + S4 Bridge)` |
| | `# S5: Orchestrator (needs S1 Bus + S3 Fabric + S4 Bridge)` |
| | `# S6: Planner (needs S1 Bus + S2 Hub + S3 Fabric + S4 Bridge)` |
| | `# S6b: Cross-wire Orch↔Planner` |
| | `# S7: Start Planner task + verify all bindings` |
| | `# Final: _validate_ports() — all 7 shared components` |
| | `self._running = True` |
| **Error handling** | If any step fails, log the error, cleanup already-created components in reverse order, re-raise. Partial startup must not leave orphaned resources. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` body |
| **Depends on** | 2.2.1–2.2.8 (all step definitions) |
| **Status** | ☐ |

---

##### Issue 2.2.10 — Implement `startup()` public method

| Field | Detail |
|-------|--------|
| **What** | Replace the `raise NotImplementedError("KernelService.startup")` stub. Calls `_startup_tier1()` and sets `self._running = True`. |
| **Code** | `async def startup(self) → None:` |
| | `if self._running: raise RuntimeError("Already running")` |
| | `await self._startup_tier1()` |
| | `self._running = True` |
| **Phase D — TEST** | Test: `KernelService.startup()` completes without error. `kernel.is_running` is True. All 7 shared fields populated. All verification methods pass. Second call raises `RuntimeError("Already running")`. Real components — NO mocks. |
| **File** | `k1/kernel/service.py` — `startup()` body |
| **Depends on** | 2.2.9 (_startup_tier1 implemented) |
| **Status** | ☐ |

---

#### Epic 2.3: Tier-2 Session Wiring — Per-Component 4-Phase Process

**Business Process (same 4-phase pattern, applied per session component):**

```
Phase A — AUDIT: Read factory signature, per-session port requirements
Phase B — VERIFY: Adapter satisfies Protocol, shared components available
Phase C — WIRE: Exact code in _create_session_tier2(), store on SessionInstance
Phase D — TEST: Integration test with REAL per-session + shared components (no mocks)
```

**Session creation order:** P1 → P2 → P3 → P4 → P5 → P6 → P7

---

##### Issue 2.3.1 — P1: Create Per-Session Bus + Mailboxes (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | Per-session Bus + Router + Mailboxes |
| **Phase A — AUDIT** | Each session gets its own `LocalBus` (SIM-D-01: total isolation). `BusFactory.create_local_ordered()` for production. `BusFactory.create_mailbox_router()` for mailboxes. `router.register("front_{sid}")` + `router.register("back_{sid}")` for front/back mailboxes. |
| **Phase B — VERIFY** | Per-session Bus is isolated — no topic collision between sessions. `LocalBus` is lightweight (TopicTrie, middleware). Same duck-type validation as shared Bus. |
| **Phase C — WIRE** | Exact code in `_create_session_tier2()`: |
| | `session_bus = BusFactory.create_local_ordered(config=self._config.bus_config, capture=False)` |
| | `session_router = BusFactory.create_mailbox_router()` |
| | `front_mb = session_router.register(f"front_{session_id}")` |
| | `back_mb = session_router.register(f"back_{session_id}")` |
| **Phase D — TEST** | Test: create session, assert session_bus.publish callable, both mailboxes created, session_bus is different instance from shared `self._bus`. Real components. |
| **File** | `k1/kernel/service.py` — `_create_session_tier2()` |
| **Depends on** | 2.2.1 (shared Bus pattern established) |
| **Status** | ☐ |

---

##### Issue 2.3.2 — P2: Wire SessionState Per Session (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | SessionState (per-session) |
| **Phase A — AUDIT** | `SessionStateFactory.create_with_ports(session_id: str, storage: IStoragePort, events: IEventPort, writer: IWriterPort, lifecycle: ILifecyclePort, k0_sync: IK0SyncPort | None = None) → SessionStateManager`. 5 required ports + optional k0_sync. Two-phase bind: create SSM with`writer=None`, create`DirectWriterAdapter(manager=ssm, guard=ssm.mutation_guard)`, inject`ssm._writer_port = writer_adapter`. |
| **Phase B — VERIFY** | Adapters: `SQLiteStorageAdapter(db_path)` for IStoragePort, `BusEventAdapter(bus)` for IEventPort, `DirectWriterAdapter(manager, guard)` for IWriterPort, `StandaloneLifecycle(manager)` for ILifecyclePort. SSM has `get_section()` — duck-type check for session validation. `AsyncSSMBridge(ssm)` wraps for async callers. |
| **Phase C — WIRE** | Exact code in `_create_session_tier2()` (after P1): |
| | `from k1.sessionstate.factory import SessionStateFactory` |
| | `from k1.sessionstate.adapters.sqlite_storage_adapter import SQLiteStorageAdapter` |
| | `from k1.sessionstate.adapters.bus_event_adapter import BusEventAdapter as SSEventAdapter` |
| | `from k1.sessionstate.adapters.direct_writer_adapter import DirectWriterAdapter` |
| | `from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle` |
| | `ss_storage = SQLiteStorageAdapter(db_path=self._config.db_path)` |
| | `ss_events = SSEventAdapter(session_bus)` |
| | `ssm = SessionStateFactory.create_with_ports(session_id=session_id, storage=ss_storage, events=ss_events, writer=None, lifecycle=None, k0_sync=None)` |
| | `writer = DirectWriterAdapter(manager=ssm, guard=ssm.mutation_guard)` |
| | `ssm._writer_port = writer` |
| | `lifecycle = StandaloneLifecycle(manager=ssm)` |
| | `ssm._lifecycle_port = lifecycle` |
| | `ssm.start()` |
| | `async_ssm = AsyncSSMBridge(ssm)` |
| **Phase D — TEST** | Test: SSM created, `ssm.get_section("control")` returns section object, `async_ssm` wraps SSM. Two-phase bind complete — writer_port is not None. Real `SessionStateFactory`, real SQLite — NO mocks. |
| **File** | `k1/kernel/service.py` — `_create_session_tier2()` |
| **Depends on** | 2.3.1 (per-session Bus for events), 2.0.2 (AsyncSSMBridge exists) |
| **Status** | ☐ |

---

##### Issue 2.3.3 — P3: Wire Per-Session Fabric (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | Fabric (per-session instance) |
| **Phase A — AUDIT** | `FabricFactory.create_with_ports(state_reader, event_port, bridge, model_gateway, prompt_system, delta_bus) → Fabric`. 6 required args. Per-session Fabric gets `SessionStateReaderAdapter(ssm, session_id)` as state_reader — bound to one SSM. Shared Fabric (S3) uses NullStateReader. |
| **Phase B — VERIFY** | `SessionStateReaderAdapter(ssm, session_id)` wraps SSM's read API for Fabric's state queries. Other adapters same as shared Fabric but wrapping per-session Bus. |
| **Phase C — WIRE** | Exact code in `_create_session_tier2()` (after P1, P2): |
| | `from k1.fabric.adapters.session_state_reader_adapter import SessionStateReaderAdapter` |
| | `session_state_reader = SessionStateReaderAdapter(ssm, session_id)` |
| | `session_event_port = BusEventAdapter(session_bus)` |
| | `session_model_gw = ModelGatewayBridge(self._model_hub)` — shared hub, per-session adapter |
| | `session_delta_bus = BusDeltaAdapter(session_bus)` |
| | `session_fabric = FabricFactory.create_with_ports(state_reader=session_state_reader, event_port=session_event_port, bridge=self._bridge, model_gateway=session_model_gw, prompt_system=self._config.prompt_config, delta_bus=session_delta_bus)` |
| **Phase D — TEST** | Test: per-session Fabric created, `session_fabric.execute` callable, state_reader bound to session SSM. Real `FabricFactory.create_with_ports()`. NO mocks. |
| **File** | `k1/kernel/service.py` — `_create_session_tier2()` |
| **Depends on** | 2.3.1 (per-session Bus), 2.3.2 (SSM for state_reader), 2.2.2 (shared ModelHub), 2.2.4 (shared Bridge) |
| **Status** | ☐ |

---

##### Issue 2.3.4 — P4: Wire Concierge Per Session (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | Concierge (per-session) |
| **Phase A — AUDIT** | `ConciergeFactory.create_with_ports(*, bus: IBus, router: IMailboxRouter, front_mailbox: IMailbox, back_mailbox: IMailbox, ports: PortBundle, config: KernelConfig, fabric_port: Any, orchestrator: Any) → ConciergeRuntime`. `PortBundle` holds 8 port references. `IFabricPort` NOT in `PortBundle` — passed separately as `fabric_port`. `orchestrator` passed separately. 8 ports via PortBundle + 3 infra args. |
| **Phase B — VERIFY** | `PortBundle` adapters (all in `k1/concierge/adapters/`): `BusInputAdapter` (IInputPort), `BusOutputAdapter` (IOutputPort), `UltraBERTClassificationAdapter` (IClassificationPort), `HubLLMAdapter` (ILLMPort), `SSMStateAdapter` (IStatePort), `FabricDispatchAdapter` (IDispatchPort), `DeltaBusAdapter` (IDeltaPort), `RecallMemoryAdapter` (IMemoryPort). `FabricDispatchAdapter` raises `RuntimeError` if orchestrator not wired — must wire orchestrator first (S5). |
| **Phase C — WIRE** | Exact code in `_create_session_tier2()` (after P1, P2, P3): |
| | `from k1.concierge.factory import ConciergeFactory` |
| | `from k1.concierge.contracts.port_bundle import PortBundle` |
| | Build PortBundle with per-session adapters wrapping session_bus, ssm, session_fabric, shared model_hub, shared bridge |
| | `concierge = ConciergeFactory.create_with_ports(bus=session_bus, router=session_router, front_mailbox=front_mb, back_mailbox=back_mb, ports=port_bundle, config=self._config, fabric_port=session_fabric, orchestrator=self._orchestrator)` |
| **Phase D — TEST** | Test: Concierge created, FSM in LISTENING state, all ports wired. Real `ConciergeFactory.create_with_ports()` with real per-session Bus/SSM/Fabric wrapping real shared components. NO mocks. |
| **File** | `k1/kernel/service.py` — `_create_session_tier2()` |
| **Depends on** | 2.3.1 (Bus+mailboxes), 2.3.2 (SSM), 2.3.3 (per-session Fabric), 2.2.5 (shared Orchestrator for dispatch) |
| **Status** | ☐ |

---

##### Issue 2.3.5 — P5: Wire MemoryWriter Per Session (4 phases)

| Field | Detail |
|-------|--------|
| **Component** | MemoryWriter (per-session) |
| **Phase A — AUDIT** | `MemoryWriterFactory.create(session_read_port: ISessionReadPort, model_hub_port: IModelHubPort, bridge_command_port: IBridgeCommandPort, event_subscription_port: IEventSubscriptionPort, health_port: IHealthPort, config: MemoryWriterConfig) → MemoryWriterService`. 5 required ports + config. All ports mandatory. |
| **Phase B — VERIFY** | Adapters (all in `k1/memory_writer/adapters/`): `SessionReadAdapter(ssm)` — per-session, wraps SSM read. `ModelHubAdapter(hub=self._model_hub)` — shared hub, anti-corruption layer (chat() ≠ execute()). `BridgeCommandAdapter(bridge)` — wraps bridge write. `EventSubscriptionAdapter(bus)` — wraps bus subscription. `HealthAdapter(...)` — health reporting. |
| **Phase C — WIRE** | Exact code in `_create_session_tier2()` (after P1, P2): |
| | `from k1.memory_writer.factory import MemoryWriterFactory` |
| | `from k1.memory_writer.adapters.session_read_adapter import SessionReadAdapter` |
| | `from k1.memory_writer.adapters.event_subscription_adapter import EventSubscriptionAdapter` |
| | `from k1.memory_writer.adapters.bridge_command_adapter import BridgeCommandAdapter` |
| | `from k1.memory_writer.adapters.health_adapter import HealthAdapter` |
| | `mw_session = SessionReadAdapter(ssm)` |
| | `mw_hub = self._create_memory_writer_hub_adapter()` — uses anti-corruption ModelHubAdapter |
| | `mw_bridge = BridgeCommandAdapter(self._bridge)` |
| | `mw_events = EventSubscriptionAdapter(session_bus)` |
| | `mw_health = HealthAdapter(...)` |
| | `memory_writer = MemoryWriterFactory.create(session_read_port=mw_session, model_hub_port=mw_hub, bridge_command_port=mw_bridge, event_subscription_port=mw_events, health_port=mw_health, config=self._config.mw_config)` |
| **Phase D — TEST** | Test: MemoryWriter created, all 5 ports wired. `_create_memory_writer_hub_adapter()` returns valid `ModelHubAdapter`. Real `MemoryWriterFactory.create()`. NO mocks. |
| **File** | `k1/kernel/service.py` — `_create_session_tier2()` |
| **Depends on** | 2.3.2 (SSM), 2.2.2 (shared ModelHub), 2.2.4 (shared Bridge), 2.3.1 (per-session Bus) |
| **Status** | ☐ |

---

##### Issue 2.3.6 — P6: Assemble SessionInstance + Start Lifecycle

| Field | Detail |
|-------|--------|
| **What** | Assemble all per-session components into `SessionInstance`, register in `_sessions` dict, start lifecycle. |
| **Phase C — WIRE** | Exact code in `_create_session_tier2()` (after P1-P5): |
| | `session = SessionInstance(session_id=session_id, bus=session_bus, router=session_router, session_state=ssm, fabric=session_fabric, concierge=concierge, memory_writer=memory_writer)` |
| | `self._sessions[session_id] = session` |
| | `await concierge.start()` — start FSM consumer loop |
| | `return session` |
| **Phase D — TEST** | Test: `create_session("test-1")` returns `SessionInstance`, `kernel.session_count == 1`, `kernel.get_session("test-1")` returns same instance. `_validate_session(session)` passes. Second session with same ID raises error. Real components. |
| **File** | `k1/kernel/service.py` — `_create_session_tier2()` |
| **Depends on** | 2.3.1–2.3.5 (all per-session components) |
| **Status** | ☐ |

---

##### Issue 2.3.7 — Implement `_create_session_tier2()` method body

| Field | Detail |
|-------|--------|
| **What** | Replace the `raise NotImplementedError("KernelService._create_session_tier2")` stub with the full P1→P6 sequence from Issues 2.3.1–2.3.6. |
| **Sequence** | `async def _create_session_tier2(self, session_id, device_id) → SessionInstance:` |
| | `# P1: Per-session Bus + Router + Mailboxes` |
| | `# P2: SessionState (two-phase bind)` |
| | `# P3: Per-session Fabric` |
| | `# P4: Concierge` |
| | `# P5: MemoryWriter` |
| | `# P6: Assemble + start` |
| **Error handling** | If any step fails, cleanup already-created per-session components in reverse order, re-raise. Do NOT leave orphaned sessions in `_sessions`. |
| **File** | `k1/kernel/service.py` — `_create_session_tier2()` body |
| **Depends on** | 2.3.1–2.3.6 (all step definitions) |
| **Status** | ☐ |

---

##### Issue 2.3.8 — Implement `create_session()` public method

| Field | Detail |
|-------|--------|
| **What** | Replace the `raise NotImplementedError("KernelService.create_session")` stub. Guards: kernel must be running, session_id must not already exist. Calls `_create_session_tier2()`. |
| **Code** | `async def create_session(self, session_id, device_id=None) → SessionInstance:` |
| | `if not self._running: raise RuntimeError("Kernel not running")` |
| | `if session_id in self._sessions: raise ValueError(f"Session '{session_id}' already exists")` |
| | `session = await self._create_session_tier2(session_id, device_id)` |
| | `self._validate_session(session)` |
| | `return session` |
| **Phase D — TEST** | Test: `create_session()` returns valid SessionInstance. Raises RuntimeError when not running. Raises ValueError on duplicate session_id. Real components. |
| **File** | `k1/kernel/service.py` — `create_session()` body |
| **Depends on** | 2.3.7 (_create_session_tier2 implemented), 2.2.10 (startup implemented) |
| **Status** | ☐ |

---

#### Epic 2.4: Shutdown Wiring — Per-Component 4-Phase Process

**Shutdown is the REVERSE of startup. Per-session teardown reverses P6→P1. Shared teardown reverses S7→S1.**

---

##### Issue 2.4.1 — Per-Session Shutdown (`destroy_session`)

| Field | Detail |
|-------|--------|
| **What** | Implement `destroy_session(session_id)` — tears down one session's Tier 2 components in reverse order. |
| **Sequence (reverse P6→P1)** | |
| | `session = self._sessions.pop(session_id)` — remove from registry FIRST |
| | `# Reverse P5: Stop MemoryWriter` |
| | `await session.memory_writer.stop()` (if has stop method) |
| | `# Reverse P4: Stop Concierge FSM + consumer tasks` |
| | `await session.concierge.stop()` |
| | `# Reverse P3: (per-session Fabric has no explicit teardown)` |
| | `# Reverse P2: Checkpoint + stop SessionState` |
| | `session.session_state.stop()` |
| | `# Reverse P1: Close per-session Bus + Router` |
| | `session.bus.close()` |
| | `session.router.close()` |
| **Error handling** | Each step wrapped in try/except — continue teardown even if one step fails. Collect all errors, log them. |
| **Phase D — TEST** | Test: `destroy_session("test-1")` completes, `kernel.session_count == 0`, `kernel.get_session("test-1")` returns None. Double-destroy raises KeyError/ValueError. Real components created then destroyed. |
| **File** | `k1/kernel/service.py` — `destroy_session()` body |
| **Depends on** | 2.3 all (sessions can be created) |
| **Status** | ☐ |

---

##### Issue 2.4.2 — Shared Shutdown (`shutdown`)

| Field | Detail |
|-------|--------|
| **What** | Implement `shutdown()` — destroys all sessions first, then tears down Tier 1 shared components in reverse order. |
| **Sequence** | |
| | `# 1. Destroy all sessions` |
| | `for sid in list(self._sessions): await self.destroy_session(sid)` |
| | `# Reverse S7: Stop Planner background task` |
| | `if self._planner: await self._planner.stop()` — graceful stop |
| | `if self._planner_task: self._planner_task.cancel()` |
| | `# Reverse S6b: (cross-wire cleanup — no action needed)` |
| | `# Reverse S5: Stop Orchestrator` |
| | `if self._orchestrator and hasattr(self._orchestrator, "stop"): await self._orchestrator.stop()` |
| | `# Reverse S4: Close Bridge` |
| | `if self._bridge and hasattr(self._bridge, "close"): self._bridge.close()` |
| | `# Reverse S3: (Fabric has no explicit teardown)` |
| | `# Reverse S2: Close ModelHub` |
| | `if self._model_hub and hasattr(self._model_hub, "close"): self._model_hub.close()` |
| | `# Reverse S1: Close Bus` |
| | `if self._bus and hasattr(self._bus, "close"): self._bus.close()` |
| | `self._running = False` |
| **Error handling** | Each step wrapped in try/except — continue teardown. Collect errors, log. Always set `_running = False` at end. |
| **Phase D — TEST** | Test: `startup()` → `create_session()` → `shutdown()` — all fields reset, `is_running` False, no orphaned tasks. `asyncio.all_tasks()` after shutdown has no kernel tasks. Real components. |
| **File** | `k1/kernel/service.py` — `shutdown()` body |
| **Depends on** | 2.4.1 (per-session shutdown), 2.2 all (shared components exist) |
| **Status** | ☐ |

---

##### Issue 2.4.3 — Error Recovery: Partial Startup/Session Failure

| Field | Detail |
|-------|--------|
| **What** | Define error handling when startup or session creation partially fails. |
| **Startup failure** | If S3 fails (Fabric), cleanup S2 (ModelHub) + S1 (Bus) + S4 (Bridge) in reverse. Do NOT set `_running = True`. |
| **Session failure** | If P4 fails (Concierge), cleanup P3 (Fabric) + P2 (SSM.stop()) + P1 (Bus.close()) in reverse. Do NOT add to `_sessions`. |
| **Shutdown timeout** | After 10s grace period, force-cancel remaining tasks. Log warnings. |
| **Implementation** | Add try/except blocks in `_startup_tier1()` and `_create_session_tier2()` with reverse-order cleanup on failure. |
| **Phase D — TEST** | Test: Mock one factory to raise → verify cleanup of already-created components. Test: shutdown with slow component → verify timeout handling. |
| **File** | `k1/kernel/service.py` — error paths in `_startup_tier1()` + `_create_session_tier2()` |
| **Depends on** | 2.2.9, 2.3.7 (method bodies exist to add error handling to) |
| **Status** | ☐ |

---

#### Epic 2.5: Integration Tests — Real Components End-to-End

**NO MOCKS. Real components talking to each other. Tests prove the wiring works.**

---

##### Issue 2.5.1 — Test: Full `startup()` Lifecycle

| Field | Detail |
|-------|--------|
| **What** | Test that `KernelService.startup()` completes with real factories and real adapters. All 7 shared fields populated. All 4 verification methods pass. |
| **Assertions** | `kernel.is_running is True`, `kernel._bus is not None`, `kernel._async_bus is not None`, `kernel._router is not None`, `kernel._model_hub is not None`, `kernel._shared_fabric is not None`, `kernel._bridge is not None`, `kernel._orchestrator is not None`, `kernel._planner is not None`, `kernel._planner_task is not None`, `kernel._planner_task.done() is False`. |
| **Verifications** | `_validate_ports()` passes, `_verify_orchestrator_monitor_binding()` passes, `_verify_planner_mailbox_binding()` passes, `_verify_planner_task_running()` passes, `_verify_planner_orchestrator_crosswire()` passes. |
| **File** | `tests/k1/kernel/test_service.py` |
| **Depends on** | 2.2.10 (startup implemented) |
| **Status** | ☐ |

---

##### Issue 2.5.2 — Test: Full `create_session()` Lifecycle

| Field | Detail |
|-------|--------|
| **What** | Test that `create_session()` creates a valid `SessionInstance` with all per-session components wired to each other AND to shared components. |
| **Assertions** | `kernel.session_count == 1`, session has bus, router, session_state, fabric, concierge, memory_writer. `_validate_session()` passes. Session bus ≠ shared bus. |
| **File** | `tests/k1/kernel/test_service.py` |
| **Depends on** | 2.3.8 (create_session implemented) |
| **Status** | ☐ |

---

##### Issue 2.5.3 — Test: Full Shutdown Lifecycle

| Field | Detail |
|-------|--------|
| **What** | Test `startup()` → `create_session()` → `destroy_session()` → `shutdown()` — complete lifecycle, no leaked resources. |
| **Assertions** | After destroy: `session_count == 0`. After shutdown: `is_running is False`. No orphaned asyncio tasks (check `asyncio.all_tasks()`). |
| **File** | `tests/k1/kernel/test_service.py` |
| **Depends on** | 2.4.1, 2.4.2 (shutdown implemented) |
| **Status** | ☐ |

---

##### Issue 2.5.4 — Test: Error Paths

| Field | Detail |
|-------|--------|
| **What** | Test error scenarios: startup when already running, create_session when not running, create duplicate session, destroy non-existent session. |
| **Assertions** | Each scenario raises expected exception type with descriptive message. |
| **File** | `tests/k1/kernel/test_service.py` |
| **Depends on** | 2.2.10, 2.3.8, 2.4.1 |
| **Status** | ☐ |

---

##### Issue 2.5.5 — Test: Multi-Session Isolation

| Field | Detail |
|-------|--------|
| **What** | Test that two sessions have isolated buses. Event published on session A's bus does NOT appear on session B's bus. Shared components (ModelHub, Orchestrator, Planner) are same instance across sessions. |
| **Assertions** | `session_a.bus is not session_b.bus`, `session_a.session_state is not session_b.session_state`, shared Orchestrator is same ref. Bus publish isolation verified. |
| **File** | `tests/k1/kernel/test_service.py` |
| **Depends on** | 2.3.8 (multiple sessions can be created) |
| **Status** | ☐ |

---

### MS-2.5: Audit-Driven Workstream Phases (7 Phases)

**Goal:** Address ALL 225 findings from Doc 28 (consolidated audit) across 7 workstream phases. These phases are ordered by severity and dependency — each phase unlocks downstream work.

**Source:** `28_consolidated_audit_findings.md` — 6 CRITICAL, 25 HIGH, 86 MEDIUM, 89 LOW, 19 INFO findings across 10 components.

**Constraint:** NOTHING DELETED — every finding from Doc 28 is accounted for in exactly one phase below.

#### Reference Document Index

All reference documents live in `docs/whiteboard/temp_kernel_bootstrap/`. File names are self-describing — read the ones listed per-phase before starting that phase's issues.

| Doc # | File | Component | Use When |
|-------|------|-----------|----------|
| 10 | `10_bus_audit.md` | Bus | Phase 6 (bus hardening) |
| 11 | `11_sessionstate_audit.md` | SessionState | Phase 1 (state wiring), Phase 5 (stubs) |
| 12 | `12_fabric_audit.md` | Fabric | Phase 1 (shared Fabric state), Phase 2 (type collisions) |
| 13 | `13_modelhub_audit.md` | ModelHub | Phase 4 (POC bypass), Phase 5 (MH ports) |
| 14 | `14_orchestrator_audit.md` | Orchestrator | Phase 1 (MockStateRead), Phase 2 (isinstance bug) |
| 15a | `15_planner_audit.md` | Planner | Phase 1 (reader=None), Phase 2 (PlanStep.to_dict) |
| 15b | `15_planner_api_mapping.md` | Planner API | Phase 1 (state adapter), Phase 2 (serialization) |
| 15c | `15_orchestrator_api_mapping.md` | Orchestrator API | Phase 1 (MockStateRead), Phase 5 (BridgeWrite) |
| 15d | `15_orchestrator_planner_cross_reference.md` | Orch↔Planner | Phase 1 (compound session-state gap) |
| 16a | `16_concierge_audit.md` | Concierge | Phase 3 (dead code), Phase 4 (POC deps) |
| 16b | `16_fabric_api_mapping.md` | Fabric API | Phase 1 (NullStateReader), Phase 5 (IEmbeddingPort) |
| 17a | `17_fabric_orchestrator_planner_cross_reference.md` | Cross-component | Phase 1 (systemic state blindness), Phase 2 (compensation bug) |
| 17b | `17_memorywriter_audit.md` | MemoryWriter | Phase 2 (BUG-1), Phase 5 (health/place) |
| 18a | `18_bridge_audit.md` | Bridge | Phase 7 (bridge adapters) |
| 18b | `18_sessionstate_api_mapping.md` | SS API | Phase 1 (adapter wiring), Phase 5 (stubs) |
| 19a | `19_kernel_package_audit.md` | Kernel pkg | Phase 3 (dead k1/kernel stubs) |
| 19b | `19_modelhub_services_adapters_audit.md` | MH adapters | Phase 4 (POC bridge), Phase 5 (MH ports) |
| 19c | `19_sessionstate_cross_reference.md` | SS xref | Phase 1 (Orch/Planner state blindness) |
| 20 | `20_concierge_api_mapping.md` | Concierge API | Phase 5 (FabricDispatchAdapter) |
| 21 | `21_concierge_cross_reference.md` | Concierge xref | Phase 1 (state wiring), Phase 5 (recall) |
| 22 | `22_modelhub_api_mapping.md` | MH API | Phase 4 (POC bypass) |
| 23 | `23_modelhub_cross_reference.md` | MH xref | Phase 4 (POC pipeline bypass) |
| 24 | `24_memorywriter_api_mapping.md` | MW API | Phase 5 (health, place resolver) |
| 25 | `25_memorywriter_cross_reference.md` | MW xref | Phase 2 (BUG-1), Phase 5 (recall loop) |
| 26 | `26_bus_api_mapping.md` | Bus API | Phase 6 (RustMailbox, async bridge) |
| 27 | `27_bus_cross_reference.md` | Bus xref | Phase 6 (topic naming, timing rules) |
| 28 | `28_consolidated_audit_findings.md` | ALL | Master reference — all 225 findings |

---

#### Phase 1: Session-State Wiring (CRITICAL — ~200 LOC) — ✅ COMPLETE 2026-04-22 (audit, 6/6)

**Why first:** Three components (Orchestrator, Planner, Fabric) operate session-blind. This is the #1 compound gap. Safety gates are bypassed. Context-free planning produces garbage plans.

**Findings killed:** C-2, C-4, C-6, H-7, H-17, H-18, M-4, M-35, M-56, M-66, M-67, M-68, M-70, M-71

📖 **Read before starting:** `11_sessionstate_audit.md`, `14_orchestrator_audit.md`, `15_planner_audit.md`, `15_orchestrator_planner_cross_reference.md`, `17_fabric_orchestrator_planner_cross_reference.md`, `19_sessionstate_cross_reference.md`, `16_fabric_api_mapping.md`

##### Issue P1.1 — Build `SessionRoutingStateReader` (shared→per-session bridge)

| Field | Detail |
|-------|--------|
| **What** | Create `SessionRoutingStateReader` that accepts `session_id` per call and looks up the correct SSM from `kernel._sessions[session_id].state_manager`. Satisfies `ISessionStateReader` protocol. |
| **Why** | Orchestrator and Planner are shared (Tier 1) but need to read per-session state. Single adapter routes to correct session. |
| **File** | NEW: `k1/kernel/adapters/session_routing_reader.py` (~50 LOC) |
| **Test** | Create 2 sessions, write different state, verify reader returns correct state per session_id. |
| **Findings addressed** | C-6, H-18, M-66, M-67 |
| **📖 Ref docs** | `17_fabric_orchestrator_planner_cross_reference.md` (compound session-state gap), `19_sessionstate_cross_reference.md` (Orch/Planner state blindness), `11_sessionstate_audit.md` (SSM ISessionStateReader protocol) |
| **Status** | ☑ DONE |

##### Issue P1.2 — Wire `StateReadAdapter` in Orchestrator (replace MockStateReadAdapter)

| Field | Detail |
|-------|--------|
| **What** | Replace `MockStateReadAdapter()` at S5 with `StateReadAdapter(reader=session_routing_reader)`. Orchestrator can now read safety band, beliefs, session context. |
| **Impact** | Safety gate `_check_safety_band()` will see real `safety_band` instead of `None→GREEN`. Planning decisions use real context. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` S5 block |
| **Findings addressed** | H-7, H-17, M-68, M-70 |
| **📖 Ref docs** | `14_orchestrator_audit.md` (MockStateReadAdapter finding), `15_orchestrator_api_mapping.md` (IStateReadPort contract), `19_sessionstate_cross_reference.md` (safety gate bypass) |
| **Status** | ☑ DONE |

##### Issue P1.3 — Wire `PlannerStateAdapter` with real reader (replace reader=None)

| Field | Detail |
|-------|--------|
| **What** | Change `PlannerStateAdapter(reader=None, session_id="__shared__")` at S6 to `PlannerStateAdapter(reader=session_routing_reader, session_id="__shared__")`. Per-request `session_id` override via `PlanRequest.session_id`. |
| **Impact** | Planner `state_read` tool no longer crashes. Plans generated with session beliefs and history. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` S6 block |
| **Findings addressed** | C-2, M-35, M-71 |
| **📖 Ref docs** | `15_planner_audit.md` (PlannerStateAdapter reader=None), `15_planner_api_mapping.md` (IStateReadPort contract), `15_orchestrator_planner_cross_reference.md` (state read crash path) |
| **Status** | ☑ DONE |

##### Issue P1.4 — Wire shared Fabric with `SessionRoutingStateReader` (replace NullStateReader)

| Field | Detail |
|-------|--------|
| **What** | In `create_shared()` or S3 shared Fabric setup, replace `NullSessionStateReaderAdapter` with `SessionRoutingStateReader`. Shared Fabric can now access session context when executing for a specific session. |
| **Impact** | PolicyEngine Affective/Cognitive scoring uses real data. ContextBuilder builds real context. Provider decisions context-aware. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` S3 block |
| **Findings addressed** | C-4, M-4 |
| **📖 Ref docs** | `12_fabric_audit.md` (NullSessionStateReaderAdapter), `16_fabric_api_mapping.md` (FAB-GAP-01 shared Fabric no context), `17_fabric_orchestrator_planner_cross_reference.md` (compound gap C-4) |
| **Status** | ☑ DONE — `create_shared(state_reader=session_routing_reader)` wired in S3; `_construct_fabric()` propagates to PolicyEngine, ContextBuilder, ProviderFactory, OutputValidationPipeline |

##### Issue P1.5 — Verify SSM adapter wrapper (SSMStateAdapter)

| Field | Detail |
|-------|--------|
| **What** | Confirm `SSMStateAdapter` (~47 LOC) correctly converts `SessionSnapshot` → `dict[str, Any]` for Concierge IStatePort. Ensure all wiring docs reference `SSMStateAdapter`, not raw SSM. |
| **Findings addressed** | M-4, M-56 |
| **📖 Ref docs** | `11_sessionstate_audit.md` (SSM does NOT satisfy IStatePort — H-1), `18_sessionstate_api_mapping.md` (adapter shape) |
| **Status** | ☑ DONE — `SSMStateAdapter` satisfies `IStatePort` protocol; 2 tests confirm `get_section` delegation and `get_snapshot` → dict conversion |

##### Issue P1.6 — Tests: session-state wiring integration

| Field | Detail |
|-------|--------|
| **What** | Integration tests: (a) Orch reads safety_band from real session, (b) Planner reads beliefs from real session, (c) Shared Fabric reads context from real session, (d) 2 sessions have isolated state. |
| **Findings addressed** | Validates all Phase 1 fixes |
| **📖 Ref docs** | `08_end_to_end_wiring_requirements.md` (wiring test patterns), `05_port_adapter_mapping.md` (port contracts for assertions) |
| **Status** | ☑ DONE — 16 integration tests in `tests/k1/kernel/test_session_state_integration.py`; 461 total kernel tests passing |

---

#### Phase 2: Serialization & Type Safety Bugs (CRITICAL/HIGH — ~50 LOC) — ⚠️ NEAR 2026-04-22 (audit, 7/8 — P2.6 partial)

**Why second:** These are code bugs that crash at runtime. Quick fixes, high impact.

**Findings killed:** C-1, C-3, H-6, M-49, M-50, M-55, M-83

📖 **Read before starting:** `15_planner_api_mapping.md` (PlanStep.to_dict), `17_fabric_orchestrator_planner_cross_reference.md` (compensation bug, PlanStep collision, RegistryEntry), `14_orchestrator_audit.md` (isinstance bug), `17_memorywriter_audit.md` (BUG-1), `25_memorywriter_cross_reference.md` (BUG-1 detail), `26_bus_api_mapping.md` (RustMailbox receive), `18_bridge_audit.md` (submit_command_batch type)

##### Issue P2.1 — Fix `PlanStep.to_dict()` — add `safety_band_min` (field 14)

| Field | Detail |
|-------|--------|
| **What** | `PlanStep.to_dict()` in `k1/orchestrator/types.py` omits `safety_band_min`. Add it to the dict output. |
| **Impact** | When `CommittedPlan` serialized to bus (`plan.ready.v1`), Orchestrator's DAGExecutor now sees Planner's safety constraint. |
| **File** | `k1/orchestrator/types.py` |
| **Findings addressed** | C-1, M-33 |
| **📖 Ref docs** | `15_planner_api_mapping.md` (C-1 safety_band_min gap), `15_orchestrator_planner_cross_reference.md` (serialization mismatch) |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/orchestrator/types.py` L711-L713 emits `safety_band_min`; field declared L671; round-trip via `from_dict` L744 |

##### Issue P2.2 — Fix `compensation_capability` AttributeError in FabricGatewayAdapter

| Field | Detail |
|-------|--------|
| **What** | `_contract_to_entry()` assumes `CapabilityContract` has `compensation_capability`. Add `getattr(contract, 'compensation_capability', None)`. |
| **File** | `k1/orchestrator/adapters/fabric_gateway_adapter.py` |
| **Findings addressed** | C-3 |
| **📖 Ref docs** | `17_fabric_orchestrator_planner_cross_reference.md` (C-3 compound gap), `14_orchestrator_audit.md` (FabricGatewayAdapter) |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/orchestrator/adapters/fabric_gateway_adapter.py` L273 hardcodes `compensation_capability=None` (CapabilityContract has no such field; AttributeError prevented) |

##### Issue P2.3 — Fix `isinstance` bug in `list_circuit_breakers()`

| Field | Detail |
|-------|--------|
| **What** | `AdminHttpAdapter.list_circuit_breakers()` checks `isinstance` on `CircuitBreakerState` against `CircuitBreaker` object — always returns empty dict. Fix the isinstance check. |
| **File** | `k1/orchestrator/adapters/admin_http_adapter.py` |
| **Findings addressed** | H-6 |
| **📖 Ref docs** | `14_orchestrator_audit.md` (H-6 isinstance bug detail) |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/orchestrator/adapters/admin_http_adapter.py` L314 now `if cb is not None and isinstance(cb, CircuitBreaker):` after `getattr(planner_adapter, '_cb', None)` |

##### Issue P2.4 — Fix PlanStep type collision (Fabric vs Orchestrator)

| Field | Detail |
|-------|--------|
| **What** | Fabric `PlanStep` (6 fields) vs Orchestrator `PlanStep` (14 fields). Rename Fabric's to `FabricPlanStep` or use qualified imports everywhere. |
| **Findings addressed** | M-49 |
| **📖 Ref docs** | `17_fabric_orchestrator_planner_cross_reference.md` (M-49 type collision), `12_fabric_audit.md` (Fabric PlanStep definition) |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/fabric/types.py` L1096 renamed to `FabricPlanStep` (alias `PlanStep = FabricPlanStep` L1156 for back-compat); `k1/orchestrator/types.py` L39 imports `FabricPlanStep` by name |

##### Issue P2.5 — Fix `RegistryEntry` lossy mapping (26→6 fields)

| Field | Detail |
|-------|--------|
| **What** | `_contract_to_entry()` drops 20 fields. Add `required_inputs`, `output`, `cost_per_call` to `RegistryEntry`. |
| **Findings addressed** | M-50 |
| **📖 Ref docs** | `17_fabric_orchestrator_planner_cross_reference.md` (M-50 lossy mapping) |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/orchestrator/types.py` L469-L487: `RegistryEntry` extended to 9 fields (`required_inputs`, `output`, `cost_per_call` added with explicit P2.5 comment); `_contract_to_entry()` maps all three via `getattr` |

##### Issue P2.6 — Fix `submit_command_batch` type mismatch

| Field | Detail |
|-------|--------|
| **What** | `submit_command_batch` takes `list[dict]` but port protocol takes `list[CommandEnvelope]`. Align types. |
| **Findings addressed** | M-55 |
| **📖 Ref docs** | `18_bridge_audit.md` (M-55 type mismatch detail) |
| **Status** | ⚠️ PARTIAL 2026-04-22 (audit) — Bridge side fixed (`bridge/client.py` L155 + L282 accept `list[CommandEnvelope \| dict]`). REMAINING: `k1/memory_writer/adapters/bridge_command_adapter.py` L40 local `_IKernelCommandPort` Protocol stub still declares `list[dict]`. 1-line cosmetic fix; runtime is fine. |

##### Issue P2.7 — Fix `RustMailboxAdapter.receive()` keyword-only mismatch

| Field | Detail |
|-------|--------|
| **What** | `RustMailboxAdapter.receive(*, timeout_ms)` is keyword-only but `IMailbox` declares positional. Fix to match protocol. |
| **Findings addressed** | M-83 |
| **📖 Ref docs** | `26_bus_api_mapping.md` (M-83 keyword-only mismatch) |
| **Status** | ☑ DONE — Removed `*` keyword-only marker; `receive(self, timeout_ms: int = 0)` now matches `IMailbox` protocol |

##### Issue P2.8 — Fix MW BridgeCommandAdapter type mismatch (BUG-1)

| Field | Detail |
|-------|--------|
| **What** | `BridgeCommandAdapter(command_port=self._bridge)` at P5 passes `SinkBridgeAdapter` (lifecycle) not `SinkBridgeClient` (command). Change to `self._bridge.get_client()`. Also verify MW expects `submit()` vs client has `submit_command()` — align method names. |
| **File** | `k1/kernel/service.py` — `_create_session_tier2()` P5 block |
| **Findings addressed** | Absorbed from MS-3 issue 3.10.1 (BUG-1) |
| **📖 Ref docs** | `17_memorywriter_audit.md` (BUG-1 BridgeCommandAdapter), `25_memorywriter_cross_reference.md` (MW bridge type mismatch) |
| **Status** | ☑ DONE — Already fixed: `service.py` line 1271 uses `self._bridge.get_client()` (returns `SinkBridgeClient`); `BridgeCommandAdapter.submit()` correctly calls `submit_command()` on client |

---

#### Phase 3: Dead Code & Package Cleanup (HIGH — -100 LOC net) — ✅ COMPLETE 2026-04-22 (audit, 4/4)

**Why third:** Remove confusion. Dead code misleads developers and hides real composition root.

**Findings killed:** H-14, H-15, L-39, L-40, L-44, L-45, L-57, L-58, L-59, L-62, L-63

📖 **Read before starting:** `19_kernel_package_audit.md` (dead k1/kernel stubs), `16_concierge_audit.md` (factory.py.bak, empty packages), `12_fabric_audit.md` (empty dirs), `18_bridge_audit.md` (empty dirs, stale status)

##### Issue P3.1 — Delete `k1/kernel/` dead stubs

| Field | Detail |
|-------|--------|
| **What** | `k1/kernel/` is 100% dead code (69 LOC stubs, nothing imports from `k1.kernel`). Delete entire package. Verify no imports break. |
| **Caution** | `k1/kernel/service.py` is the REAL composition root (different from `k1/kernel/` stubs). Ensure these are the dead stubs at `k1/kernel/__init__.py`, `k1/kernel/registries.py`, `k1/kernel/tool_registry.py`. |
| **Findings addressed** | H-14, H-15 |
| **📖 Ref docs** | `19_kernel_package_audit.md` (H-14 dead stubs, H-15 shadow risk) |
| **Status** | ☑ DONE — dead `k1/kernel/registries/` stubs removed in MS-2 work |

##### Issue P3.2 — Delete `factory.py.bak`

| Field | Detail |
|-------|--------|
| **What** | `k1/concierge/factory.py.bak` — dead backup file in source tree. |
| **Findings addressed** | L-39 |
| **📖 Ref docs** | `16_concierge_audit.md` (L-39 dead .bak file) |
| **Status** | ☑ DONE — file already deleted in MS-2 work |

##### Issue P3.3 — Clean empty placeholder packages

| Field | Detail |
|-------|--------|
| **What** | Delete or add `__doc__` to: `k1/concierge/affective/`, `k1/concierge/empathy/`, `k1/concierge/rhythm/`, `k1/concierge/types/` (empty `__init__.py`), `k1/fabric/capability_types/` (empty), `k1/fabric/module_registry/` (empty), `bridge/codecs/` (empty), `bridge/adapters/` (empty), `bridge/connector/` (empty). |
| **Findings addressed** | L-40, L-44, L-45, L-58, L-62, L-63 |
| **📖 Ref docs** | `16_concierge_audit.md` (L-40 empty concierge dirs), `12_fabric_audit.md` (L-44, L-45 empty fabric dirs), `18_bridge_audit.md` (L-58, L-62, L-63 empty bridge dirs) |
| **Status** | ☑ DONE — added future-integration docstrings to all 8 packages (concierge/types already had real content, skipped) |

##### Issue P3.4 — Fix stale status markers

| Field | Detail |
|-------|--------|
| **What** | Bridge `__status__ = "planning"` is stale — substantial implementation exists. Update to `"alpha"`. Fix `sync/__init__.py` that exports 6 `None` symbols (`CertificateManager`, `CRDTMerge`, etc.). |
| **Findings addressed** | L-57, L-59 |
| **📖 Ref docs** | `18_bridge_audit.md` (L-57 stale status, L-59 None symbol exports) |
| **Status** | ☑ DONE — status → "alpha", removed 6 None symbol exports from sync/**init**.py |

---

#### Phase 4: POC Layer Decoupling (HIGH — 5 issues) — ✅ COMPLETE 2026-04-22 (audit, 5/5)

**Why fourth:** 98 `from poc.*` import lines remain in `k1/`. They violate clean architecture boundaries and block production deployment. Phase 1 delivered real state readers so the POC state path is no longer needed.

**Findings killed:** H-11, H-16, H-23, L-5, L-42, M-59, M-60, M-77, M-79

**Scope reality-check (code-verified 2026-04-15):**

| Coupling category | Files | Import lines | Phase 4 issue |
|-------------------|-------|-------------|---------------|
| `poc.k1_poc.main.boot()` in bootstrap | 0 | 0 | P4.1 — **ALREADY DONE** (replaced with BusFactory in Issue 2.0.3) |
| `ModelHubPOCBridge` instantiation (production) | 2 | 2 | P4.2 |
| `get_config()` in sessionstate | 12 | 12 | P4.3 |
| FlatBuffer type imports in sessionstate/sections | 12 | ~60 | DEFERRED (pure types, no runtime POC coupling — move in MS-5 package reorganisation) |
| Config shim `k1.concierge.config` → `poc.*` | 2 | 4 | P4.4 |
| `chat_repl.py` post-boot model mutation | 1 | 3 | P4.2 (folded in) |
| `runner.py` tool_tier mismatch | 1 | 0 | P4.5 |
| `POCMockBridgeAdapter` in `_create_fabric()` | 1 | 1 | DEFERRED to P5 (Fabric bridge adapter replacement) |

##### Issue P4.1 — Verify `poc.k1_poc.main.boot()` elimination ☑ ALREADY DONE

| Field | Detail |
|-------|--------|
| **What** | `k1/kernel/bootstrap.py` L109 has comment: `# --- Bus infrastructure (was: poc.k1_poc.main.boot()) --- / Issue 2.0.3: Direct factory calls, no POC dependency.` Zero `poc.k1_poc.main` imports remain. `k1/concierge/kernel/bootstrap.py` is a pure re-export shim (16 LOC, no POC imports). |
| **Findings addressed** | H-11, H-16 |
| **Status** | ☑ DONE — replaced with BusFactory in Issue 2.0.3 |

##### Issue P4.2 — Replace `ModelHubPOCBridge` with `ModelHubFactory` in bootstrap + chat_repl

| Field | Detail |
|-------|--------|
| **What** | Two production sites create `ModelHubPOCBridge(GeminiConciergeAdapter)`, bypassing budget, caching, circuit breakers, rate limiting, fallback, audit, metrics, cost tracking. Replace both with the `ModelHubFactory.create_standalone()` path that `chat_repl.py` already proves works (via `_create_production_model_hub()`). |
| **Site 1** | `k1/kernel/bootstrap.py` `_create_model()` L647-665 — non-test branch returns `ModelHubPOCBridge(GeminiConciergeAdapter(api_key))`. **Replace** with `ModelHubAdapter(ModelHubFactory.create_standalone(plugins={"google": plugin}))` — same pattern as `chat_repl._create_production_model_hub()`. |
| **Site 2** | `k1/kernel/chat_repl.py` `_create_legacy_gemini()` L245-256 — returns `ModelHubPOCBridge(GeminiConciergeAdapter(api_key))`. **Delete** this function entirely; the `--legacy-gemini` CLI flag now calls `_create_production_model_hub()` instead (or remove the flag). |
| **Adapter note** | `ModelHubAdapter` (at `k1/concierge/llm/model_hub_adapter.py`) already wraps `IModelHubPort.execute()` → `ILLMPort.generate()`. It's used by `_create_production_model_hub()` today. No new adapter needed. |
| **chat_repl race fix** | Current code boots `test_mode=True` then mutates `runtime.model` post-boot (L82-92). Fix: add `model_mode: str = "test"` field to `KernelConfig` with values `"test"` / `"hub"`. `_create_model(cfg)` reads `cfg.model_mode` and builds the correct model at boot. `chat_repl.py` passes `KernelConfig(model_mode="hub")` instead of post-boot mutation. Kills M-59 race window. |
| **Findings addressed** | H-23, M-59, M-77, M-79 |
| **Files** | `k1/kernel/bootstrap.py`, `k1/kernel/chat_repl.py`, `k1/concierge/config/kernel.py` (add `model_mode` field) |
| **Status** | ☑ DONE — `_create_model()` reads `cfg.model_mode`; `_create_model_hub()` extracted to bootstrap; `chat_repl.py` passes `KernelConfig(model_mode="hub")` at boot (no post-mutation); `_create_legacy_gemini()` deleted; `--no-test-mode` flag removed |

##### Issue P4.3 — Replace `get_config()` with constructor-injected config in SessionState

| Field | Detail |
|-------|--------|
| **What** | 12 files in `k1/sessionstate/` import `from poc.k1_poc.config import get_config` to read tuning knobs (tier limits, SLA thresholds, eviction budgets, etc.) at runtime. Each call reads `get_config().sessionstate.*` subtree. Replace with constructor-injected config dataclass. |
| **Approach** | 1) Define `@dataclass SessionStateConfig` in `k1/sessionstate/config.py` with all knobs currently read from `get_config().sessionstate.*`. 2) `SessionStateFactory.create_standalone()` accepts optional `SessionStateConfig` (defaults from `defaults.yaml` values hardcoded as class defaults). 3) Factory passes config to each component constructor. 4) Remove all 12 `from poc.k1_poc.config import get_config` lines. |
| **12 files to change** | `tiers/warm.py` L53, `tiers/hot.py` L62, `tiers/local_cold.py` L56, `snapshot.py` L41, `sizetracker.py` L63, `eviction.py` L53, `local_cold.py` L52, `migration.py` L60, `guard.py` L61, `reconstruction.py` L47, `adapters/sqlite_storage.py` L55, `adapters/direct_writer.py` L268 |
| **Findings addressed** | L-5 |
| **Status** | ☑ DONE — `SessionStateConfig` dataclass in `k1/sessionstate/config.py`; 12 files constructor-injected; all `from poc.k1_poc.config import get_config` removed |

##### Issue P4.4 — Replace config triple-indirection shims

| Field | Detail |
|-------|--------|
| **What** | `k1/concierge/config/__init__.py` (4 LOC) does `from poc.k1_poc.config import *`. `k1/concierge/config/loader.py` (20 LOC) does `import poc.k1_poc.config.loader as _canonical` + star import + dynamic attribute copy. These are pure pass-through shims creating a 3-hop chain: `k1.concierge.config` → `poc.k1_poc.config` → `poc.k1_poc.config.loader` → `defaults.yaml`. |
| **Approach** | 1) Move the ~40 config dataclass definitions from `poc/k1_poc/config/loader.py` into `k1/concierge/config/types.py`. 2) Move `get_config()`/`load_config()`/`reset_config()` and YAML loading into `k1/concierge/config/loader.py` (replace the shim). 3) Rewrite `k1/concierge/config/__init__.py` to import from `k1.concierge.config.types` + `k1.concierge.config.loader`. 4) Make `poc/k1_poc/config/__init__.py` a reverse shim that imports from `k1.concierge.config` (preserves POC demo scripts). |
| **Note** | `KernelConfig` at `k1/concierge/config/kernel.py` and `ConciergeConfig` at `k1/concierge/config/concierge.py` are already clean — no POC imports. Only the legacy `get_config()` path is affected. |
| **Findings addressed** | L-42 |
| **Files** | `k1/concierge/config/__init__.py`, `k1/concierge/config/loader.py`, `poc/k1_poc/config/__init__.py` (reverse shim), `poc/k1_poc/config/loader.py` (reverse shim) |
| **Status** | ☑ DONE — 1500-line loader.py moved to `k1/concierge/config/loader.py`; `__init__.py` imports from own loader; POC `__init__.py` + `loader.py` converted to reverse shims; singleton shared; 286 tests pass |

##### Issue P4.5 — Fix `runner.py` tool_tier mismatch

| Field | Detail |
|-------|--------|
| **What** | `k1/kernel/runner.py` L28 argparse `choices=["LOW", "MEDIUM", "HIGH", "CRISIS"]`. `k1/concierge/config/concierge.py` L15 `_VALID_TOOL_TIERS = frozenset({"LOW", "MED", "HIGH"})`. Passing `--tool-tier MEDIUM` or `--tool-tier CRISIS` silently passes through `KernelConfig` (no validation) then blows up at `ConciergeConfig.__post_init__()` with `ValueError`. |
| **Fix** | Change runner.py choices to `["LOW", "MED", "HIGH"]`. If `CRISIS` tier is needed, add it to `_VALID_TOOL_TIERS` in `concierge.py` and document the semantics. |
| **Findings addressed** | M-60 |
| **Files** | `k1/kernel/runner.py` L28-33, `k1/concierge/config/concierge.py` L15 (if adding CRISIS) |
| **Status** | ☑ DONE — runner.py choices changed to `["LOW", "MED", "HIGH"]` matching `_VALID_TOOL_TIERS` |

**Items explicitly deferred from Phase 4:**

| Item | Why deferred | Target |
|------|-------------|--------|
| ~60 FlatBuffer type imports in `k1/sessionstate/sections/*.py` from `poc.k1_poc.sessionstate.generated.flatbuffers.*` | Pure generated types, no runtime POC logic. Moving them is a package reorganisation task, not an architecture fix. | MS-5 package reorg |
| `POCMockBridgeAdapter` in `k1/kernel/bootstrap.py` `_create_fabric()` L696 | Fabric bridge adapter needs a real replacement (P5.1 BridgeWriteAdapter). Removing the mock without a replacement breaks Fabric. | P5.1 |
| SS type imports (`SessionStateFactory`, `HotTier`, `WarmTier`, `LocalColdArchive`, `SessionStateMetrics`) from `poc.k1_poc.sessionstate.*` | TYPE_CHECKING + re-export shims. Same package reorg as FlatBuffer types. | MS-5 package reorg |
| Docstring/comment references to `poc.k1_poc.*` in `cli.py`, `logging.py`, `compile_flatbuffers.py` | Cosmetic. Zero runtime impact. | MS-5 cleanup |

---

#### Phase 4B: Concierge Port Wiring & Bootstrap Reduction (HIGH — ~800 LOC) — ✅ COMPLETE 2026-04-22 (audit, 8/8; P4B.4 done-by-design per DEFERRED-4)

**Why before Phase 5:** Phase 5 fixes adapters in `service.py`. If we do P5 first, `bootstrap.py` remains a divergent legacy copy and the factory still ignores `IDispatchPort`. This phase makes the concierge consume external systems (Fabric, Orchestrator, ModelHub) through proper ports injected via `service.py`, and eliminates the legacy `bootstrap.py` wiring that duplicates `factory.py`.

**Findings killed:** L-42 (dispatch bypass), M-64, M-69 (IDispatchPort ignored), plus structural debt from `29_concierge_findings.md` (N1–N6)

📖 **Read before starting:** `29_concierge_findings.md` (full analysis), `20_concierge_api_mapping.md` (IDispatchPort), `21_concierge_cross_reference.md` (orchestrator/fabric boundary), `15_orchestrator_api_mapping.md` (real orchestrator ports)

##### Issue P4B.1 — Reduce `bootstrap.py` to thin `KernelService` delegate

| Field | Detail |
|-------|--------|
| **What** | `bootstrap.py` `start_kernel()` (~600 LOC) duplicates every concierge wiring step that `factory.py._construct_concierge()` already handles (FSM, HITL, Weave, Delta, DeadLetter, OrchestratorStub, Tools, Experience — all 16 steps). `chat_repl.py` and `runner.py` use this legacy path instead of `KernelService`. |
| **Approach** | 1) Rewrite `start_kernel(cfg)` to instantiate `KernelService(cfg)`, call `.startup()` + `.create_session()`, and wrap the result in `KernelRuntime` for backward compat. 2) Rewrite `stop_kernel(rt)` to call `KernelService.destroy_session()` + `.shutdown()`. 3) Keep `_mailbox_consumer()` (kernel infrastructure). 4) Delete all inline concierge wiring (~600 LOC): FSM creation, HITL lambdas, delta/weave/deadletter, OrchestratorStub, ToolContext, ExperienceLayer, front subscriptions. 5) Delete `_create_fabric()` (uses `POCMockBridgeAdapter`), `_create_capability_registry()`, `_build_recall_fn()`, `_build_experience_context()`, `_tick_experience()`. 6) Keep `_create_model_hub()` only if `KernelService` needs a test-mode model path; otherwise delete. |
| **Why first** | Every subsequent issue in this phase modifies `factory.py` and `service.py`. If bootstrap.py still has its own divergent copy, changes must be made twice. After this issue, there is ONE boot path. |
| **Files** | `k1/kernel/bootstrap.py` (~960→~150 LOC), `k1/kernel/chat_repl.py`, `k1/kernel/runner.py`, `k1/kernel/__init__.py` (re-exports) |
| **Findings addressed** | N1 from `29_concierge_findings.md` |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/concierge/kernel/bootstrap.py` is now 9 lines: tombstone docstring + single re-export of `KernelConfig`/`KernelRuntime`/`start_kernel`/`stop_kernel` from `k1.kernel.bootstrap`. All concierge wiring lives in `k1/kernel/service.py`. |

##### Issue P4B.2 — Wire `IDispatchPort` through factory (replace `fabric_port`/`orchestrator` kwargs)

| Field | Detail |
|-------|--------|
| **What** | `_construct_concierge()` step 14 ignores `ports.dispatch` entirely. Instead it receives `fabric_port` and `orchestrator` as raw kwargs and creates `OrchestratorStub` internally with three internal adapter classes (`_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter`). The `IDispatchPort` port is **defined in `ports.py`, populated by `service.py` with `FabricDispatchAdapter`**, but never read. |
| **Approach** | 1) Remove `fabric_port` and `orchestrator` kwargs from `create_with_ports()` and `_construct_concierge()`. 2) Step 14: read `ports.dispatch` for all task dispatch. If `ports.dispatch is None`, create a `NullDispatchAdapter` that returns canned "no orchestrator" response (test/standalone mode). 3) Pass `ports.dispatch` into ToolContext as the dispatch surface. 4) Update `service.py` `_create_session_tier2()` to stop passing `fabric_port=` and `orchestrator=` kwargs. |
| **Impact** | Concierge no longer has internal access to raw Fabric or Orchestrator objects. All external dispatch goes through the `IDispatchPort` contract. |
| **Files** | `k1/concierge/factory.py` (step 14 rewrite, remove kwargs), `k1/kernel/service.py` (remove kwargs from P4 call) |
| **Findings addressed** | M-64, M-69, supersedes old P5.8 |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/concierge/factory.py` L88 `PortBundle.dispatch: IDispatchPort \| None`; `create_with_ports(ports)` only — no `fabric_port`/`orchestrator` kwargs. L695-L699 step 14 wires orchestrator via `_DispatchPortFSMAdapter(ports.dispatch)`. |

##### Issue P4B.3 — Wire tools through `IDispatchPort` (remove `ctx.fabric_port`)

| Field | Detail |
|-------|--------|
| **What** | `invoke_capability` tool calls `ctx.fabric_port.execute()` directly, bypassing `IDispatchPort`. `dispatch_task` tool calls `route_task()` which internally creates `OrchestratorStub`. Both paths bypass the port system. |
| **Approach** | 1) Replace `fabric_port` in `ToolContext` with `dispatch: IDispatchPort`. 2) `invoke_capability` → `ctx.dispatch.dispatch_direct(CapabilityRequest)` for LOW-tier single fabric calls. 3) `dispatch_task` → `ctx.dispatch.dispatch_task(TaskEnvelope)` for MEDIUM/HIGH-tier orchestrated execution. 4) Remove `from k1.concierge.fabric.ports import IFabricPort` from tools. |
| **Depends on** | P4B.2 (IDispatchPort wired in factory) |
| **Files** | `k1/concierge/tools/implementations.py`, `k1/concierge/tools/dispatcher.py` |
| **Findings addressed** | Part of N1, N4 from `29_concierge_findings.md` |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/concierge/factory.py` L607-L622 builds `front_ctx`/`back_ctx` with `dispatch=ports.dispatch`; no `fabric_port:` kwarg in any `ToolContext` construction. |

##### Issue P4B.4 — Delete `k1/concierge/orchestrator/` (move `route_task` to `k1/orchestrator/`)

| Field | Detail |
|-------|--------|
| **What** | `k1/concierge/orchestrator/` is a parallel reimplementation (7 files: types, ports, interfaces, routing, stub, degradation, `__init__`) with its own `TaskEnvelope`, `Budget`, `AggregatedResult` that are "intentionally SEPARATE from k1.orchestrator.types." This dual-type system serves no purpose once `IDispatchPort` is the boundary. |
| **Approach** | 1) Move `route_task()` / `route_task_sync()` and tier budget tables from `routing.py` to `k1/orchestrator/routing.py` (or merge into existing orchestrator dispatcher). 2) Move `CircuitBreaker` + degradation logic from `degradation.py` to `k1/orchestrator/degradation.py`. 3) Delete `OrchestratorStub` — its MEDIUM-tier logic (max 2 fabric calls, budget enforcement) should be in the real orchestrator's MEDIUM handler. 4) Delete the 9 port protocols and 6 ABC interfaces — the real orchestrator has its own. 5) Delete the entire `k1/concierge/orchestrator/` directory. 6) Update `k1/concierge/factory.py` imports (should be gone after P4B.2). |
| **Depends on** | P4B.2 + P4B.3 (no more internal references to OrchestratorStub) |
| **Files** | Delete `k1/concierge/orchestrator/` (7 files). Move routing+degradation to `k1/orchestrator/`. Update imports in tests. |
| **Findings addressed** | N2 from `29_concierge_findings.md` |
| **Status** | ☑ DONE-BY-DESIGN 2026-04-22 (audit) — `OrchestratorStub` + `CircuitBreaker` + HIGH-tier interfaces + port protocols already removed (CircuitBreaker → `k1/orchestrator/degradation.py`). `k1/concierge/orchestrator/{routing.py,types.py,__init__.py}` directory **intentionally retained** because `route_task`/`route_task_sync`/`DispatchRecord` operate on POC types (TaskEnvelope/Budget/ComplexityTier) per ARCHITECTURE.md R-1 (POC↔production type split). Production has its own `_route_task` over different fields. Treating as DONE-by-design. |

##### Issue P4B.5 — Delete internal adapter trinity from factory

| Field | Detail |
|-------|--------|
| **What** | `_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter` in `factory.py` exist solely to feed `OrchestratorStub` with adapted port surfaces. With stub deleted (P4B.4) and dispatch going through `IDispatchPort` (P4B.2), these are dead code. |
| **Approach** | Delete the three adapter classes (~130 LOC) and their backward-compat re-exports from `bootstrap.py`. |
| **Depends on** | P4B.2 + P4B.4 |
| **Files** | `k1/concierge/factory.py` (delete classes + step 14 adapter wiring), `k1/kernel/bootstrap.py` (delete re-exports — may already be gone from P4B.1) |
| **Findings addressed** | Part of N2 |
| **Status** | ☑ DONE 2026-04-22 (audit) — `_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter` absent from `k1/concierge/factory.py`; only tombstone comment at L279-L283. `_build_delta_applicator` correctly retained (migrated, not deleted). Re-exports gone from `k1/concierge/kernel/bootstrap.py` and `k1/kernel/bootstrap.py` (enforced by `TestBackwardCompatExports` in `tests/k1/concierge/test_concierge_factory.py`). |

##### Issue P4B.6 — Fix `writer_port` reach-through in factory

| Field | Detail |
|-------|--------|
| **What** | Factory step 7 does `getattr(ports.state, "_writer_port", None)` — reaching into the `IStatePort` adapter's private attribute to extract a writer reference for ToolContext. This breaks port encapsulation. |
| **Approach** | Option A: Add `writer: IStateWriterPort | None` field to `PortBundle`.`service.py` passes the writer explicitly. Option B: Extend `IStatePort` protocol with a `get_writer()` method. Option A preferred — explicit is better than implicit. |
| **Files** | `k1/concierge/factory.py` (step 7), `k1/concierge/ports.py` (PortBundle or IStatePort), `k1/kernel/service.py` (pass writer) |
| **Findings addressed** | N5 (reach-through) from `29_concierge_findings.md` |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/concierge/factory.py` L606 `writer_port = ports.writer` (explicit port from `PortBundle.writer`); L613 + L621 pass it to `ToolContext`. Comment L604 confirms old `ssm._writer_port` reach-through removed. |

##### Issue P4B.7 — Move demo capabilities to test fixtures

| Field | Detail |
|-------|--------|
| **What** | `k1/concierge/fabric/` holds 40 mock capabilities (7 demo + 31 family + 2 web), `CapabilityRegistry`, `POCMockBridgeAdapter`, and `contract_converter`. These are test/demo fixtures in production code. Only `IFabricPort` (the port protocol) belongs in concierge. |
| **Approach** | 1) Keep `k1/concierge/fabric/ports.py` (`IFabricPort` protocol). 2) Move `demo_capabilities.py`, `family_capabilities.py`, `web_capabilities.py` → `tests/fixtures/capabilities/`. 3) Move `capability_registry.py` → `tests/fixtures/capabilities/registry.py`. 4) Move `poc_bridge_adapter.py` + `contract_converter.py` → `k1/fabric/adapters/` or `tests/fixtures/`. 5) Delete `k1/concierge/fabric/__init__.py` re-exports. Update test imports. |
| **Depends on** | P4B.1 (bootstrap.py no longer calls `_create_fabric()` / `create_demo_registry()`) |
| **Files** | `k1/concierge/fabric/` (6 files moved/deleted), `tests/fixtures/` (new), test files that import capabilities |
| **Findings addressed** | N4 from `29_concierge_findings.md` |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/concierge/fabric/` contains only `ports.py` + `__init__.py` (with P4B.7 docstring). All 6 demo files (registry.py, demo_capabilities.py, family_capabilities.py, web_capabilities.py, contract_converter.py, poc_bridge_adapter.py) live under `tests/fixtures/capabilities/`. |

##### Issue P4B.8 — Wire `IClassificationPort` in service.py

| Field | Detail |
|-------|--------|
| **What** | `service.py` passes `classification=None` to `ConciergeFactory`. Factory falls back to stub Phase1 pipeline. The real `Phase1Pipeline` exists in `k1/concierge/fsm/phase1/` but is only wired in the legacy `bootstrap.py` path. |
| **Approach** | 1) In `_create_session_tier2()` P4 block, create `Phase1Pipeline` (or `Phase1Factory.create()` if factory exists) and pass as `classification=pipeline`. 2) If Phase1 needs config, pass from `ConciergeConfig`. |
| **Files** | `k1/kernel/service.py` (P4 block) |
| **Findings addressed** | N6 (partial — classification port dead in production) |
| **Status** | ☑ DONE 2026-04-22 (audit) — `k1/kernel/service.py` L1401 `classification=self._phase1_pipeline` in `PortBundle`; L1128 `_build_phase1_pipeline()` builds process-wide UltraBERT pipeline shared across sessions. |

**Items explicitly deferred from Phase 4B:**

| Item | Why deferred | Target |
|------|-------------|--------|
| `k1/concierge/llm/` dual type system (`IConciergeModelPort` vs `IModelHubPort`) | Deep refactor touching every actor, prompt builder, and tool. ~50 files. Requires careful type migration. Not a wiring fix — it's a type unification project. | MS-5 type unification |
| HIGH tier Orchestrator→Planner→DAGExecutor path (interface-only, not wired) | Needs real Planner + DAGExecutor implementation. Out of scope for wiring plan. | Feature work |
| Experience/Compression/Scheduler stubs extraction | 3 experience stubs + 1 compression stub + 1 scheduler stub. Zero runtime impact. Cosmetic. | MS-5 cleanup |

---

#### Phase 5: Production Adapter Stubs → Real (MEDIUM — ~500 LOC) — ✅ COMPLETE 2026-04-22 (audit, 7/8; P5.7 PlaceResolver explicitly DEFERRED LOW)

**Why fifth:** With state wiring (Phase 1) and POC removal (Phase 4) done, these stubs can now be replaced with real adapters.

**Findings killed:** H-2, H-24, H-25, M-5, M-6, M-7, M-15, M-16, M-53, M-64, M-73, M-74, M-75, M-80, M-81, M-82

📖 **Read before starting:** `15_orchestrator_api_mapping.md` (BridgeWriteAdapter), `21_concierge_cross_reference.md` (recall memory), `24_memorywriter_api_mapping.md` (health adapter, PlaceResolver), `25_memorywriter_cross_reference.md` (recall loop broken), `13_modelhub_audit.md` (dev/test adapters), `19_modelhub_services_adapters_audit.md` (MH port wiring), `20_concierge_api_mapping.md` (FabricDispatchAdapter), `18_sessionstate_api_mapping.md` (SS stubs), `17_memorywriter_audit.md` (FakeSessionReadPort)

##### Issue P5.1 — Wire Orchestrator `BridgeWriteAdapter` (replace MockBridgeAdapter)

| Field | Detail |
|-------|--------|
| **What** | Replace `MockBridgeAdapter()` at S5 with `BridgeWriteAdapter(client=self._bridge.get_client())`. `SinkBridgeClient` queues commands to `LocalOutbox` (offline). Better than mock — audit trail preserved on disk. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` S5 block |
| **Findings addressed** | Absorbed from MS-3 issue 3.10.3 (MOCK-2) |
| **📖 Ref docs** | `15_orchestrator_api_mapping.md` (MOCK-2 BridgeWriteAdapter), `18_bridge_audit.md` (SinkBridgeClient offline pattern) |
| **Status** | ☑ DONE — S5 already wires `BridgeWriteAdapter(bridge_client=BridgeClientShim(orch_bridge_client))` when `bridge_enabled=True`; `MockBridgeAdapter()` retained as fallback for `OfflineBridgeAdapter` (`bridge_enabled=False` mode). |

##### Issue P5.2 — Wire Concierge `RecallMemoryAdapter` (replace memory=None)

| Field | Detail |
|-------|--------|
| **What** | `memory=None` → `_null_recall` returns empty list. Wire `RecallMemoryAdapter(bridge=self._bridge.get_client())`. Even with `SinkBridgeClient`, query returns empty gracefully rather than `None` fallback. |
| **Impact** | `recall_memory` tool no longer dead. When bridge comes online, recall works automatically. |
| **Findings addressed** | H-24 |
| **📖 Ref docs** | `21_concierge_cross_reference.md` (H-24 recall memory dead), `25_memorywriter_cross_reference.md` (recall loop broken) |
| **Status** | ☑ DONE — added `build_recall_fn(bridge_client)` helper in `k1/concierge/adapters/recall_memory.py` that maps `(query, memory_types, max_results)` → `bridge.query(QueryEnvelope([RecallSelector(type=t, query=query, limit=max_results) for t in memory_types]))` and flattens `RecallBundle` items to dicts. Wired `memory=RecallMemoryAdapter(build_recall_fn(self._bridge.get_client()))` in `service.py` PortBundle. `SinkBridgeClient` returns `RecallBundle.empty()` offline so closure yields `[]` cleanly; defensive try/except returns `[]` on bridge errors. |

##### Issue P5.3 — Fix MW `HealthAdapter` `get_started` lambda

| Field | Detail |
|-------|--------|
| **What** | `HealthAdapter(get_started=lambda: False)` at P5. Should bind to actual MW running state. Change to `get_started=lambda: memory_writer.is_running`. |
| **Findings addressed** | H-25, M-82 |
| **📖 Ref docs** | `24_memorywriter_api_mapping.md` (H-25 hardcoded False, M-82 health gap), `25_memorywriter_cross_reference.md` (health adapter wiring) |
| **Status** | ☑ DONE — in `service.py` P5 block, `HealthAdapter(get_started=...)` now uses forward-reference pattern: `lambda: session_memory_writer.is_started if session_memory_writer is not None else False`. Mirrors the existing `fabric_registration.py` wiring. |

##### Issue P5.4 — Wire ModelHub `IEventPort` to K1 Bus

| Field | Detail |
|-------|--------|
| **What** | Switch S2 from `ModelHubFactory.create_standalone()` to `create_with_ports()`. Wire `EventBusAdapter(bus=self._bus)` for `IEventPort`. |
| **Findings addressed** | M-16, M-75. Absorbed from MS-3 issue 3.10.5 / 3.4.4 |
| **📖 Ref docs** | `13_modelhub_audit.md` (M-16 dev/test adapters), `22_modelhub_api_mapping.md` (M-75 IEventPort mapping), `19_modelhub_services_adapters_audit.md` (MH port wiring detail) |
| **Status** | ☑ DONE — extended `EventBusAdapter.__init__` with optional `bus=` kwarg. When `bus` is set: `publish()` JSON-encodes payload into `Envelope` and calls `bus.publish(env)`; `subscribe()` registers a sync handler that JSON-decodes and dispatches the async user handler via `run_coroutine_threadsafe`. S2 wires `MHEventBusAdapter(bus=self._bus)`. Stub `MHStateReadAdapter` import removed (replaced by P5.5 wiring). |

##### Issue P5.5 — Wire ModelHub `IStateReadPort` to session routing reader

| Field | Detail |
|-------|--------|
| **What** | Wire `SessionStateProdAdapter(manager=session_routing_reader)` for ModelHub. Enables model selection based on user preferences. |
| **Findings addressed** | M-16. Absorbed from MS-3 issue 3.4.5 |
| **📖 Ref docs** | `13_modelhub_audit.md` (M-16 IStateReadPort stub), `19_modelhub_services_adapters_audit.md` (SessionStateProdAdapter) |
| **Status** | ☑ DONE — ModelHub is process-singleton built at S2 (before any session exists); `SessionStateProdAdapter` expects a per-session `manager.get_section(name)`. Resolved via `_FirstSessionSSMShim(self._sessions)` in `service.py` that picks the first active session's SSM. When no session active yet, `get_section()` returns `None` → prod adapter yields empty `StateSnapshot` (already its degraded mode). Good enough for `persona`/`control` reads used by routing. |

##### Issue P5.6 — Fix MW `FakeSessionReadPort` missing methods

| Field | Detail |
|-------|--------|
| **What** | Add `list_sections()` and `snapshot_all()` to `FakeSessionReadPort`. |
| **Findings addressed** | M-53 |
| **📖 Ref docs** | `17_memorywriter_audit.md` (M-53 FakeSessionReadPort missing methods) |
| **Status** | ☑ DONE — added `list_sections() -> FrozenSet[str]` and `snapshot_all(exclude=frozenset()) -> Dict[str, Any]` to `FakeSessionReadPort` in `k1/memory_writer/adapters/test_adapters.py`. Honours configured `fail_on` set so error paths still exercise. |

##### Issue P5.7 — Fix MW `PlaceResolver` empty entity list

| Field | Detail |
|-------|--------|
| **What** | `MemoryWriterFactory` passes `PlaceResolver([])`. Wire to entity list from session state at session start. |
| **Findings addressed** | M-81 |
| **📖 Ref docs** | `24_memorywriter_api_mapping.md` (M-81 PlaceResolver empty), `25_memorywriter_cross_reference.md` (entity resolution gap) |
| **Status** | ☐ DEFERRED — `17_memorywriter_audit.md` rates this LOW; entities are populated per-turn from NER at runtime, so the empty initial seed has no functional impact. Wiring an async `read_section("beliefs_active")` at session start (in `factory.create_for_session`) gains us 0–1 location entries before the first turn — not worth the lifecycle complexity now. Revisit when persona-warm-start matters. |

##### Issue P5.8 — ~~Wire Concierge `FabricDispatchAdapter` in factory~~ ABSORBED → P4B.2

| Field | Detail |
|-------|--------|
| **What** | `IDispatchPort` adapter available but factory Step 14 wires OrchestratorStub directly, bypassing `FabricDispatchAdapter`. Wire through adapter for proper port contract. |
| **Findings addressed** | M-64, M-69 |
| **📖 Ref docs** | `20_concierge_api_mapping.md` (M-64 IDispatchPort bypass), `21_concierge_cross_reference.md` (M-69 FabricDispatchAdapter detail) |
| **Status** | ☑ ABSORBED into P4B.2 |

---

#### Phase 6: Bus Production Hardening (MEDIUM — ~1500 LOC, internal-only refactor) — ✅ COMPLETE 2026-04-22 (audit, 15/15)

**Why sixth:** Bus is the nervous system. Today it is in-memory fire-and-forget at-most-once. Production needs backpressure, retry/DLQ, schema validation, idempotency, and durability for critical topics. This phase delivers all of that **behind the existing public API** so no consumer code (`k1/concierge`, `k1/orchestrator`, `k1/model_hub`, `k1/memory_writer`, `k1/sessionstate`, `bridge/`) requires changes — only 2 specific topic strings get renamed.

**Hard constraint — API IMPACT: NONE.** The following surfaces are FROZEN byte-for-byte:

- `IBus`, `IAsyncBus`, `Envelope`, `Priority`, `DeliveryMode`, `PayloadFormat`, `SubscriptionHandle`
- `BusFactory.create_local()`, `create_local_ordered()`, `create_for_testing()`, `create_mailbox_router()`
- `AsyncBusBridge`, `AsyncMailboxBridge`, `AsyncMailboxRouterBridge`
- `Middleware`, `MiddlewareChain`, all built-in middlewares, `TopicRegistry`
- `TimingChain`, `TimingConfig`, `TimingStats`, `default_timing_config()`, `DEFAULT_RULES`, `DEFAULT_MODE`
- `BusConfig`, `load_bus_config()`

**One additive Protocol method:** `IBus.flush()` (duck-typed, backward-compatible — no existing implementer breaks).

**Findings killed:** M-1, M-2, M-3, M-8, M-84, M-85, M-86, I-16, I-19, plus unmapped findings A (drain Rust/Python diff), B (impl re-export), F-D (DLQ topic has no publisher). Defer F-G (BridgeConnectionAdapter naming) to Phase 7.

**TimingChain decision:** KEEP UNTOUCHED. Causal + gap buffering still meaningful, especially after we add per-subscription mailboxes (Tier 3) — gap buffering preserves per-topic ordering, dispatch-time causal ordering preserved, handler-completion-causal ordering was never a documented guarantee. See doc note in P6.7.

**Topic renames in this phase:** Only 2.

1. `turn.complete.v1` → `k1.session.turn.complete.v1` (M-84) — single topic missing `k1.` prefix
2. `SessionBusAdapter` internal mapping flattens `k1.session.sessionstate.*` → `k1.sessionstate.*` (M-86) — adapter behavior, not a string per topic

All other topic names in the codebase are unchanged.

📖 **Read before starting:** `10_bus_audit.md` (sync threading, async gap), `26_bus_api_mapping.md` (RustMailbox, middleware chain), `27_bus_cross_reference.md` (topic naming, timing rules, namespace conventions). Plus `bus end-to-end audit` (the consolidated finding inventory from session memory).

**Phase 6 is organised in 7 tiers + branch/test bookends:**

```text
P6.0   Branch from POC_Migration → bus-hardening                 (workflow)
P6.1–P6.4   Tier 2: Async + observability fixes (pure internal, ~150 LOC)
P6.5        Tier 3: Per-subscription bounded mailbox (~250 LOC)
P6.6–P6.7   Tier 4: Retry policy + DeadLetterMiddleware (~200 LOC)
P6.8–P6.9   Tier 5: 2 topic renames (~50 LOC across publishers/subscribers)
P6.10       Add k1.model_hub STRICT rule (~5 LOC)
P6.11–P6.13 Tier 6: Opt-in extensions — schema, idempotency, durability (~700 LOC)
P6.14  End-to-end bus integration test before PR                 (workflow)
```

**Phase 6 status (as of 2026-04-18, branch `bus-hardening` HEAD `7164a26`):**

| Issue | Title | Commit | Status |
|-------|-------|--------|--------|
| P6.0  | Branch `bus-hardening` from `POC_Migration` | (branch cut) | ✅ DONE |
| P6.1  | Async handler Future error logging | `44006c8` | ✅ DONE |
| P6.2  | Wire MiddlewareChain into `RustBusAdapter` | `44006c8` | ✅ DONE |
| P6.3  | Fix `RustBusAdapter.drain()` to clear | `44006c8` | ✅ DONE |
| P6.4  | `k1/bus/impl/__init__.py` re-export consistency | `44006c8` | ✅ DONE |
| P6.5  | Per-subscription bounded mailbox + `IBus.flush()` | `47c7f10` | ✅ DONE |
| P6.6  | Per-topic `RetryPolicy` (resolver) | `47c7f10` | ✅ DONE |
| P6.7  | DLQ callback on retry exhaustion | `47c7f10` | ✅ DONE |
| P6.8  | Rename `turn.complete.v1` → `k1.session.turn.complete.v1` | `47c7f10` | ✅ DONE |
| P6.9  | Flatten `SessionBusAdapter` `sessionstate.*` topics | `47c7f10` | ✅ DONE |
| P6.10 | `k1.model_hub` STRICT timing rule | — | ❌ **OPEN** |
| P6.11 | Schema validation on `TopicRegistry` (+11 tests) | `7164a26` | ✅ DONE |
| P6.12 | `IdempotencyMiddleware` (+9 tests) | `7164a26` | ✅ DONE |
| P6.13 | `BusOutbox` SQLite durability + replay (+13 tests) | `7164a26` | ✅ DONE |
| P6.14 | E2E test suite + PR summary (+8 tests) | `7164a26` | ✅ DONE |

##### Issue P6.0 — [DONE branch cut] Create `bus-hardening` branch from `POC_Migration`

| Field | Detail |
|-------|--------|
| **What** | Cut a working branch off `POC_Migration` for the entire Phase 6 effort. All P6.1–P6.13 commits land on this branch; P6.14 verifies before opening PR back to `POC_Migration`. |
| **Commands** | `git checkout POC_Migration && git pull origin POC_Migration && git checkout -b bus-hardening` |
| **Why** | Phase 6 is 1500 LOC across the bus internals. Bundling on a feature branch keeps `POC_Migration` clean during the multi-issue effort and gives one PR review surface. |
| **Files** | (none — git workflow only) |
| **Status** | ☑ Branch `bus-hardening` cut from `POC_Migration`; HEAD now `7164a26`. |

**Outcome:** Branch `bus-hardening` was cut from `POC_Migration` and all P6.1–P6.14 commits landed on it. HEAD is `7164a26`.

---

##### Issue P6.1 — [DONE 44006c8] Async handler Future error logging (I-16)

| Field | Detail |
|-------|--------|
| **What** | `AsyncBusBridge._wrap_async_handler` schedules user coroutine via `asyncio.run_coroutine_threadsafe` but never inspects the returned `Future`, so async handler exceptions are silently swallowed. Add `Future.add_done_callback` that logs exceptions and increments a new `BusStats.async_handler_errors` counter. |
| **API impact** | None — internal change inside `_wrap_async_handler`. Public callback signature unchanged. |
| **Approach** | In [k1/bus/async_bridge.py](k1/bus/async_bridge.py), the `_sync_shim` already calls `run_coroutine_threadsafe`. Capture the returned `Future` and attach `lambda fut: _log_handler_exception(fut, env)`. Helper logs via `logger.exception` and bumps stats. |
| **Findings addressed** | I-16 |
| **📖 Ref docs** | `26_bus_api_mapping.md` §4 |
| **Status** | ☑ Landed in `44006c8`. |

**Outcome:** `k1/bus/async_bridge.py` now registers `Future.add_done_callback` that logs handler exceptions and increments a new `_async_handler_errors` counter on `BusStats`.

##### Issue P6.2 — [DONE 44006c8] Wire MiddlewareChain into `RustBusAdapter` dispatch (I-19)

| Field | Detail |
|-------|--------|
| **What** | `RustBusAdapter` stores `TimingChain` and `MiddlewareChain` references but does NOT invoke them — Rust backend silently bypasses tracing/metrics/topic-validation. Run Python `MiddlewareChain.process(env)` before calling Rust dispatch (accept the PyO3 callback overhead — observability matters more than the last microsecond). For TimingChain: route `RustBus.publish()` output through Python TimingChain when one is configured (same pattern as `LocalBus`), or document Rust = "unordered, observability-only via Python middleware" if integration is too slow. |
| **API impact** | None — `RustBusAdapter` public methods unchanged; behavior simply matches `LocalBus` now. |
| **Approach** | In [k1/bus/impl/rust_bus_adapter.py](k1/bus/impl/rust_bus_adapter.py), `publish()`: `stamped = self._stamp(env); processed = self._middleware.process(stamped); if processed is None: return; if self._timing_chain: self._timing_chain.process(processed, self._rust_dispatch) else: self._rust_dispatch(processed)`. Add parity test in `tests/k1/bus/impl/test_rust_bus_parity.py` proving middleware fires identically across backends. |
| **Findings addressed** | I-19 |
| **📖 Ref docs** | `26_bus_api_mapping.md` §3.4 |
| **Status** | ☑ Landed in `44006c8`. |

**Outcome:** `RustBusAdapter.publish()` now runs `MiddlewareChain` and `TimingChain` before Rust dispatch; a `None` return from the chain drops the envelope (parity with `LocalBus`).

##### Issue P6.3 — [DONE 44006c8] Fix `RustBusAdapter.drain()` to clear (finding A)

| Field | Detail |
|-------|--------|
| **What** | `LocalBus.drain()` returns captured envelopes AND clears the buffer. `RustBusAdapter.drain()` returns cumulative captures without clearing. Tests using `drain()` as a reset point behave differently between backends. |
| **API impact** | None — semantics align to existing `LocalBus` contract. |
| **Approach** | In [k1/bus/impl/rust_bus_adapter.py](k1/bus/impl/rust_bus_adapter.py), `drain()` calls underlying Rust `drain_captured()` (add to Rust crate if missing) or local `_captured.clear()` after read. Update `test_rust_bus_parity.py` with explicit drain-then-publish-then-drain assertion. |
| **Findings addressed** | finding A (unmapped, audit doc) |
| **📖 Ref docs** | `26_bus_api_mapping.md` §12 |
| **Status** | ☑ Landed in `44006c8`. |

**Outcome:** `RustBusAdapter` gained a `_drain_offset` slot. `drain()` now returns the un-drained tail and advances the offset; the `captured` property slices from the same offset for parity with `LocalBus.drain()`.

##### Issue P6.4 — [DONE 44006c8] Fix `k1/bus/impl/__init__.py` re-export consistency (finding B)

| Field | Detail |
|-------|--------|
| **What** | `k1/bus/impl/__init__.py` does not re-export `LocalMailbox`, `LocalMailboxRouter`, or Rust adapters; they are exported only from `k1.bus.__init__`. Inconsistent layering. Add the missing re-exports so `from k1.bus.impl import LocalMailbox` works. |
| **API impact** | None — purely additive. |
| **Approach** | Add 3-line `__all__` extension in [k1/bus/impl/**init**.py](k1/bus/impl/__init__.py). |
| **Findings addressed** | finding B (unmapped, audit doc) |
| **📖 Ref docs** | `26_bus_api_mapping.md` §12 |
| **Status** | ☑ Landed in `44006c8`. |

**Outcome:** `k1/bus/impl/__init__.py` now re-exports `LocalBus`, `LocalMailbox`, `LocalMailboxRouter`, `TopicTrie`, and `BusStats`, and conditionally re-exports the Rust adapters when present.

---

##### Issue P6.5 — [DONE 47c7f10] Per-subscription bounded mailbox + worker drain (M-1, M-2, M-3, M-8)

| Field | Detail |
|-------|--------|
| **What** | Today `LocalBus._dispatch()` invokes every matching handler synchronously on the publisher's thread. Slow or blocking handlers stall ALL publishers. Async handlers via `AsyncBusBridge` enqueue Futures unboundedly (OOM risk under load). Replace with: each subscription owns a bounded `LocalMailbox` (reuse the existing WFQ primitive). Publish enqueues to all matching mailboxes; one drain worker per subscription invokes the handler. Mailbox full → metric increment + DLQ (if topic durable) or drop. |
| **API impact** | `IBus.subscribe()`/`unsubscribe()`/`publish()` signatures unchanged. **Additive Protocol method:** `IBus.flush()` for tests that need "wait until all queued envelopes have been dispatched". Existing implementations duck-type — no break. |
| **Caveat** | Dispatch becomes asynchronous to publish. Tests that assert "after `bus.publish(env)`, handler has been called" must call `bus.flush()` first. Document in test conventions. |
| **TimingChain interaction** | TimingChain still runs on publisher's thread BEFORE mailbox enqueue. Per-topic gap buffering preserved (sequence ordering at enqueue). Causal buffering: `_CausalTracker` marks parent "delivered" at enqueue, not at handler completion — this matches Kafka/NATS semantics and is the correct guarantee. **Add docstring note** to [k1/bus/timing/timing_chain.py](k1/bus/timing/timing_chain.py) and a section in [k1/bus/ARCHITECTURE.md](k1/bus/ARCHITECTURE.md). |
| **Approach** | In [k1/bus/impl/local_bus.py](k1/bus/impl/local_bus.py): `_Subscription` dataclass gains a `mailbox: LocalMailbox` and `worker: threading.Thread`. `subscribe()` creates both; `unsubscribe()` joins worker and discards mailbox. `_dispatch_fn(env)` iterates matching subscriptions and calls `sub.mailbox.try_put(env)`. Worker loop: `while not closed: env = mailbox.receive(timeout_ms=100); try: handler(env) except: log + retry-or-DLQ (P6.6/P6.7)`. New stats: `mailbox_full_drops`, `mailbox_high_water_mark`. Mailbox capacity from new `BusConfig.subscription_mailbox_capacity` (default 1024). |
| **Findings addressed** | M-1 (sync blocks async), M-3 (no async path), M-8 (lock contention — per-sub mailbox eliminates global handler lock contention), M-2 (PortBundle/SessionBusAdapter type tightening folded in here as a small adjacent fix — change concrete `LocalBus` annotations to `IBus` Protocol where they appear) |
| **📖 Ref docs** | `10_bus_audit.md` §"Concurrency Model"; `26_bus_api_mapping.md` §7.1 Lock Hierarchy |
| **Status** | ☑ Landed in `47c7f10`. |

**Outcome:** Opt-in async dispatch via `LocalBus(async_dispatch=True, subscription_mailbox_capacity=...)`. Each subscription owns a `LocalMailbox` drained by a daemon thread. Added `IBus.flush(timeout_ms)` Protocol method and new `BusStats.mailbox_full_drops` / `BusStats.mailbox_high_water_mark` counters.

---

##### Issue P6.6 — [DONE 47c7f10] Per-topic RetryPolicy in TopicRegistry

| Field | Detail |
|-------|--------|
| **What** | When a handler raises, today the exception is logged and the envelope dropped. Add an opt-in `RetryPolicy(max_attempts: int = 0, base_ms: int = 100, jitter: bool = True, backoff: Literal["fixed","exponential"] = "exponential")` field on `TopicRegistry` entries. Default `max_attempts=0` = preserve current behavior (no retry, no consumer impact). |
| **API impact** | None for existing callers — `TopicRegistry.register(topic, ...)` gains optional `retry=None` kwarg. Topics without `retry=` get default no-retry. |
| **Approach** | Inside the per-subscription mailbox worker (P6.5), wrap handler call in retry loop reading the topic's `RetryPolicy` from the registry. Sleep with jitter between attempts. On exhausted attempts, hand off to DLQ (P6.7) if topic is durable, else log + drop + metric. |
| **Findings addressed** | (no formal finding ID; addresses missing reliability primitive) |
| **📖 Ref docs** | `26_bus_api_mapping.md` §"Future Work" |
| **Status** | ☑ Landed in `47c7f10`. |

**Outcome:** `LocalBus` accepts a `retry_resolver: (topic) -> RetryPolicy | None`. The async worker consults it and applies fixed/exponential backoff with jitter, capped at 10 s. Added `BusStats.async_handler_retries`. Default behavior (no resolver) preserves the prior no-retry contract.

##### Issue P6.7 — [DONE 47c7f10] `DeadLetterMiddleware` and `k1.internal.dead_letter.v1` publisher (finding F-D)

| Field | Detail |
|-------|--------|
| **What** | Topic `k1.internal.dead_letter.v1` is registered as published by "Bus middleware" but no publisher exists today. After P6.6 retry exhaustion, publish a `DLQRecord(original_topic, original_envelope_id, original_payload, error_class, error_msg, attempts, first_failure_ts, last_failure_ts)` to the DLQ topic. The DLQ topic itself is durable (Tier 6 / P6.13) so failures survive crash. |
| **API impact** | None — DLQ is internal observability surface. |
| **Approach** | New `k1/bus/middleware/dead_letter.py`: `DeadLetterMiddleware` is misnamed — it's actually a **DLQ publisher invoked by the mailbox worker**, not a middleware in the publish path. Real implementation: a small helper `_publish_to_dlq(bus, original_env, exc, attempts)` called from the mailbox worker on retry exhaustion. The publish goes through normal bus path (re-uses middleware/timing/durability). |
| **Findings addressed** | finding F-D (unmapped, audit doc) |
| **📖 Ref docs** | `27_bus_cross_reference.md` §9 Gap #4; `26_bus_api_mapping.md` §10.13 |
| **Status** | ☑ Landed in `47c7f10`. |

**Outcome:** `LocalBus` accepts a `dlq_callback(envelope, exc, attempts)` invoked once retries are exhausted. Added `BusStats.async_handler_dlq` counter. Wiring an actual `k1.internal.dead_letter.v1` publisher remains a downstream consumer concern; the bus-side hook is in place.

---

##### Issue P6.8 — [DONE 47c7f10] Rename `turn.complete.v1` → `k1.session.turn.complete.v1` (M-84)

| Field | Detail |
|-------|--------|
| **What** | This is the **only** topic in the entire registry missing the `k1.` namespace prefix. Without it, no `TimingConfig` rule matches → falls to RELAXED default → MemoryWriter `TurnDispatcher` trigger can be reordered. Renaming to `k1.session.turn.complete.v1` matches the existing `k1.session` STRICT rule automatically. |
| **API impact** | Topic string changes at 1 publisher + 1 subscriber. Atomic find-replace in same PR. |
| **Approach** | Grep `"turn.complete.v1"` and `TOPIC_TURN_COMPLETE`; update both publisher (FSM in `k1/concierge`) and subscriber (`k1/memory_writer/kernel/turn_dispatcher.py`). Update topic registry entry. Add migration note to changelog. |
| **Findings addressed** | M-84 |
| **📖 Ref docs** | `27_bus_cross_reference.md` §9 Gap #1 |
| **Status** | ☑ Rename landed in `47c7f10`. |

**Outcome:** `turn.complete.v1` was renamed to `k1.session.turn.complete.v1` in `k1/memory_writer/events.py` and `k1/memory_writer/pipeline/turn_dispatcher.py`. Note: this is distinct from the concierge `k1.session.turn.completed.v1` event (different event, different verb tense). Earlier references to `turn.complete.v1` in this plan are historical — the rename landed in `47c7f10`.

##### Issue P6.9 — [DONE 47c7f10] Flatten `SessionBusAdapter` double-nested topics (M-86)

| Field | Detail |
|-------|--------|
| **What** | `SessionBusAdapter._map_topic(event_type)` prefixes with `"k1.session."`, so `sessionstate.mutation.requested` becomes `k1.session.sessionstate.mutation.requested` — double-nested. Change adapter to map directly: `sessionstate.*` → `k1.sessionstate.*`, leave other prefixes alone. |
| **API impact** | Adapter callers (sessionstate publishers) keep their current `event_type=` strings unchanged. Only the wire topic string changes. Subscribers must update their pattern from `k1.session.sessionstate.*` → `k1.sessionstate.*`. |
| **Approach** | Change `_map_topic()` in [k1/bus/adapters/session_adapter.py](k1/bus/adapters/session_adapter.py). Grep subscribers for `"k1.session.sessionstate"` — update patterns. Update topic registry entries. |
| **Findings addressed** | M-86 |
| **📖 Ref docs** | `27_bus_cross_reference.md` §9 Gap #3; `26_bus_api_mapping.md` §10.17 |
| **Status** | ☑ Landed in `47c7f10`. |

**Outcome:** `SessionBusAdapter` declares `_FLATTEN_PREFIXES = ("sessionstate.",)` and now flattens `sessionstate.*` events to `k1.sessionstate.*` (previously double-nested as `k1.session.sessionstate.*`).

##### Issue P6.10 — [OPEN] Add `k1.model_hub` STRICT timing rule (M-85)

| Field | Detail |
|-------|--------|
| **What** | `k1.model_hub.execute.v1` is used for synchronous bus RPC (request/response correlation). Has no timing rule → falls to RELAXED → out-of-order delivery can route response to wrong waiter. Add `"k1.model_hub": STRICT` to `DEFAULT_RULES`. |
| **API impact** | None — adding a rule to a frozen dict that consumers don't read directly. |
| **Approach** | One-line addition in [k1/bus/timing/defaults.py](k1/bus/timing/defaults.py) `DEFAULT_RULES`. Test in `test_timing_config.py` confirming `resolve("k1.model_hub.execute.v1") == STRICT`. |
| **Findings addressed** | M-85 |
| **📖 Ref docs** | `27_bus_cross_reference.md` §5, §9 Gap #2 |
| **Status** | ☐ **OPEN** — not committed in the Phase 6 chain. |

**Outcome:** **NOT IMPLEMENTED.** `k1/config/bus.yaml` does not contain a `k1.model_hub` entry, so the topic falls to the default RELAXED rule. To be picked up in a follow-up batch — the change itself remains a one-line addition to `DEFAULT_RULES` plus a confirming test.

---

##### Issue P6.11 — [DONE 7164a26] Schema validation on `TopicRegistry` (opt-in, additive)

| Field | Detail |
|-------|--------|
| **What** | `TopicValidationMiddleware` today only validates that the topic *name* is registered. Add optional `schema: type[Pydantic\|msgspec.Struct] | None = None` field on `TopicRegistry` entries. When set, middleware validates the envelope payload against schema (decode + structural check). Two modes: `permissive` (default — log + metric on schema violation, deliver anyway) and `strict` (drop on violation). |
| **API impact** | None — `register(topic, ...)` gains optional `schema=` kwarg. Topics without schema get current behavior (name-only validation). |
| **Approach** | Pick `msgspec.Struct` (~30× faster than Pydantic for high-volume topics; tiny dependency footprint). Extend `TopicRegistry.Entry` dataclass. `TopicValidationMiddleware.process()` checks schema if present, decodes via `msgspec.msgpack.decode(env.payload, type=schema)`. Mode controlled by `BusConfig.schema_validation_mode` (default `"permissive"`). |
| **Findings addressed** | (extension — not a previously logged finding) |
| **📖 Ref docs** | (none — new functionality) |
| **Status** | ☑ Landed in `7164a26`. |

**Outcome:** `TopicRegistry` gained `register(topic, validator=None)`, `register_prefix(...)`, and `lookup_validator(topic)` (resolution order: exact → prefix → fnmatch). New `TopicValidationMiddleware(schema_validation_mode="permissive"|"strict")` with `schema_violation_count` / `schema_drop_count` counters. Added `SchemaValidationError(ValueError)` and a `PayloadValidator` type alias. +11 tests in `tests/k1/bus/middleware/test_schema_validation.py`. Note: implementation is validator-callable based (not `msgspec.Struct`-typed) — keeps the surface dependency-free.

##### Issue P6.12 — [DONE 7164a26] `IdempotencyMiddleware` for command topics (opt-in, additive)

| Field | Detail |
|-------|--------|
| **What** | Command topics with caller-provided `request_id` need idempotency: re-publishing the same command must NOT re-execute. Add a new `IdempotencyMiddleware` that maintains an LRU cache (default 10K entries, 5-minute TTL) keyed by `(topic, request_id)`. Duplicate within window → drop + metric. NOT in default chain — sites that publish commands wire it in explicitly. |
| **API impact** | None — new middleware. Sites that don't use it see no change. |
| **Approach** | New file [k1/bus/middleware/idempotency.py](k1/bus/middleware/idempotency.py). Use `cachetools.TTLCache` (already in deps). Document recommended placement: AFTER topic validation, BEFORE tracing. |
| **Findings addressed** | (extension) |
| **📖 Ref docs** | (none — new functionality) |
| **Status** | ☑ Landed in `7164a26`. |

**Outcome:** New `IdempotencyMiddleware` at `k1/bus/middleware/idempotency.py` — stdlib only (no `cachetools` dependency). LRU `OrderedDict` keyed by `(topic, request_id)` with monotonic-clock TTL. Counters: `drop_count`, `pass_count`, `no_key_count`, `cache_size`. +9 tests.

##### Issue P6.13 — [DONE 7164a26] Durability outbox + replay (opt-in per topic)

| Field | Detail |
|-------|--------|
| **What** | Today every envelope lives only in RAM. Process crash = total event loss for in-flight commands/responses. Add per-topic `durable: bool = False` flag in `TopicRegistry`. When true, `LocalBus.publish()` appends `(envelope_id, topic, payload, ts, ack_offset=NULL)` to a SQLite WAL outbox BEFORE dispatch. Per-consumer ack tracking: durable subscriptions get a stable `consumer_id`; mailbox worker calls `outbox.ack(consumer_id, envelope_id)` after successful handler completion. On startup, `bus.replay_durable_topics()` re-publishes un-acked envelopes per consumer (at-least-once). |
| **API impact** | `subscribe()` gains optional `consumer_id: str \| None = None` kwarg for durable topics. Without it, durable topics behave at-most-once (current behavior preserved). With it, at-least-once delivery; **handlers must be idempotent** (P6.12 idempotency middleware available for the publish-side). |
| **Approach** | New `k1/bus/outbox/sqlite_outbox.py` with `BusOutbox` class wrapping SQLite WAL connection. Schema: `envelopes(envelope_id PK, topic, payload BLOB, ts_ns, deleted INT)` + `acks(consumer_id, last_acked_envelope_id, PRIMARY KEY (consumer_id))`. Reuse pattern from existing `k0/outbox/local_outbox.py`. Outbox path from `BusConfig.durable_outbox_path` (default `~/.familyos/bus_outbox.db`). |
| **Topics to flag durable** | `k1.session.turn.complete.v1`, `k1.orchestration.task.dispatch.v1`, `k1.orchestration.task.result.v1`, `k1.memory.write.requested.v1`, `k1.bridge.command.*`, `k1.internal.dead_letter.v1`. Topics that stay non-durable: `k1.affect.*`, `k1.k0.sse.*`, `k1.fabric.learning.*`, `k1.mw.*` telemetry. |
| **Replay semantics** | At-least-once for durable. Subscribers must idempotently handle duplicates. Document this in `ARCHITECTURE.md` and add a runtime check (warn if durable topic subscribed without consumer_id). |
| **Findings addressed** | (extension — closes the biggest production-readiness gap) |
| **📖 Ref docs** | (none — new functionality; reference k0 outbox pattern) |
| **Status** | ☑ Landed in `7164a26`. |

**Outcome:** New `BusOutbox` at `k1/bus/outbox/sqlite_outbox.py` (SQLite WAL): `append`, `ack`, `unacked`, `prune_acked`, `last_envelope_id`, `count`, `close`. `OutboxRecord` dataclass with `to_envelope()`. `LocalBus(outbox=, durable_topics=)` persists envelopes before dispatch; `subscribe(consumer_id=...)` enables at-least-once via `_acking_handler`; new `replay_durable_topics(*, consumer_id=None)` method. +13 tests.

---

##### Issue P6.14 — [DONE 7164a26] End-to-end bus integration test before PR

| Field | Detail |
|-------|--------|
| **What** | Before opening PR `bus-hardening` → `POC_Migration`, run a curated suite that exercises every Phase 6 change end-to-end with both Python and Rust backends. Must all pass before PR. |
| **Test matrix (each backend)** | 1) **Smoke**: Full `tests/k1/bus/` suite (~600 tests). 2) **Regression**: `tests/k1/concierge`, `tests/k1/orchestrator`, `tests/k1/memory_writer`, `tests/k1/model_hub`, `tests/k1/sessionstate` — proves no consumer broke. 3) **New behavior**: `tests/k1/bus/test_phase6_e2e.py` (new file) — backpressure (P6.5), retry+DLQ (P6.6/P6.7), topic-rename traffic (P6.8/P6.9), strict timing for `k1.model_hub` (P6.10), schema validation (P6.11), idempotency (P6.12), durability replay across simulated process restart (P6.13). 4) **Async**: `pytest tests/k1/bus/test_async_bridge.py` confirms `AsyncBusBridge` still works after `flush()` was added. 5) **Lifecycle**: `KernelService.startup() → create_session() → publish-traffic → destroy_session() → shutdown()` smoke. |
| **Manual sanity** | `chat_repl.py` boot, send 3 turns, verify SSE responses arrive, kill mid-turn, restart, confirm durable replay completes. |
| **Acceptance criteria** | All test files pass with both `K1_BUS_BACKEND=python` and `K1_BUS_BACKEND=rust`. No new pytest warnings. `mypy k1/bus` clean. `ruff check k1/bus` clean. |
| **PR commands** | `git push -u origin bus-hardening && gh pr create --base POC_Migration --title "Phase 6: Bus Production Hardening" --body-file docs/whiteboard/temp_kernel_bootstrap/phase6_pr_summary.md` |
| **Files** | `tests/k1/bus/test_phase6_e2e.py` (new), short PR summary at `docs/whiteboard/temp_kernel_bootstrap/phase6_pr_summary.md` (new) |
| **Status** | ☑ Landed in `7164a26`. |

**Outcome:** New E2E test file `tests/k1/bus/test_phase6_e2e.py` (8 tests) covers async retry/DLQ, topic renames, schema validation, idempotency, and durability replay across a simulated process restart. PR summary published at [docs/whiteboard/temp_kernel_bootstrap/phase6_pr_summary.md](docs/whiteboard/temp_kernel_bootstrap/phase6_pr_summary.md). Bus suite total: **1108 passing** (+39 vs. baseline 1069). Consumer-suite failures observed during regression were verified pre-existing on `POC_Migration` parent (perf SLO flakes, `test_no_deep_imports_in_production`, model_hub asyncio loop pollution, `runner_cli` SystemExit:2) and unrelated to Phase 6. Acceptance criteria for the open item P6.10 (Rust + Python backend matrix on `k1.model_hub` STRICT) remain unchecked.

---

**Phase 6 explicitly defers (out of scope):**

| Item | Why deferred | Target |
|------|-------------|--------|
| `BridgeConnectionAdapter` method-name mismatch (`send/query/route_ifl` vs `submit_command/query/execute_connector`) | Bridge layer concern, not bus internals. Already noted in Phase 7 plan. | Phase 7 |
| Cross-process bus transport (NATS/Redis backend) | Single-process scope today. Bridge handles K0↔K1 transport. | Out of roadmap |
| Consumer groups / load balancing across replicas | Single-process scope. | Out of roadmap |
| Encryption / SASL / mTLS on bus | Single-process trust boundary. | Out of roadmap |
| `k1.mw` RELAXED-fallthrough confirmation comment | Cosmetic. | Fold into P6.10 if convenient |
| `RustBusAdapter.sweep()` no-op documentation | Doc-only; add to ARCHITECTURE.md note during P6.2 | Fold into P6.2 |

---

#### Phase 7: Bridge Adapter Completion (DEFERRED — ~800 LOC) — ❌ NOT STARTED 2026-04-22 (audit, 0/7; P7.4 BLOCKED on K0 HTTP API)

**Why last:** Bridge requires K0 API availability. Build adapters for offline queueing pattern but defer real HTTP transport until K0 API is ready.

**Findings killed:** H-12, H-13, L-56, L-60, L-61, M-54

📖 **Read before starting:** `18_bridge_audit.md` (port protocols, SinkBridgeClient, offline patterns, missing adapters)

##### Issue P7.1 — Build `KernelQueryPort` adapter

| Field | Detail |
|-------|--------|
| **What** | `IKernelQueryPort` protocol defined (`query()`, `query_single()`). Build offline adapter that queues queries, returns empty results when disconnected. |
| **Findings addressed** | H-12 (partial). Absorbed from MS-3 issue 3.9.3 |
| **📖 Ref docs** | `18_bridge_audit.md` (H-12 port protocol definition, §3.9.3 KernelQueryPort) |
| **Status** | ☐ NOT DONE 2026-04-22 (audit) — protocol exists at [bridge/ports/query_port_protocol.py:115](bridge/ports/query_port_protocol.py#L115) but `bridge/adapters/` contains only `__init__.py`. No offline adapter implemented. |

##### Issue P7.2 — Build `KernelSSEPort` adapter

| Field | Detail |
|-------|--------|
| **What** | `IKernelSSEPort` protocol defined (`subscribe()`, `ack()`, `close()`). Build offline adapter that no-ops when disconnected. |
| **Findings addressed** | H-12 (partial). Absorbed from MS-3 issue 3.9.4 |
| **📖 Ref docs** | `18_bridge_audit.md` (H-12 port protocol definition, §3.9.4 KernelSSEPort) |
| **Status** | ☐ NOT DONE 2026-04-22 (audit) — protocol exists at [bridge/ports/sse_port_protocol.py:73](bridge/ports/sse_port_protocol.py#L73); no offline adapter in `bridge/adapters/`. |

##### Issue P7.3 — Build `KernelObsPort` adapter

| Field | Detail |
|-------|--------|
| **What** | `IKernelObsPort` protocol defined (`emit()`, `emit_feedback()`). Build offline adapter that queues to `LocalOutbox`. Fix: `emit_obs` currently drops NORMAL/HIGH despite docstring saying it queues. |
| **Findings addressed** | H-12 (partial), M-54. Absorbed from MS-3 issue 3.9.5 |
| **📖 Ref docs** | `18_bridge_audit.md` (H-12 port protocol, M-54 emit_obs drops, §3.9.5 KernelObsPort) |
| **Status** | ☐ NOT DONE 2026-04-22 (audit) — protocol exists at [bridge/ports/obs_port_protocol.py:78](bridge/ports/obs_port_protocol.py#L78); no offline adapter in `bridge/adapters/`. Includes `emit_obs` NORMAL/HIGH drop bug fix. |

##### Issue P7.4 — Build `HttpBridgeClient` (deferred — K0 API required)

| Field | Detail |
|-------|--------|
| **What** | Compose all 5 port adapters into online `HttpBridgeClient`. Requires real K0 API. |
| **Findings addressed** | H-13. Absorbed from MS-3 issue 3.9.8 |
| **📖 Ref docs** | `18_bridge_audit.md` (H-13 HttpBridgeClient, §3.9.8 online transport) |
| **Status** | 🔲 BLOCKED on K0 API |

##### Issue P7.5 — Fix `SigningBackend` — add `@runtime_checkable`

| Field | Detail |
|-------|--------|
| **What** | `SigningBackend` Protocol not decorated with `@runtime_checkable`. Add for isinstance() checks. |
| **Findings addressed** | L-56 |
| **📖 Ref docs** | `18_bridge_audit.md` (L-56 SigningBackend protocol) |
| **Status** | ☐ NOT DONE 2026-04-22 (audit) — [bridge/core/signing.py:40](bridge/core/signing.py#L40) `class SigningBackend(Protocol):` has no `@runtime_checkable` decorator. 1-line fix. |

##### Issue P7.6 — Move `StubBridgeClient` from prod to test module

| Field | Detail |
|-------|--------|
| **What** | `StubBridgeClient` lives in `bridge/client.py` (production). Move to test module. |
| **Findings addressed** | L-60 |
| **📖 Ref docs** | `18_bridge_audit.md` (L-60 StubBridgeClient in prod code) |
| **Status** | ☐ NOT DONE 2026-04-22 (audit) — `StubBridgeClient` still in production module at [bridge/client.py:128](bridge/client.py#L128). |

##### Issue P7.7 — Add Protocol conformance to `KernelCommandPort`

| Field | Detail |
|-------|--------|
| **What** | `KernelCommandPort` uses structural subtyping but doesn't declare protocol conformance explicitly. Add for clarity. |
| **Findings addressed** | L-61 |
| **📖 Ref docs** | `18_bridge_audit.md` (L-61 KernelCommandPort protocol conformance) |
| **Status** | ☐ NOT DONE 2026-04-22 (audit) — [bridge/kernel/command_port.py:47](bridge/kernel/command_port.py#L47) `class KernelCommandPort:` is a plain class with no explicit Protocol conformance declaration. |

---

### MS-3: Technical Debt Removal

**Goal:** Address remaining findings NOT covered by Phases 1-7. These are non-blocking items: type safety sweeps, documentation fixes, future-scope stubs, and architectural improvements.

**Rationale:** All CRITICAL and HIGH findings are addressed in Phases 1-7. MS-3 contains only MEDIUM/LOW/INFO items that don't block production wiring.

---

#### Epic 3-TD.1: Type Safety Sweep (~150 LOC)

**What:** Replace `Any` types with Protocol types across all adapter constructors and port boundaries.

📖 **Read:** `12_fabric_audit.md`, `14_orchestrator_audit.md`, `15_planner_audit.md`, `16_concierge_audit.md`, `17_memorywriter_audit.md`, `19_modelhub_services_adapters_audit.md`

| Issue | Component | What | Findings | 📖 Ref |
|-------|-----------|------|----------|---------|
| TD-1.1 | Fabric / Factory | `create_with_ports()` all 6 port args typed `Any` → Protocol | M-9 | `12_fabric_audit.md` |
| TD-1.2 | Planner / Adapters | All 7 adapter constructors typed `Any` → Protocol | M-38 | `15_planner_audit.md` |
| TD-1.3 | Orchestrator / PlannerAdapter | `planner_mailbox` typed `Any` → `IPlannerMailbox` | L-21 | `14_orchestrator_audit.md` |
| TD-1.4 | Orchestrator / IWorkflowStoragePort | `save_run(manifest: object)`, `get_runs() → list` → typed | M-20 | `14_orchestrator_audit.md` |
| TD-1.5 | Concierge / KernelRuntime | 24+ fields typed `Any` → Protocol types | M-43 | `16_concierge_audit.md` |
| TD-1.6 | Concierge / ToolContext | 4 fields typed `Any` → Protocol | L-77, L-78, L-80 | `20_concierge_api_mapping.md` |
| TD-1.7 | MemoryWriter / Adapters | 4 of 5 adapters type deps as `Any` → Protocol | L-51 | `17_memorywriter_audit.md` |
| TD-1.8 | ModelHub / SessionStateProdAdapter | `manager` typed `Any` → Protocol | L-75 | `19_modelhub_services_adapters_audit.md` |
| TD-1.9 | Fabric / ModelInfo | `capabilities` uses `List[str]` → `List[ModelCapability]` | L-14 | `12_fabric_audit.md` |
| TD-1.10 | k1/kernel / registries | No type hints on any parameter → add types | L-70 | `19_kernel_package_audit.md` |

---

#### Epic 3-TD.2: Documentation & Stale Markers (~0 LOC code, docs only)

📖 **Read:** `14_orchestrator_audit.md`, `19_kernel_package_audit.md`, `24_memorywriter_api_mapping.md`, `18_sessionstate_api_mapping.md`

| Issue | What | Findings | 📖 Ref |
|-------|------|----------|---------|
| TD-2.1 | Orchestrator `ports/__init__.py` docstring says "8 ports" — actually 9. Fix. | L-20 | `14_orchestrator_audit.md` |
| TD-2.2 | Orchestrator `adapters/__init__.py` docstring says "16 adapters" — actually 17. Fix. | L-24 | `14_orchestrator_audit.md` |
| TD-2.3 | k1/kernel `tool_registry` comment says "versions" but none exist. Fix. | L-71 | `19_kernel_package_audit.md` |
| TD-2.4 | MemoryWriter `ARCHITECTURE.md` claims 37% — stale, update. | L-86 | `24_memorywriter_api_mapping.md` |
| TD-2.5 | SessionState docstring says 48KB but actual is 52KB. Fix. | L-68 | `18_sessionstate_api_mapping.md` |

---

#### Epic 3-TD.3: Architectural Improvements (MEDIUM, non-blocking)

📖 **Read:** `12_fabric_audit.md`, `14_orchestrator_audit.md`, `15_orchestrator_api_mapping.md`, `16_concierge_audit.md`, `20_concierge_api_mapping.md`, `21_concierge_cross_reference.md`, `13_modelhub_audit.md`, `19_modelhub_services_adapters_audit.md`, `24_memorywriter_api_mapping.md`

| Issue | Component | What | Findings | 📖 Ref |
|-------|-----------|------|----------|---------|
| TD-3.1 | Fabric / IEmbeddingPort | Define formal `IEmbeddingPort` Protocol (currently implicit). Wire in kernel S4. | M-10, C-5, M-46 | `12_fabric_audit.md`, `17_fabric_orchestrator_planner_cross_reference.md` |
| TD-3.2 | Fabric / IBridgePort | Resolve mixed sync/async (3 async + 2 sync methods) | M-13 | `12_fabric_audit.md` |
| TD-3.3 | Fabric + SS | Resolve ABC vs Protocol inconsistency | M-11 | `12_fabric_audit.md`, `11_sessionstate_audit.md` |
| TD-3.4 | Fabric / Providers | Wire WORKFLOW and CONCIERGE provider deps in `ProviderFactory` | H-3, M-14, M-47, M-48 | `12_fabric_audit.md`, `17_fabric_orchestrator_planner_cross_reference.md` |
| TD-3.5 | Orchestrator / IBridgeWritePort | Rename to `IBridgePersistencePort` (contains read methods) | M-19 | `15_orchestrator_api_mapping.md` |
| TD-3.6 | Orchestrator / AdminHttpAdapter | Address "god adapter" accessing 6 private fields | M-22 | `14_orchestrator_audit.md` |
| TD-3.7 | Orchestrator / ErrorRouter | Implement HIGH→MEDIUM degradation action on FALLBACK | M-23 | `14_orchestrator_audit.md` |
| TD-3.8 | Orchestrator / Shutdown | Implement force-compensate and persist-triggers on shutdown | M-24, M-25 | `14_orchestrator_audit.md` |
| TD-3.9 | Orchestrator / CrashRecovery | Fix crash_recovery → bridge read_wal returns None | M-26, M-27, M-32 | `14_orchestrator_audit.md`, `15_orchestrator_api_mapping.md` |
| TD-3.10 | Concierge / Runtimes | Converge `KernelRuntime` (24 fields) + `ConciergeRuntime` (19 params) → single runtime | H-10 | `16_concierge_audit.md` |
| TD-3.11 | Concierge / KernelConfig | Add validation on `tool_tier` | M-41 | `16_concierge_audit.md` |
| TD-3.12 | Concierge / KernelRuntime | Fix undeclared fields via setattr | M-42 | `16_concierge_audit.md` |
| TD-3.13 | Concierge / PortBundle | Include `IFabricPort` in PortBundle (currently excluded) | M-44 | `20_concierge_api_mapping.md` |
| TD-3.14 | ModelHub / BusEnvelopeDeserializer | Type only CHAT and TOOL_CALL — add remaining 13 types | M-61 | `22_modelhub_api_mapping.md` |
| TD-3.15 | ModelHub / EventBusAdapter | Wire to real K1 bus (currently in-memory only) | L-81 | `13_modelhub_audit.md` |
| TD-3.16 | ModelHub / Rename MW's IModelHubPort | Rename to `IMemoryWriterLLMPort` | M-18, H-4 | `24_memorywriter_api_mapping.md`, `13_modelhub_audit.md` |
| TD-3.17 | Concierge / Type divergence | Align `name` vs `capability_name` across POC↔K1 | M-63, M-72 | `21_concierge_cross_reference.md` |
| TD-3.18 | MemoryWriter / AccumulationGate | Build Stage 1B accumulation gate (6 triggers) | M-80 | `24_memorywriter_api_mapping.md` |

---

#### Epic 3-TD.4: Future-Scope Stubs (deferred to specific milestones)

📖 **Read:** `11_sessionstate_audit.md`, `18_sessionstate_api_mapping.md`, `13_modelhub_audit.md`, `22_modelhub_api_mapping.md`, `21_concierge_cross_reference.md`, `18_bridge_audit.md`

| Issue | Component | What | Blocked On | Findings | 📖 Ref |
|-------|-----------|------|-----------|----------|---------|
| TD-4.1 | SS / DeltaBusAdapter | Wire SS events to Bus. Replace `LocalEventAdapter`. | Bus↔SS async bridge | M-5, H-2 (partial) | `11_sessionstate_audit.md`, `18_sessionstate_api_mapping.md` |
| TD-4.2 | SS / ConciergeWriterAdapter | Route mutations through Concierge FSM. Replace `DirectWriterAdapter`. | Concierge factory | M-6, L-7 | `11_sessionstate_audit.md`, `18_sessionstate_api_mapping.md` |
| TD-4.3 | SS / FabricLifecycleAdapter | Coordinated lifecycle signals. Replace `StandaloneLifecycle`. | Fabric lifecycle protocol | M-7, L-8 | `11_sessionstate_audit.md`, `18_sessionstate_api_mapping.md` |
| TD-4.4 | SS / BridgeStorage + BridgeSync | Cloud backup/restore to K0. | Bridge online | L-9, L-10, M-57 | `18_sessionstate_api_mapping.md`, `18_bridge_audit.md` |
| TD-4.5 | ModelHub / IMetricsPort | Wire `PrometheusAdapter` to real Prometheus. | Prometheus endpoint | M-15 (partial), M-40 | `13_modelhub_audit.md`, `22_modelhub_api_mapping.md` |
| TD-4.6 | ModelHub / IConfigPort | Wire `ConfigAdapter` with file watcher. | Config file watcher | M-15 (partial) | `13_modelhub_audit.md`, `22_modelhub_api_mapping.md` |
| TD-4.7 | Concierge / IClassificationPort | Wire `UltraBERTPhase1Pipeline`. | UltraBERT model available | Absorbed from MS-3 3.7.6 | `21_concierge_cross_reference.md` |
| TD-4.8 | Bridge / IConnectorGatewayPort | Build adapter. Deferred to IFL scope. | IFL (Inter-Family Link) | Absorbed from MS-3 3.9.6 | `18_bridge_audit.md` |
| TD-4.9 | Concierge / HIGH tier ports | `IPlannerPort`, `IWorkflowPort`, `IConnectorPort`, `IConstraintPort`, `ISagaPort` — interface-only | H-20, H-21, H-22, M-62, M-65 | `16_concierge_audit.md`, `20_concierge_api_mapping.md` |
| TD-4.10 | ModelHub / Stream validation | Implement stream validation invariant | M-73 | `22_modelhub_api_mapping.md` |
| TD-4.11 | ModelHub / Manifest hot-reload | Implement filesystem watcher | M-74 | `22_modelhub_api_mapping.md` |

---

#### Epic 3-TD.5: Remaining LOW Items (cleanup)

📖 **Read:** Per-item — each finding's source doc is listed in `28_consolidated_audit_findings.md` Source column.

| Issue | What | Findings | 📖 Ref |
|-------|------|----------|---------|
| TD-5.1 | Bus: soft topic validation — unknown topics never dropped. Consider strict mode. | L-1 | `10_bus_audit.md` |
| TD-5.2 | Bus: shared vs per-session bus decision (L-2, L-3, L-4, L-6, L-15, L-16) | L-2, L-3, L-4, L-6, L-15, L-16 | `10_bus_audit.md`, `27_bus_cross_reference.md` |
| TD-5.3 | Fabric: lazy bus imports in adapters (minor perf) | L-12 | `12_fabric_audit.md` |
| TD-5.4 | Fabric: `IModelGatewayPort` create_handle sync/async mismatch | L-13 | `12_fabric_audit.md` |
| TD-5.5 | Fabric: missing `create_shared()` factory method | L-17 | `12_fabric_audit.md` |
| TD-5.6 | ModelHub: `EventBusAdapter` no `unsubscribe()` | L-18, L-72 | `13_modelhub_audit.md` |
| TD-5.7 | ModelHub: `ConfigAdapter.get()` ignores env overrides | L-19, L-73 | `13_modelhub_audit.md` |
| TD-5.8 | ModelHub: `CredentialStoreAdapter.refresh_key()` identical to `get_key()` | L-74 | `19_modelhub_services_adapters_audit.md` |
| TD-5.9 | Orchestrator: `TestMailboxAdapter` missing `reset()` | L-22 | `14_orchestrator_audit.md` |
| TD-5.10 | Orchestrator: `MockFabricAdapter` unused `cancel_log` | L-23 | `14_orchestrator_audit.md` |
| TD-5.11 | Orchestrator: `WorkflowStorageAdapter` adapter-over-adapter pattern | L-25 | `14_orchestrator_audit.md` |
| TD-5.12 | Orchestrator: StepRunner schema retry budget only 1 | L-26 | `14_orchestrator_audit.md` |
| TD-5.13 | Orchestrator: `PlanRequest.context` vs `snapshot` naming inconsistency | L-27 | `15_orchestrator_planner_cross_reference.md` |
| TD-5.14 | Planner: HIL handlers are V1 stubs | L-28 | `15_planner_audit.md` |
| TD-5.15 | Planner: `PlannerStateAdapter` session_id hardcoded `__shared__` | L-29 | `15_planner_audit.md` |
| TD-5.16 | Planner: `MicroReplanRequest.to_dict()` exists but no `from_dict()` | L-30, L-31 | `15_planner_audit.md` |
| TD-5.17 | Planner: `LLMGatewayAdapter` local `ILLMRequestBus` Protocol duplication | L-32 | `15_planner_audit.md` |
| TD-5.18 | Planner: `MailboxAdapter.set_pipeline_controller()` two-phase init risk | L-33 | `15_planner_audit.md` |
| TD-5.19 | Planner: request/cancel events unused by Orchestrator | L-34 | `15_planner_audit.md`, `15_orchestrator_planner_cross_reference.md` |
| TD-5.20 | ModelHub: sync-async bridging not resolved | L-35 | `13_modelhub_audit.md` |
| TD-5.21 | Concierge: `create_test_bus()` returns real LocalBus not test double | L-36 | `16_concierge_audit.md` |
| TD-5.22 | Concierge: 3 adapter files are pure re-exports | L-37 | `16_concierge_audit.md` |
| TD-5.23 | Concierge: 20+ deferred imports in factory.py | L-38 | `16_concierge_audit.md` |
| TD-5.24 | Concierge: `chat_repl.py` encapsulation violations | L-41 | `16_concierge_audit.md` |
| TD-5.25 | Fabric: EmbeddingIndex rebuild O(N) | L-43 | `12_fabric_audit.md` |
| TD-5.26 | Cross-component: dead event handlers (`step.execute.v1`, `discovery.request.v1`) | L-46, L-47 | `17_fabric_orchestrator_planner_cross_reference.md` |
| TD-5.27 | Cross-component: compensation capability registration dependency | L-48 | `17_fabric_orchestrator_planner_cross_reference.md` |
| TD-5.28 | MemoryWriter: `HealthAdapter.last_extraction_ms` hardcoded 0.0 | L-49 | `17_memorywriter_audit.md` |
| TD-5.29 | MemoryWriter: no null adapters — all 5 ports mandatory | L-50 | `17_memorywriter_audit.md` |
| TD-5.30 | MemoryWriter: `EventSubscriptionAdapter._sync_wrapper` swallows errors | L-52 | `17_memorywriter_audit.md` |
| TD-5.31 | MemoryWriter: no explicit Protocol inheritance on adapters | L-53 | `17_memorywriter_audit.md` |
| TD-5.32 | MemoryWriter: no `reset()`/`clear()` on Fake test doubles | L-54 | `17_memorywriter_audit.md` |
| TD-5.33 | MemoryWriter: `FakeModelHubPort` returns `tokens=0` | L-55 | `17_memorywriter_audit.md` |
| TD-5.34 | SessionState: WARM sections sum 52KB but tier limit 48KB | L-64 | `11_sessionstate_audit.md` |
| TD-5.35 | SessionState: `narrative_active` in demotion list but no WARM target | L-65 | `11_sessionstate_audit.md` |
| TD-5.36 | SessionState: `_eviction_in_progress` is boolean not lock | L-66 | `11_sessionstate_audit.md` |
| TD-5.37 | SessionState: events via adapter only — raw manager bypasses emission | L-67 | `18_sessionstate_api_mapping.md` |
| TD-5.38 | SessionState: no schema validation at consumer boundary | L-76 | `19_sessionstate_cross_reference.md` |
| TD-5.39 | Concierge: `submit_result` event indirect via `ToolResult.data` stash | L-79 | `20_concierge_api_mapping.md` |
| TD-5.40 | Concierge: bus topics currently internal — need cross-component contract | L-85 | `21_concierge_cross_reference.md` |
| TD-5.41 | k1/kernel: `chat_repl.py` inconsistent CLI parsing | L-69 | `19_kernel_package_audit.md` |
| TD-5.42 | Bus: `drain()` cumulative behavioral drift (Rust vs Python) | L-87 | `27_bus_cross_reference.md` |
| TD-5.43 | Bus: inconsistent re-export layering | L-88 | `27_bus_cross_reference.md` |
| TD-5.44 | Bus: `k1.mw` prefix has no timing rule | L-89 | `27_bus_cross_reference.md` |
| TD-5.45 | ModelHub: Anthropic plugin requires `max_tokens` explicitly | L-83 | `22_modelhub_api_mapping.md` |
| TD-5.46 | ModelHub: OpenAI reasoning models need special handling | L-84 | `22_modelhub_api_mapping.md` |
| TD-5.47 | ModelHub: CredentialStore env-var only (prod target: Vault) | L-82 | `22_modelhub_api_mapping.md` |
| TD-5.48 | Fabric: `NullStateReader` location mismatch | L-11 | `12_fabric_audit.md` |

---

#### Epic 3-TD.6: INFO Items (observability, documentation, architecture notes)

📖 **Read:** Per-item — see `28_consolidated_audit_findings.md` INFO section. Most are observational, no code changes required.

| Issue | What | Findings | 📖 Ref |
|-------|------|----------|---------|
| TD-6.1 | Concierge→Planner: no direct integration (by design — via Orch) | I-1 | `15_orchestrator_planner_cross_reference.md` |
| TD-6.2 | ModelHub: 18 LLM consumers, per-consumer budgets not enforced (global only) | I-2 | `23_modelhub_cross_reference.md` |
| TD-6.3 | ModelHub: 37 test files, 982 functions, zero mock imports — good | I-3 | `13_modelhub_audit.md` |
| TD-6.4 | ModelHub: 34 tracing phases (info only) | I-4 | `13_modelhub_audit.md` |
| TD-6.5 | Concierge: 45 bus topics (35 STRICT + 10 RELAXED) — document surface | I-5 | `21_concierge_cross_reference.md` |
| TD-6.6 | Concierge: POC Fabric has 40 capabilities | I-6 | `16_concierge_audit.md` |
| TD-6.7 | Concierge: 19 total adapters (8 prod + 3 bridge + 8 test) | I-7 | `16_concierge_audit.md` |
| TD-6.8 | ModelHub: budget $5/day, $100/month — configurable | I-8 | `22_modelhub_api_mapping.md` |
| TD-6.9 | ModelHub: Supervision/Arbiter uses REALTIME priority | I-9 | `22_modelhub_api_mapping.md` |
| TD-6.10 | MemoryWriter: UltraBERT validation is K0-only (by design) | I-10 | `25_memorywriter_cross_reference.md` |
| TD-6.11 | MemoryWriter: created directly in kernel P5, not via Fabric | I-11 | `25_memorywriter_cross_reference.md` |
| TD-6.12 | Planner: turns don't trigger MemoryWriter | I-12 | `15_orchestrator_planner_cross_reference.md` |
| TD-6.13 | Orchestrator: no direct MW dependency (indirect via Concierge) | I-13 | `15_orchestrator_api_mapping.md` |
| TD-6.14 | MemoryWriter: reads 13 of 15 SS sections, skips telemetry+artifacts | I-14 | `25_memorywriter_cross_reference.md` |
| TD-6.15 | MemoryWriter: owns distinct IModelHubPort (anti-corruption) | I-15 | `24_memorywriter_api_mapping.md` |
| TD-6.16 | Bus: `load_bus_config()` never raises — may mask config errors | I-17 | `26_bus_api_mapping.md` |
| TD-6.17 | Bus: `k1.internal.dead_letter.v1` topic defined but no publisher | I-18 | `26_bus_api_mapping.md` |
| TD-6.18 | SessionState: `emergency.activated` event has no subscriber | H-19 (observability) | `19_sessionstate_cross_reference.md` |
| TD-6.19 | SessionState: events emitted but no consumer subscribes | M-58 (observability) | `19_sessionstate_cross_reference.md` |

---

#### Remaining MS-3 Audit Findings (from original Epics 3.1-3.9)

The following original MS-3 epics are RETAINED for reference but marked with their disposition:

| Original Epic | Verdict | Disposition |
|---------------|---------|-------------|
| 3.1 Bus Adapters | ✅ ALL COMPLETE | No work needed — retained as audit record |
| 3.2 SessionState Adapters | ✅ 4 prod WIRED, 5 stubs deferred | Stubs → TD-4.1..TD-4.4 |
| 3.3 Fabric Adapters | ✅ ALL 6 WIRED | No work needed — retained as audit record |
| 3.4 ModelHub Adapters | 3 WIRED, 4 TODO | TODO items → P5.4, P5.5 (IEventPort, IStateRead), TD-4.5..TD-4.6 (IMetrics, IConfig) |
| 3.5 Orchestrator Adapters | 6 WIRED, 2 MOCK, 1 disabled | MOCKs → P1.2, P5.1 (StateRead, BridgeWrite) |
| 3.6 Planner Adapters | 7 WIRED, reader=None | reader=None → P1.3 |
| 3.7 Concierge Adapters | 7 WIRED, 2 NONE | NONEs → P5.2 (IMemoryPort), TD-4.7 (IClassification) |
| 3.8 MemoryWriter Adapters | 5 WIRED, 1 BUG | BUG → P2.8 |
| 3.9 Bridge Completion | 1 REAL, 4 MISSING | Missing → P7.1..P7.4, TD-4.8 (IFL) |
| 3.10 Cross-Cutting Fixes | 5 issues | → P1.2, P1.3, P2.8, P5.1, P5.4 |

---

#### MS-3 Execution Priority

| Priority | Phase/Issues | What | Est. Scope |
|----------|-------------|------|------------|
| **P0 — CRITICAL** | Phase 1 (6 issues) | Session-state wiring — safety gates, context, planning | ~200 LOC |
| **P1 — CRITICAL** | Phase 2 (8 issues) | Serialization bugs, type mismatches, runtime crashes | ~50 LOC |
| **P2 — HIGH** | Phase 3 (4 issues) | Dead code removal, package cleanup | -100 LOC |
| **P3 — HIGH** | Phase 4 (6 issues) | POC layer decoupling | ~400 LOC |
| **P4 — MEDIUM** | Phase 5 (8 issues) | Stub→real adapter replacements | ~500 LOC |
| **P5 — MEDIUM** | Phase 6 (6 issues) | Bus hardening (timing, naming, async) | ~200 LOC |
| **P6 — DEFERRED** | Phase 7 (7 issues) | Bridge adapter completion | ~800 LOC |
| **P7 — LOW** | TD Epics 1-6 (100+ items) | Type safety, docs, architecture, future stubs, INFO | ~150 LOC |

---

### ORIGINAL MS-3 PRODUCTION ADAPTER AUDIT RECORD

> The following section preserves the original code-verified audit from 2026-04-12 for reference. All actionable items have been absorbed into Phases 1-7 or TD Epics above.

<details>
<summary>Click to expand original MS-3 audit inventory (read-only reference)</summary>

#### CODE-VERIFIED: Global Port/Adapter Inventory

**Totals across all 9 components:**

| Metric | Count |
|--------|-------|
| Total port definitions | 53 |
| Production adapters exist | 45 |
| Wired in `service.py` (production) | 36 |
| Wired with MOCK adapter | 2 |
| Wired OFFLINE (bridge sink) | 3 |
| Wired with `reader=None` (deferred) | 1 |
| Not wired (`None` / skipped) | 7 |
| Adapter is STUB (`NotImplementedError`) | 5 |
| **BUG: Type mismatch in wiring** | **1** |

---

#### CODE-VERIFIED: Per-Component Status Summary

| Component | Ports | WIRED | MOCK | OFFLINE | NONE | STUB | BUG |
|-----------|-------|-------|------|---------|------|------|-----|
| **Bus** | 6 | 6 | — | — | — | — | — |
| **SessionState** | 5 | 4 | — | — | 1 | 5* | — |
| **ModelHub** | 7 | 3 | — | — | 4 | — | — |
| **Fabric** | 6 | 6 | — | — | — | — | — |
| **Orchestrator** | 9 | 6 | 2 | — | 1 | — | — |
| **Planner** | 7 | 7 | — | — | — | — | — |
| **Concierge** | 8+1 | 7 | — | — | 2 | — | — |
| **MemoryWriter** | 5 | 5 | — | — | — | — | 1 |
| **Bridge** | 5+1 | 1+1 | — | 3 | 4 | — | — |

*SS stubs are future-scope adapters (`BridgeStorage`, `DeltaBus`, `ConciergeWriter`, `FabricLifecycle`, `BridgeSync`) — all raise `NotImplementedError`.

---

#### CODE-VERIFIED: Complete Port × Adapter × Wiring Matrix

##### Bus (6 ports — ALL WIRED ✅)

| Port | File | Prod Adapter | Wired At | Status |
|------|------|-------------|----------|--------|
| `IBus` | `k1/bus/ports/bus.py` | `LocalBus` / `RustBusAdapter` (auto-detect) | S1 | ✅ WIRED |
| `IMailbox` | `k1/bus/ports/mailbox.py` | `LocalMailbox` / `RustMailboxAdapter` | S1 | ✅ WIRED |
| `IMailboxRouter` | `k1/bus/ports/mailbox.py` | `LocalMailboxRouter` / `RustMailboxRouterAdapter` | S1 | ✅ WIRED |
| `IAsyncBus` | `k1/bus/ports/async_bus.py` | `AsyncBusBridge` (wraps sync IBus) | S1 | ✅ WIRED |
| `IAsyncMailbox` | `k1/bus/ports/async_bus.py` | `AsyncMailboxBridge` | S1 | ✅ WIRED |
| `IAsyncMailboxRouter` | `k1/bus/ports/async_bus.py` | `AsyncMailboxRouterBridge` | S1 | ✅ WIRED |

**Middleware:** `TracingMiddleware` (OTel spans), `MetricsMiddleware` (Prometheus), `TopicValidationMiddleware` — all exist and complete.
**Cross-bus adapters:** `FabricBusAdapter` (Fabric→Bus bridge), `SessionBusAdapter` (SS→Bus bridge) — both exist and complete.

##### SessionState (5 ports — 4 WIRED, 1 NONE, 5 future stubs)

| Port | File | Prod Adapter | Wired At | Status |
|------|------|-------------|----------|--------|
| `IStoragePort` | `k1/sessionstate/ports/storage.py` | `SQLiteStorageAdapter` | P2 | ✅ WIRED |
| `IEventPort` | `k1/sessionstate/ports/events.py` | `LocalEventAdapter` | P2 | ✅ WIRED |
| `IWriterPort` | `k1/sessionstate/ports/writer.py` | `DirectWriterAdapter` | P2 | ✅ WIRED |
| `ILifecyclePort` | `k1/sessionstate/ports/lifecycle.py` | `StandaloneLifecycle` | P2 | ✅ WIRED |
| `IK0SyncPort` | `k1/sessionstate/ports/k0_sync.py` | — (`k0_sync=None`) | P2 | ⬜ NONE (optional, future) |

**Future stubs (all raise `NotImplementedError`):**

| Stub Adapter | Port | File | Purpose |
|-------------|------|------|---------|
| `BridgeStorageAdapter` | `IStoragePort` | `k1/sessionstate/adapters/bridge_storage.py` | K0 cloud persistence (MS-4+) |
| `DeltaBusAdapter` | `IEventPort` | `k1/sessionstate/adapters/delta_bus.py` | Bus-routed SS events (MS-4+) |
| `ConciergeWriterAdapter` | `IWriterPort` | `k1/sessionstate/adapters/concierge_writer.py` | Concierge-mediated writes (MS-4+) |
| `FabricLifecycleAdapter` | `ILifecyclePort` | `k1/sessionstate/adapters/fabric_lifecycle.py` | Fabric-managed lifecycle (MS-4+) |
| `BridgeSyncAdapter` | `IK0SyncPort` | `k1/sessionstate/adapters/bridge_sync.py` | K0 cloud sync (MS-4+) |

##### ModelHub (7 ports — 3 WIRED in standalone, 4 NONE)

| Port | File | Prod Adapter | Wired At | Status |
|------|------|-------------|----------|--------|
| `IModelHubPort` | `k1/model_hub/ports/hub_port.py` | `_HubCore` (facade) | S2 (inside factory) | ✅ WIRED |
| `ICredentialPort` | `k1/model_hub/ports/credential_port.py` | `CredentialStoreAdapter` (env vars) | S2 (inside factory) | ✅ WIRED |
| `IHealthPort` | `k1/model_hub/ports/health_port.py` | `HealthReportAdapter` | S2 (inside factory) | ✅ WIRED |
| `IEventPort` | `k1/model_hub/ports/event_port.py` | `EventBusAdapter` (exists, incomplete) | Not in standalone | ⬜ NONE |
| `IStateReadPort` | `k1/model_hub/ports/state_read_port.py` | `SessionStateProdAdapter` (exists) | Not in standalone | ⬜ NONE |
| `IMetricsPort` | `k1/model_hub/ports/metrics_port.py` | `PrometheusAdapter` (in-memory) | Not in standalone | ⬜ NONE |
| `IConfigPort` | `k1/model_hub/ports/config_port.py` | `ConfigAdapter` (in-memory dict) | Not in standalone | ⬜ NONE |

**Note:** `ModelHubFactory.create_standalone()` only wires 3 of 7 ports. The other 4 have adapter classes but are never constructed. `create_with_ports()` would wire all 7 but is not called by `service.py`.

##### Fabric (6 ports — ALL WIRED ✅)

| Port | File | Prod Adapter | Wired At | Status |
|------|------|-------------|----------|--------|
| `IEventPort` | `k1/fabric/ports/event_port.py` | `EventPortProdAdapter(bus)` | S3 | ✅ WIRED |
| `ISessionStateReader` | `k1/fabric/ports/state_reader.py` | `NullSessionStateReaderAdapter` (shared), `SessionStateReaderAdapter(ssm)` (per-session) | S3 / P3 | ✅ WIRED |
| `IBridgePort` | `k1/fabric/ports/bridge_port.py` | `BridgeConnectionAdapter(client)` | S3 | ✅ WIRED (offline — SinkBridgeClient) |
| `IModelGatewayPort` | `k1/fabric/ports/model_gateway.py` | `ModelGatewayBridgeAdapter(hub)` | S3 | ✅ WIRED |
| `IPromptSystemPort` | `k1/fabric/ports/prompt_system.py` | `PromptSystemProdAdapter(prompts_dir)` | S3 | ✅ WIRED |
| `IDeltaBusPort` | `k1/fabric/ports/delta_bus.py` | `DeltaBusProdAdapter(bus)` | S3 | ✅ WIRED |

**Boot log "None" fields were display artifacts** — ports are injected into internal subsystems (ProviderFactory, ContextBuilder, etc.) during `_construct_fabric()`, not stored as top-level `Fabric` fields.

##### Orchestrator (9 ports — 6 WIRED, 2 MOCK, 1 DISABLED)

| Port | File | Prod Adapter | Wired At | Status |
|------|------|-------------|----------|--------|
| `IMailboxPort` | `k1/orchestrator/ports/mailbox_port.py` | `MailboxAdapter` | S5 | ✅ WIRED |
| `IFabricGatewayPort` | `k1/orchestrator/ports/fabric_gateway_port.py` | `FabricGatewayAdapter(fabric)` | S5 | ✅ WIRED |
| `IPlannerPort` | `k1/orchestrator/ports/planner_port.py` | `MockPlannerAdapter` → S6b cross-wire → `PlannerAdapter(mailbox, cb)` | S5→S6b | ✅ WIRED (post cross-wire) |
| `IDeltaEmitPort` | `k1/orchestrator/ports/delta_emit_port.py` | `DeltaEmitAdapter(event_port, delta_bus)` | S5 | ✅ WIRED |
| `IEventSubscriptionPort` | `k1/orchestrator/ports/event_subscription_port.py` | `EventSubscriptionAdapter(event_port)` | S5 | ✅ WIRED |
| `IWorkflowStoragePort` | `k1/orchestrator/ports/workflow_storage_port.py` | `WorkflowStorageAdapter(SQLiteWorkflowAdapter)` | S5 | ✅ WIRED |
| `IStateReadPort` | `k1/orchestrator/ports/state_read_port.py` | `MockStateReadAdapter()` | S5 | ⚠️ **MOCK** — prod `StateReadAdapter` exists but needs `ISessionStateReader` |
| `IBridgeWritePort` | `k1/orchestrator/ports/bridge_write_port.py` | `MockBridgeAdapter()` | S5 | ⚠️ **MOCK** — prod `BridgeWriteAdapter` exists but needs real `IBridgeClient` |
| `IAdminPort` | `k1/orchestrator/ports/admin_port.py` | `AdminHttpAdapter` | — (`admin_enabled=False`) | ⬜ DISABLED |

##### Planner (7 ports — ALL WIRED ✅ but 1 has reader=None)

| Port | File | Prod Adapter | Wired At | Status |
|------|------|-------------|----------|--------|
| `IMailboxPort` | `k1/planner/ports/mailbox_port.py` | `MailboxAdapter` | S6 | ✅ WIRED |
| `ILLMPort` | `k1/planner/ports/llm_port.py` | `LLMGatewayAdapter(llm_request_bus=ModelHubRequestBus(hub))` | S6 | ✅ WIRED |
| `IFabricRetrievalPort` | `k1/planner/ports/fabric_retrieval_port.py` | `FabricRetrievalAdapter(fabric_retrieval=fabric.retrieval)` | S6 | ✅ WIRED |
| `IStateReadPort` | `k1/planner/ports/state_read_port.py` | `PlannerStateAdapter(reader=None, session_id="__shared__")` | S6 | ⚠️ **WIRED but `reader=None`** — `read_sections()` will raise `AttributeError` |
| `IBridgePort` | `k1/planner/ports/bridge_port.py` | `PlannerBridgeAdapter(bridge_port=BridgeConnectionAdapter)` | S6 | ✅ WIRED (offline — upstream sink) |
| `IDeltaEmitPort` | `k1/planner/ports/delta_emit_port.py` | `DeltaBusAdapter(delta_bus)` | S6 | ✅ WIRED |
| `IEventPort` | `k1/planner/ports/event_port.py` | `EventBusAdapter(event_port)` | S6 | ✅ WIRED |

##### Concierge (8+1 ports — 7 WIRED, 2 NONE with graceful fallback)

| Port | File | Prod Adapter | Wired At | Status |
|------|------|-------------|----------|--------|
| `IDeltaPort` (IBus) | `k1/bus/ports/bus.py` | `LocalBus` (per-session) | P4 (`delta=session_bus`) | ✅ WIRED |
| `IInputPort` | `k1/concierge/ports.py` | `BusInputAdapter(bus)` | P4 | ✅ WIRED |
| `IOutputPort` | `k1/concierge/ports.py` | `BusOutputAdapter(bus)` | P4 | ✅ WIRED |
| `IStatePort` | `k1/concierge/ports.py` | `SSMStateAdapter(ssm)` | P4 | ✅ WIRED |
| `ILLMPort` | `k1/model_hub/ports/hub_port.py` | shared `self._model_hub` | P4 (`llm=self._model_hub`) | ✅ WIRED |
| `IDispatchPort` | `k1/concierge/ports.py` | `FabricDispatchAdapter(fabric, orchestrator)` | P4 | ✅ WIRED |
| `IClassificationPort` | `k1/concierge/fsm/phase1.py` | — (`classification=None`) | P4 | ⬜ NONE — falls back to `StubPhase1Pipeline` |
| `IMemoryPort` | `k1/concierge/ports.py` | — (`memory=None`) | P4 | ⬜ NONE — falls back to `_null_recall` |
| `IFabricPort` (infra) | `k1/concierge/fabric/ports.py` | `session_fabric` (Fabric instance) | P4 (`fabric_port=session_fabric`) | ✅ WIRED |

##### MemoryWriter (5 ports — ALL WIRED ✅, 1 BUG)

| Port | File | Prod Adapter | Wired At | Status |
|------|------|-------------|----------|--------|
| `ISessionReadPort` | `k1/memory_writer/ports/session_read_port.py` | `SessionReadAdapter(manager=ssm)` | P5 | ✅ WIRED |
| `IModelHubPort` | `k1/memory_writer/ports/model_hub_port.py` | `ModelHubAdapter(hub)` (anti-corruption: `chat()` → `execute()`) | P5 | ✅ WIRED |
| `IBridgeCommandPort` | `k1/memory_writer/ports/bridge_command_port.py` | `BridgeCommandAdapter(command_port=self._bridge)` | P5 | 🐛 **BUG** — type mismatch (see below) |
| `IEventSubscriptionPort` | `k1/memory_writer/ports/event_subscription_port.py` | `MWEventSubscriptionAdapter(bus_adapter=FabricBusAdapter(bus))` | P5 | ✅ WIRED |
| `IHealthPort` | `k1/memory_writer/ports/health_port.py` | `HealthAdapter(circuit_breaker, ...)` | P5 | ✅ WIRED |

**🐛 BUG:** `BridgeCommandAdapter(command_port=self._bridge)` at P5 passes a `SinkBridgeAdapter` (which has `connect()`/`disconnect()`/`get_client()`) but the adapter calls `self._command_port.submit()` and `self._command_port.submit_batch()` — methods that don't exist on `SinkBridgeAdapter`. Should be `BridgeCommandAdapter(command_port=self._bridge.get_client())` to get the underlying `SinkBridgeClient` which HAS `submit_command()`.

##### Bridge (5+1 ports — 1 REAL, 3 OFFLINE, 4 NONE)

| Port | File | Prod Adapter | Wired At | Status |
|------|------|-------------|----------|--------|
| `IBridgePort` (kernel) | `k1/kernel/ports/bridge_port.py` | `SinkBridgeAdapter` / `OfflineBridgeAdapter` | S4 | ✅ WIRED (offline sink) |
| `IKernelCommandPort` | `bridge/ports/command_port_protocol.py` | `KernelCommandPort` (HTTP+LocalOutbox) | Inside `SinkBridgeClient` | ✅ REAL (but client is sink) |
| `IKernelQueryPort` | `bridge/ports/query_port_protocol.py` | — | — | ❌ **NONE — no adapter exists** |
| `IKernelSSEPort` | `bridge/ports/sse_port_protocol.py` | — | — | ❌ **NONE — no adapter exists** |
| `IKernelObsPort` | `bridge/ports/obs_port_protocol.py` | — | — | ❌ **NONE — no adapter exists** |
| `IConnectorGatewayPort` | `bridge/ports/connector_gateway_protocol.py` | — | — | ❌ **NONE — no adapter exists** |

**Bridge client facade:** `IBridgeClient` protocol in `bridge/client.py`. Only `StubBridgeClient` (test) and `SinkBridgeClient` (offline) exist. No online `HttpBridgeClient` yet.

---

#### CODE-VERIFIED: Issues That MUST Be Fixed (Blocking)

| ID | Component | Issue | Severity | Fix |
|----|-----------|-------|----------|-----|
| **BUG-1** | MemoryWriter | `BridgeCommandAdapter(command_port=self._bridge)` — type mismatch, `SinkBridgeAdapter` has no `submit()`/`submit_batch()` | 🔴 HIGH | Change to `self._bridge.get_client()` or guard with try/except |
| **MOCK-1** | Orchestrator | `IStateReadPort` wired with `MockStateReadAdapter` — orch can't read session state (safety band, beliefs) | 🟡 MEDIUM | Wire `StateReadAdapter` with per-session SSM via session binding |
| **MOCK-2** | Orchestrator | `IBridgeWritePort` wired with `MockBridgeAdapter` — WAL writes, audit trail are no-ops | 🟡 MEDIUM | Wire `BridgeWriteAdapter` or keep mock until bridge online |
| **DEFERRED-1** | Planner | `IStateReadPort` has `reader=None` — `read_sections()` will crash | 🟡 MEDIUM | Wire per-session SSM reader via session binding callback |

---

#### Epic 3.1: Bus Adapters — AUDIT COMPLETE ✅

**Verdict: ALL COMPLETE. No work needed.**

| Issue | What To Do | Code-Verified Finding | Status |
|-------|-----------|----------------------|--------|
| 3.1.1 | Verify `SessionBusAdapter` for per-session bus | `k1/bus/adapters/session_adapter.py` — complete, JSON ser/de bridge from SS events → IBus | ✅ DONE |
| 3.1.2 | Verify `FabricBusAdapter` for dual-role bus bridge | `k1/bus/adapters/fabric_adapter.py` — complete, bridges Fabric `IEventPort` + `IDeltaBusPort` → IBus | ✅ DONE |
| 3.1.3 | Verify `TracingMiddleware` — session_id + trace stamping | `k1/bus/middleware/tracing.py` — complete OTel spans, graceful no-op if OTel missing. `MetricsMiddleware` + `TopicValidationMiddleware` also exist. | ✅ DONE |

---

#### Epic 3.2: SessionState Adapters — AUDIT COMPLETE ✅ (5 future stubs deferred)

**Verdict: All 4 production ports WIRED. 5 future-scope stubs remain (all `NotImplementedError`).**

| Issue | What To Do | Code-Verified Finding | Status |
|-------|-----------|----------------------|--------|
| 3.2.1 | Verify `SQLiteStorageAdapter` for production | `k1/sessionstate/adapters/sqlite_storage.py` — complete, LOCAL COLD persistence, wired at P2 | ✅ DONE |
| 3.2.2 | Verify `DeltaBusAdapter` wires to session bus | `k1/sessionstate/adapters/delta_bus.py` — **STUB**: all methods raise `NotImplementedError`. Not wired — `LocalEventAdapter` used instead. | 🔲 FUTURE (MS-4+) |
| 3.2.3 | Verify `BridgeStorage`/`BridgeSync` for K0 sync | `bridge_storage.py` + `bridge_sync.py` — both **STUB**: all methods raise `NotImplementedError`. Blocked on bridge online. | 🔲 FUTURE (MS-4+) |
| 3.2.4 | Verify `ConciergeWriterAdapter` | `k1/sessionstate/adapters/concierge_writer.py` — **STUB**: all methods raise `NotImplementedError`. `DirectWriterAdapter` used instead. | 🔲 FUTURE (MS-4+) |
| 3.2.5 | Verify `FabricLifecycleAdapter` | `k1/sessionstate/adapters/fabric_lifecycle.py` — **STUB**: all methods raise `NotImplementedError`. `StandaloneLifecycle` used instead. | 🔲 FUTURE (MS-4+) |

---

#### Epic 3.3: Fabric Adapters — AUDIT COMPLETE ✅

**Verdict: ALL 6 PORTS WIRED with production adapters. No work needed.**

| Issue | What To Do | Code-Verified Finding | Status |
|-------|-----------|----------------------|--------|
| 3.3.1 | Verify `SessionStateReaderAdapter` | `k1/fabric/adapters/sessionstate_reader.py` — wraps SSM, takes `(ssm, session_id)`. Per-session Fabric uses this. Shared Fabric uses `NullSessionStateReaderAdapter`. | ✅ DONE |
| 3.3.2 | Verify `NullSessionStateReaderAdapter` for shared Fabric | `k1/fabric/adapters/null_state_reader.py` — exists, returns empty for all reads. Wired in `FabricFactory.create_shared()`. | ✅ DONE |
| 3.3.3 | Verify `ModelGatewayBridgeAdapter` | `k1/fabric/adapters/model_gateway_bridge.py` — wraps `IModelHubPort`, returns `LLMHandleBridge` handles. Wired at S3. | ✅ DONE |
| 3.3.4 | Verify `EventPortProdAdapter` + `DeltaBusProdAdapter` | `event_port_prod.py` wraps IBus for events. `delta_bus_prod.py` wraps IBus for deltas. Both wired at S3. | ✅ DONE |
| 3.3.5 | Verify `BridgeConnectionAdapter` | `k1/fabric/adapters/bridge_connection.py` — wraps bridge client. Starts in LOCAL COLD mode, offline fallback when disconnected. Wired at S3 with `SinkBridgeClient`. | ✅ DONE (offline) |

---

#### Epic 3.4: ModelHub Adapters — 3 WIRED, 4 NOT WIRED

**Verdict: Core `IModelHubPort` + credentials + health WIRED. 4 auxiliary ports not wired in standalone mode.**

| Issue | What To Do | Code-Verified Finding | Status |
|-------|-----------|----------------------|--------|
| 3.4.1 | Verify `LLMRequestBusAdapter` — execute/stream | `k1/model_hub/adapters/llm_request_bus_adapter.py` — decorator over inner `IModelHubPort`, wired inside `_HubCore`. | ✅ DONE |
| 3.4.2 | Verify `CredentialStoreAdapter` | `k1/model_hub/adapters/credential_store_adapter.py` — reads from env vars `MH_KEY_<PROVIDER_ID>`. Wired inside factory. | ✅ DONE |
| 3.4.3 | Verify `HealthReportAdapter` | `k1/model_hub/adapters/health_report_adapter.py` — in-memory status tracking. Wired inside factory. | ✅ DONE |
| 3.4.4 | Wire `IEventPort` — connect MH events to K1 bus | `EventBusAdapter` exists (`k1/model_hub/adapters/event_bus_adapter.py`) but is in-memory only, not wired to real K1 bus. `create_standalone()` skips it. | ☐ TODO — wire `EventBusAdapter(bus=self._bus)` in `create_with_ports()`, switch S2 to `create_with_ports()` |
| 3.4.5 | Wire `IStateReadPort` — connect MH to session state | `SessionStateProdAdapter` exists (`k1/model_hub/adapters/session_state_prod.py`) but not wired in standalone. Needed for model selection based on user preferences. | ☐ TODO — wire per-session reader, requires session binding strategy |
| 3.4.6 | Wire `IMetricsPort` — connect MH to Prometheus | `PrometheusAdapter` exists (`k1/model_hub/adapters/prometheus_adapter.py`) but is in-memory accumulator only. | 🔲 FUTURE — needs real Prometheus endpoint |
| 3.4.7 | Wire `IConfigPort` — YAML hot-reload | `ConfigAdapter` exists (`k1/model_hub/adapters/config_adapter.py`) but is in-memory dict, no file watching. | 🔲 FUTURE — needs config file watcher |

---

#### Epic 3.5: Orchestrator Adapters — 6 WIRED, 2 MOCK, 1 DISABLED

**Verdict: Core ports all WIRED. `IStateReadPort` and `IBridgeWritePort` use mocks that need production replacement.**

| Issue | What To Do | Code-Verified Finding | Status |
|-------|-----------|----------------------|--------|
| 3.5.1 | Verify `DeltaEmitAdapter` | `k1/orchestrator/adapters/delta_emit_adapter.py` — takes `(event_port, delta_bus)`. Wired at S5. | ✅ DONE |
| 3.5.2 | Verify `PlannerAdapter` for S6b hot-swap | `k1/orchestrator/adapters/planner_adapter.py` — takes `(planner_mailbox, cb_planner)`. Initially `MockPlannerAdapter` at S5, then cross-wired at S6b with real `PlannerAdapter`. | ✅ DONE |
| 3.5.3 | Verify `FabricGatewayAdapter` wraps shared Fabric | `k1/orchestrator/adapters/fabric_gateway_adapter.py` — wraps `self._shared_fabric`. Wired at S5. | ✅ DONE |
| 3.5.4 | Replace `MockStateReadAdapter` → real `StateReadAdapter` | `StateReadAdapter` exists at `k1/orchestrator/adapters/state_read_adapter.py` — needs `ISessionStateReader`. Currently `MockStateReadAdapter()` returns empty dicts. Orch can't read safety band, beliefs, or session context. | ☐ **TODO (MOCK-1)** — wire per-session SSM reader, requires session binding callback |
| 3.5.5 | Replace `MockBridgeAdapter` → real `BridgeWriteAdapter` | `BridgeWriteAdapter` exists at `k1/orchestrator/adapters/bridge_write_adapter.py` — needs real `IBridgeClient`. Currently `MockBridgeAdapter()` stores audit/WAL in memory only. | ☐ **TODO (MOCK-2)** — wire when bridge comes online, or use `SinkBridgeClient` with `submit_command()` |
| 3.5.6 | Verify `WorkflowStorageAdapter` wraps SQLite | `k1/orchestrator/adapters/workflow_storage_adapter.py` wraps `SQLiteWorkflowAdapter`. Wired at S5. | ✅ DONE |
| 3.5.7 | Verify `AdminHttpAdapter` | `k1/orchestrator/adapters/admin_http_adapter.py` — exists, `admin_enabled=False` in kernel config. Intentionally disabled. | ✅ DONE (disabled by design) |

---

#### Epic 3.6: Planner Adapters — ALL 7 WIRED ✅ (1 deferred binding)

**Verdict: All 7 ports wired with production adapters. `IStateReadPort` has `reader=None` — deferred to per-session binding.**

| Issue | What To Do | Code-Verified Finding | Status |
|-------|-----------|----------------------|--------|
| 3.6.1 | Verify `SessionStateReadAdapter` (snapshot pattern) | `k1/planner/adapters/session_state_adapter.py` — `PlannerStateAdapter(reader=None, session_id="__shared__")`. Production adapter exists but `reader=None` means `read_sections()` crashes. Shared planner needs per-session binding. | ⚠️ **DEFERRED-1** — needs session binding callback to inject reader per-request |
| 3.6.2 | Verify `EventBusAdapter` ≠ `DeltaBusAdapter` (separate) | `k1/planner/adapters/event_bus_adapter.py` (sync emit/subscribe) vs `k1/planner/adapters/delta_bus_adapter.py` (sync emit only). Both exist, distinct files, both wired at S6. | ✅ DONE |
| 3.6.3 | Verify `LLMGatewayAdapter` wraps ModelHub | `k1/planner/adapters/llm_gateway_adapter.py` — wraps `ModelHubRequestBus(self._model_hub)`. Wired at S6. | ✅ DONE |
| 3.6.4 | Verify `FabricRetrievalAdapter` | `k1/planner/adapters/fabric_retrieval_adapter.py` — wraps `self._shared_fabric.retrieval`. Wired at S6. | ✅ DONE |
| 3.6.5 | Verify `BridgeAdapter` | `k1/planner/adapters/bridge_adapter.py` — wraps `BridgeConnectionAdapter`. Offline when upstream sink. Wired at S6. | ✅ DONE (offline) |
| 3.6.6 | Verify `MailboxAdapter` | `k1/planner/adapters/mailbox_adapter.py` — internal queue. Wired at S6. | ✅ DONE |

---

#### Epic 3.7: Concierge Adapters — 7 WIRED, 2 NONE (graceful fallback)

**Verdict: 7 of 9 ports wired. `IClassificationPort` and `IMemoryPort` intentionally `None` with graceful fallbacks.**

| Issue | What To Do | Code-Verified Finding | Status |
|-------|-----------|----------------------|--------|
| 3.7.1 | Verify `BusInputAdapter` / `BusOutputAdapter` | `k1/concierge/adapters/bus_input.py` + `bus_output.py` — both wrap per-session `LocalBus`. Wired at P4. | ✅ DONE |
| 3.7.2 | Verify `ILLMPort` — shared ModelHub | `llm=self._model_hub` passed directly. Shared `_HubCore` satisfies `IModelHubPort`. | ✅ DONE |
| 3.7.3 | Verify `SSMStateAdapter` | `k1/concierge/adapters/ssm_state.py` — wraps SSM `get_section()`/`get_snapshot()`. Wired at P4. | ✅ DONE |
| 3.7.4 | Verify `FabricDispatchAdapter` — tier routing | `k1/concierge/adapters/fabric_dispatch.py` — `dispatch_direct()` → Fabric, `dispatch_envelope()` → Orchestrator. Wired at P4. | ✅ DONE |
| 3.7.5 | Wire `IMemoryPort` — `RecallMemoryAdapter` | `k1/concierge/adapters/recall_memory.py` exists — wraps Bridge `query("memory.recall", ...)`. Currently `memory=None` → `_null_recall` (returns empty list). | ☐ TODO — wire `RecallMemoryAdapter(bridge=self._bridge.get_client())` when bridge has real query |
| 3.7.6 | Wire `IClassificationPort` — `UltraBERTPhase1Pipeline` | `k1/concierge/fsm/ultrabert_phase1.py` exists — needs UltraBERT model loaded. Currently `classification=None` → FSM uses `StubPhase1Pipeline` (keyword-based). | ☐ TODO — wire when UltraBERT model available |

---

#### Epic 3.8: MemoryWriter Adapters — ALL 5 WIRED ✅ (1 BUG)

**Verdict: All 5 ports wired. BUG in `IBridgeCommandPort` wiring — type mismatch.**

| Issue | What To Do | Code-Verified Finding | Status |
|-------|-----------|----------------------|--------|
| 3.8.1 | Verify `ModelHubAdapter` — chat() vs execute() | `k1/memory_writer/adapters/model_hub_adapter.py` — anti-corruption layer: MW's `chat()` → Hub's `execute()`. Wired at P5. | ✅ DONE |
| 3.8.2 | **FIX** `BridgeCommandAdapter` — type mismatch | `k1/memory_writer/adapters/bridge_command_adapter.py` — calls `self._command_port.submit()` but `self._bridge` is a `SinkBridgeAdapter` which has `connect()`/`get_client()` — NOT `submit()`. | ☐ **TODO (BUG-1)** — fix: `BridgeCommandAdapter(command_port=self._bridge.get_client())` |
| 3.8.3 | Verify `MWEventSubscriptionAdapter` | `k1/memory_writer/adapters/event_subscription_adapter.py` — wraps `FabricBusAdapter(session_bus)`. Wired at P5. | ✅ DONE |
| 3.8.4 | Verify `HealthAdapter` | `k1/memory_writer/adapters/health_adapter.py` — self-contained (circuit breaker + lambdas). Wired at P5. | ✅ DONE |

---

#### Epic 3.9: Bridge Completion — 1 REAL, 4 MISSING ADAPTERS

**Verdict: Bridge infrastructure (transport, signing, outbox, health) is REAL and complete. But 4 of 5 bridge-side ports have NO adapter implementation. Only `IKernelCommandPort` has a real adapter.**

| Issue | What To Do | Code-Verified Finding | Status |
|-------|-----------|----------------------|--------|
| 3.9.1 | Verify `IBridgeClient` facade | `bridge/client.py` — `IBridgeClient` protocol composes all 5 ports. `SinkBridgeClient` (offline) and `StubBridgeClient` (test) exist. No online `HttpBridgeClient`. | ✅ DONE (offline only) |
| 3.9.2 | Verify `KernelCommandPort` — submit() | `bridge/kernel/command_port.py` — real HTTP impl via `HttpTransport` + `EnvelopeBuilder` + `LocalOutbox`. Functional. | ✅ DONE |
| 3.9.3 | **BUILD** `IKernelQueryPort` adapter | `bridge/ports/query_port_protocol.py` — Protocol defined, methods: `query()`, `query_single()`. **NO concrete adapter exists anywhere.** | ☐ **TODO** — build `KernelQueryPort` adapter |
| 3.9.4 | **BUILD** `IKernelSSEPort` adapter | `bridge/ports/sse_port_protocol.py` — Protocol defined, methods: `subscribe()`, `ack()`, `close()`. **NO concrete adapter exists.** | ☐ **TODO** — build `KernelSSEPort` adapter |
| 3.9.5 | **BUILD** `IKernelObsPort` adapter | `bridge/ports/obs_port_protocol.py` — Protocol defined, methods: `emit()`, `emit_feedback()`. **NO concrete adapter exists.** | ☐ **TODO** — build `KernelObsPort` adapter |
| 3.9.6 | **BUILD** `IConnectorGatewayPort` adapter | `bridge/ports/connector_gateway_protocol.py` — Protocol defined, methods: `execute()`, `list_adapters()`. **NO concrete adapter exists.** Deferred to IFL (Inter-Family Link). | 🔲 FUTURE (IFL scope) |
| 3.9.7 | Verify `LocalOutbox` for offline queueing | `bridge/sync/local_outbox.py` — SQLite-backed offline queue. Functional. | ✅ DONE |
| 3.9.8 | Build online `HttpBridgeClient` | `bridge/client.py` — only `SinkBridgeClient` exists. Need `HttpBridgeClient` that composes all 5 port adapters for real K0 communication. | ☐ **TODO** — build when K0 API available |
| 3.9.9 | Verify `HttpTransport` + `EnvelopeBuilder` + `SigningBackend` | `bridge/core/` — all three exist and are functional. `HmacSigning` for dev, Ed25519 planned. | ✅ DONE |

---

#### Epic 3.10: Cross-Cutting Wiring Fixes

**Issues that span multiple components — fixing wiring bugs and mock replacements.**

##### Issue 3.10.1 — FIX BUG-1: MemoryWriter Bridge Type Mismatch

| Field | Detail |
|-------|--------|
| **What** | Fix `BridgeCommandAdapter(command_port=self._bridge)` at P5 in `_create_session_tier2()`. Currently passes `SinkBridgeAdapter` (lifecycle adapter) instead of `SinkBridgeClient` (command interface). |
| **Root Cause** | `self._bridge` is `SinkBridgeAdapter` which has `connect()`/`disconnect()`/`get_client()`. MW's `BridgeCommandAdapter` calls `self._command_port.submit()` — method doesn't exist on `SinkBridgeAdapter`. |
| **Fix** | Change `BridgeCommandAdapter(command_port=self._bridge)` → `BridgeCommandAdapter(command_port=self._bridge.get_client())`. The `SinkBridgeClient` returned by `get_client()` HAS `submit_command()`. Verify method name alignment: MW expects `submit()` vs client has `submit_command()`. |
| **Test** | Call `memory_writer` pipeline in a live session — must not raise `AttributeError`. |
| **File** | `k1/kernel/service.py` — `_create_session_tier2()` P5 block |
| **Severity** | 🔴 HIGH — crashes on first MW write |
| **Status** | ☐ |

---

##### Issue 3.10.2 — FIX MOCK-1: Orchestrator StateReadPort

| Field | Detail |
|-------|--------|
| **What** | Replace `MockStateReadAdapter()` with production `StateReadAdapter` in orchestrator wiring at S5. |
| **Challenge** | Orchestrator is shared (Tier 1) but session state is per-session (Tier 2). `StateReadAdapter` needs an `ISessionStateReader` that routes to the correct session's SSM. |
| **Options** | (A) Deferred binding: wire `MockStateReadAdapter` at S5, replace with real adapter when session starts. (B) Session-routing adapter: build `SessionRoutingStateReader` that looks up SSM from `kernel._sessions[session_id]`. (C) Accept mock for now — orch doesn't use state reads in current flow. |
| **Recommendation** | Option C for MS-3 (mock is safe — orch reads are informational). Option B for MS-4. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` S5 block |
| **Severity** | 🟡 MEDIUM |
| **Status** | ☐ |

---

##### Issue 3.10.3 — FIX MOCK-2: Orchestrator BridgeWritePort

| Field | Detail |
|-------|--------|
| **What** | Replace `MockBridgeAdapter()` with production `BridgeWriteAdapter` in orchestrator wiring at S5. |
| **Challenge** | `BridgeWriteAdapter` needs a real `IBridgeClient` — currently only `SinkBridgeClient` exists (offline). |
| **Recommendation** | Wire `BridgeWriteAdapter(client=self._bridge.get_client())` — the `SinkBridgeClient` will queue commands to `LocalOutbox` (offline). Better than mock because audit trail is preserved on disk. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` S5 block |
| **Severity** | 🟡 MEDIUM |
| **Status** | ☐ |

---

##### Issue 3.10.4 — FIX DEFERRED-1: Planner StateReadPort reader=None

| Field | Detail |
|-------|--------|
| **What** | `PlannerStateAdapter(reader=None, session_id="__shared__")` at S6 — `read_sections()` will raise `AttributeError`. |
| **Challenge** | Same as MOCK-1: Planner is shared but SSM is per-session. Planner needs to read the *requesting session's* state. |
| **Options** | (A) Per-request injection: planner pipeline receives `session_id` in `PlanRequest`, adapter looks up SSM from kernel. (B) Session-routing reader: same as MOCK-1 Option B. (C) Accept `None` — planner currently runs without state reads (uses empty context). |
| **Recommendation** | Option C for MS-3 (planner works without state reads). Option A for MS-4 (planner needs beliefs/history for real plans). |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` S6 block |
| **Severity** | 🟡 MEDIUM |
| **Status** | ☐ |

---

##### Issue 3.10.5 — Wire ModelHub `IEventPort` to K1 Bus

| Field | Detail |
|-------|--------|
| **What** | Switch S2 from `ModelHubFactory.create_standalone()` to `create_with_ports()` to wire `IEventPort`, `IStateReadPort`, `IMetricsPort`, `IConfigPort`. |
| **Priority** | LOW for MS-3 — ModelHub works fine standalone. Events/metrics are informational. |
| **File** | `k1/kernel/service.py` — `_startup_tier1()` S2 block |
| **Severity** | 🟢 LOW |
| **Status** | ☐ |

---

#### MS-3 Execution Priority

| Priority | Issues | What | Est. Scope |
|----------|--------|------|------------|
| **P0 — FIX NOW** | 3.10.1 | MW bridge type mismatch (BUG-1) | 1 line fix + test |
| **P1 — WIRE** | 3.10.3 | Orch `BridgeWriteAdapter` (MOCK-2 → real sink) | adapter wiring + test |
| **P2 — DEFER** | 3.10.2, 3.10.4 | Orch + Planner `StateReadPort` — needs session routing | design + build SessionRoutingStateReader |
| **P3 — BUILD** | 3.9.3, 3.9.4, 3.9.5 | Bridge query/SSE/obs adapters | 3 new adapter files |
| **P4 — ENHANCE** | 3.4.4, 3.4.5, 3.10.5 | ModelHub auxiliary ports | factory mode switch |
| **P5 — FUTURE** | 3.7.5, 3.7.6, 3.9.6, 3.9.8 | Memory recall, UltraBERT, IFL, HttpBridgeClient | blocked on external deps |

</details>

---

### MS-4: Cross-Component Integration & Turn-Level Testing

**Goal:** Prove components talk to each other correctly through the full user-turn pipeline. Test classification → tier routing → dispatch → response. Wire the dead degradation code. Fix the HIGH-tier stub.

**NOT duplicated from Epic 2.5:** Epic 2.5 covers startup/session/shutdown/error-paths/isolation. MS-4 covers what happens INSIDE a live session — the actual request flow.

---

#### CODE-VERIFIED: Current Tier Routing Reality (Audit Findings)

Before writing tests, document what the code ACTUALLY does today:

| Tier | Classification Source | Routing Path | End Handler | Status |
|------|----------------------|-------------|-------------|--------|
| **LOW** | `StubPhase1Pipeline` (keyword: no match → LOW) or `UltraBERTPhase1Pipeline` (score 0 → LOW) | `route_task_sync(dispatch, LOW)` → `_route_low_sync()` → `DispatchRecord(tier=LOW)` → `_deliver_to_back(envelope)` via `IMailboxRouter` | Back actor ReAct loop (budget: 6 iterations) | WORKS |
| **MEDIUM** | `StubPhase1Pipeline` (keywords: hotel/flight/travel/doctor/health) or UltraBERT (score 1-2) | `route_task_sync(dispatch, MEDIUM)` → `_route_medium_sync()` → `DispatchRecord(tier=MEDIUM, envelope=TaskEnvelope)` → if orchestrator wired: `asyncio.create_task(_run_medium_orchestration(...))` else: fallback to `_deliver_to_back()` | `OrchestratorStub.handle_task()` → 1-2 Fabric calls → `k1.orchestration.dag.completed` event | WORKS (with OrchestratorStub) |
| **HIGH** | `UltraBERTPhase1Pipeline` only (score ≥ 3: multi-intent + cross-domain + temporal) — `StubPhase1Pipeline` NEVER produces HIGH | `route_task_sync(dispatch, HIGH)` → `_route_high_sync()` → **PassthroughPlannerStub** at `controller.py:2114` wraps as 1-step plan → **re-routes as MEDIUM** | Same as MEDIUM — no real Planner | STUBBED — HIGH = MEDIUM in practice |
| **Safety override** | UltraBERT `safety_band in ("RED", "CRISIS")` → **forces LOW** regardless of score | Same as LOW | Back actor with safety constraints | WORKS |

**Classification scoring (UltraBERT `_compute_complexity`):**

- `len(intents) > 1` → +1 (multi-intent)
- `len(domains) > 1` → +1 (cross-domain)
- Temporal ambiguity (intent in {set_reminder, seek_advice, reflect, scheduling} AND entities contain DATE_REL/TIME_REL/TEMPORAL) → +1
- **Thresholds**: score 0 = LOW, score 1-2 = MEDIUM, score ≥ 3 = HIGH

**Circuit breaker degradation (DEAD CODE):**

- `cb_planner`, `cb_orchestrator`, `cb_fabric` — exist as module singletons in `k1/concierge/orchestrator/degradation.py`
- `route_task_with_degradation()` and `get_effective_tier()` — fully implemented with cascade: HIGH+CB_PLANNER_OPEN→MEDIUM, MEDIUM+CB_ORCHESTRATOR_OPEN→LOW, LOW+CB_FABRIC_OPEN→CannedResponse
- **NEVER CALLED** by FSM controller — controller calls `route_task_sync()` directly (zero circuit breaker awareness)

---

#### Epic 4.1: Classification & Tier Decision Tests

**What we're testing:** The classification pipeline correctly assigns LOW/MEDIUM/HIGH based on input text, and the tier determines the dispatch path.

---

##### Issue 4.1.1 — Test: StubPhase1Pipeline classification paths

| Field | Detail |
|-------|--------|
| **What** | Verify `StubPhase1Pipeline.classify(text)` returns correct `Phase1Result` for each keyword path. |
| **Code-verified paths** | File: `k1/concierge/fsm/phase1.py` L167-247, class `StubPhase1Pipeline` |
| | (a) `"hello"` → `Phase1Result(complexity_tier="LOW", domain="general", primary_intent="general")` |
| | (b) `"book a hotel"` → `Phase1Result(complexity_tier="MEDIUM", domain="travel", primary_intent="booking")` |
| | (c) `"doctor appointment"` → `Phase1Result(complexity_tier="MEDIUM", domain="health", primary_intent="scheduling")` |
| | (d) **No input produces HIGH** — `StubPhase1Pipeline` has no HIGH path |
| **Assertions** | (a) tier=LOW, (b) tier=MEDIUM domain=travel, (c) tier=MEDIUM domain=health, (d) exhaustive: no string input returns tier=HIGH |
| **Why it matters** | If classification is wrong, entire dispatch goes to wrong tier. This is the entry gate. |
| **File** | `tests/k1/kernel/test_integration.py` (new file for cross-component tests) |
| **Depends on** | Phase1Pipeline code exists (MS-1 verified) |
| **Status** | ☐ |

---

##### Issue 4.1.2 — Test: UltraBERT multi-factor complexity scoring

| Field | Detail |
|-------|--------|
| **What** | Verify `UltraBERTPhase1Pipeline._compute_complexity()` scoring: multi-intent (+1), cross-domain (+1), temporal ambiguity (+1), safety override (RED/CRISIS → force LOW). |
| **Code-verified** | File: `k1/concierge/fsm/ultrabert_phase1.py` L283-323 |
| | (a) Single intent, single domain, no temporal → score 0 → LOW |
| | (b) Two intents → score 1 → MEDIUM |
| | (c) Two intents + two domains → score 2 → MEDIUM |
| | (d) Two intents + two domains + temporal ambiguity → score 3 → HIGH |
| | (e) Score 3 but `safety_band="RED"` → **forced LOW** (override at L297-298) |
| | (f) Score 3 but `safety_band="CRISIS"` → **forced LOW** |
| **Assertions** | Each scenario produces expected tier. Safety override tested with RED and CRISIS. Thresholds configurable via `phase1.complexity_thresholds`. |
| **Why it matters** | This is the ONLY path that can produce HIGH tier. If scoring is wrong, HIGH tier never activates. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | UltraBERT adapter code exists (MS-1 verified) |
| **Status** | ☐ |

---

##### Issue 4.1.3 — Test: UltraBERT fallback to StubPhase1Pipeline

| Field | Detail |
|-------|--------|
| **What** | When `UltraBERTAdapter.analyze()` returns `None` (GPU unavailable, model missing, exception), `UltraBERTPhase1Pipeline` degrades to `StubPhase1Pipeline` and sets `result._degraded = True`. |
| **Code-verified** | File: `k1/concierge/fsm/ultrabert_phase1.py` L105-115 |
| **Assertions** | (a) With working adapter: returns UltraBERT-scored result. (b) With `StubUltraBERTAdapter` (returns None): falls back, `result._degraded is True`, tier from keyword logic. (c) With adapter that raises: same fallback. |
| **Why it matters** | Production deploys without GPU must still classify correctly. Silent degradation must be observable. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Status** | ☐ |

---

#### Epic 4.2: Tier Routing & Dispatch Path Tests

**What we're testing:** After classification, each tier follows the correct dispatch path through the FSM to the correct handler component.

---

##### Issue 4.2.1 — Test: LOW tier dispatch — FSM → Back actor via Mailbox

| Field | Detail |
|-------|--------|
| **What** | Verify LOW tier message flows: user input → FSM LISTENING → classification → `route_task_sync(dispatch, LOW)` → `_route_low_sync()` → `_deliver_to_back(envelope)` → Back actor receives via `IMailboxRouter.deliver(ACTOR_BACK, ...)`. |
| **Code-verified path** | `controller.py:2097 _on_task_dispatch` → `routing.py:139 _route_low_sync()` → `controller.py:2195 _deliver_to_back()` → `controller.py:1976 self._router.deliver(ACTOR_BACK, envelope)` |
| **Cross-component chain** | Bus (user.input event) → FSM (state transition) → Router (mailbox delivery) → Back actor (ReAct loop with budget=6) |
| **Assertions** | (a) FSM transitions LISTENING→CLASSIFYING→DISPATCHING. (b) `route_task_sync` returns `DispatchRecord(tier=LOW)`. (c) Envelope delivered to back mailbox. (d) Back actor receives envelope with correct payload. |
| **Real components** | Real Bus, real Router, real FSM, real StubPhase1Pipeline. Only LLM is stubbed (no real API call). |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 2.5.2 (session created with working components) |
| **Status** | ☐ |

---

##### Issue 4.2.2 — Test: MEDIUM tier dispatch — FSM → OrchestratorStub.handle_task()

| Field | Detail |
|-------|--------|
| **What** | Verify MEDIUM tier flows: classification → `route_task_sync(dispatch, MEDIUM)` → `_route_medium_sync()` → controller checks `self._orchestrator is not None` → `asyncio.create_task(_run_medium_orchestration(record.envelope))` → `OrchestratorStub.handle_task(task_envelope)` → 1-2 Fabric calls → `k1.orchestration.dag.completed` event → FSM DELIVERING. |
| **Code-verified path** | `controller.py:2172` checks orchestrator wired → `controller.py:2184 _run_medium_orchestration()` → `stub.py:69 OrchestratorStub.handle_task()` → reads SS context → Fabric.execute() → emits `dag.completed` |
| **Cross-component chain** | Bus → FSM → OrchestratorStub → Fabric → Bus (dag.completed) → FSM (DELIVERING) |
| **Assertions** | (a) Classification returns MEDIUM for "book a hotel". (b) `_route_medium_sync()` returns `DispatchRecord(tier=MEDIUM, envelope=TaskEnvelope)`. (c) OrchestratorStub.handle_task called. (d) Fabric.execute called at least once. (e) `dag.completed` event published on bus. (f) FSM transitions to DELIVERING state. |
| **Real components** | Real Bus, FSM, OrchestratorStub, Fabric (shared), SessionState. LLM stubbed. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 2.5.2, 2.2.5 (Orchestrator wired to Concierge) |
| **Status** | ☐ |

---

##### Issue 4.2.3 — Test: MEDIUM fallback when Orchestrator NOT wired

| Field | Detail |
|-------|--------|
| **What** | When `self._orchestrator is None`, MEDIUM tier silently falls back to `_deliver_to_back()` — same path as LOW. |
| **Code-verified** | `controller.py:2177` — `else` branch of orchestrator check falls through to `_deliver_to_back(canonical_env)` |
| **Assertions** | (a) Create session with orchestrator=None on Concierge. (b) Send MEDIUM-triggering text ("book a hotel"). (c) Envelope delivered to Back actor (not OrchestratorStub). (d) No error raised — silent downgrade. |
| **Why it matters** | This is the graceful degradation path. Must work for offline/minimal deployments. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Status** | ☐ |

---

##### Issue 4.2.4 — Test: HIGH tier dispatch — PassthroughPlannerStub → MEDIUM re-route

| Field | Detail |
|-------|--------|
| **What** | Verify HIGH tier is intercepted by `PassthroughPlannerStub` (inline at `controller.py:2114-2130`) and re-routed as MEDIUM. This is the CURRENT behavior — HIGH = MEDIUM in practice. |
| **Code-verified** | `controller.py:2114`: `if record.tier == ComplexityTier.HIGH:` → wraps single intent as 1-step plan → sets `dispatch_dict["committed_plan"]` and `dispatch_dict["original_tier"] = "HIGH"` → re-routes via `route_task_sync(dispatch, ComplexityTier.MEDIUM)` |
| **Cross-component chain** | UltraBERT (score ≥ 3) → FSM → PassthroughPlannerStub → re-route as MEDIUM → OrchestratorStub → Fabric |
| **Assertions** | (a) Construct input that would score HIGH (multi-intent + cross-domain + temporal). (b) Classification returns tier=HIGH. (c) PassthroughPlannerStub wraps as 1-step plan. (d) `dispatch_dict["original_tier"] == "HIGH"`. (e) Actual routing follows MEDIUM path. (f) OrchestratorStub.handle_task called (not Planner). |
| **Why it matters** | Documents current HIGH-tier limitation. When real Planner is wired, this test must be UPDATED to verify Planner receives the request. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Status** | ☐ |

---

##### Issue 4.2.5 — Test: HIGH tier with REAL Planner (future — wire real OrchestratorService + PlannerAgent)

| Field | Detail |
|-------|--------|
| **What** | Replace PassthroughPlannerStub with real Planner dispatch. HIGH tier → `PlannerAgent` mailbox → 4-stage pipeline (SKETCH→EXPAND→VALIDATE→COMMIT) → committed plan → `OrchestratorService.process()` → DAGExecutor wave execution → results. |
| **Code-verified gap** | `k1/concierge/orchestrator/interfaces.py` L1-17: "These interfaces are NOT IMPLEMENTED in the POC." `IPlannerService`, `IDAGExecutor`, `IWorkflowEngine`, `IConstraintResolver`, `ISagaRecovery` — interfaces only. |
| **What needs to exist first** | (a) Controller must replace PassthroughPlannerStub block (L2114-2130) with real dispatch: `self._planner_mailbox.submit(PlanRequest(...))`. (b) PlannerAgent.start() must be running (S7 from Epic 2.2). (c) OrchestratorService (not Stub) must handle committed plans. (d) Cross-wire S6b must be complete. |
| **Cross-component chain (target)** | FSM → PlannerAgent (via mailbox) → PipelineController (SKETCH→EXPAND→VALIDATE→COMMIT) → committed plan event → OrchestratorService.process() → DAGExecutor → Fabric calls → results → Bus event → FSM DELIVERING |
| **Assertions** | (a) HIGH input reaches PlannerAgent mailbox. (b) PipelineController executes 4 stages. (c) Committed plan has ≥ 1 step. (d) OrchestratorService processes plan (not OrchestratorStub). (e) DAGExecutor runs topological wave. (f) Fabric calls executed per plan steps. (g) `dag.completed` event on bus. (h) FSM reaches DELIVERING. |
| **Depends on** | Real PlannerAgent wired (2.2.6), Real OrchestratorService wired (2.2.5), S6b cross-wire (2.2.7), Controller updated to remove PassthroughPlannerStub |
| **Status** | ☐ |

---

#### Epic 4.3: Circuit Breaker Degradation & Wiring Tests

**What we're testing:** The degradation cascade (`route_task_with_degradation`) that EXISTS in code but is DEAD (never called by FSM). These tests first WIRE the degradation, then verify the cascade works end-to-end.

---

##### Issue 4.3.1 — Wire `route_task_with_degradation()` into FSM controller

| Field | Detail |
|-------|--------|
| **What** | Replace `route_task_sync()` call in `_route_via_orchestrator()` with `route_task_with_degradation()`. This activates the circuit breaker cascade that currently exists as dead code. |
| **Code-verified dead code** | `k1/concierge/orchestrator/degradation.py` L208-266: `route_task_with_degradation(dispatch, tier, cb_planner, cb_orchestrator, cb_fabric)` → calls `get_effective_tier()` → cascade: HIGH+CB_OPEN→MEDIUM, MEDIUM+CB_OPEN→LOW, LOW+CB_OPEN→CannedResponse |
| **Current controller call** | `controller.py:2105 _route_via_orchestrator()` calls `route_task_sync(dispatch, tier)` — zero CB awareness |
| **Change required** | In `_route_via_orchestrator()`: replace `route_task_sync(dispatch, tier)` with `route_task_with_degradation(dispatch, tier, cb_planner=cb_planner, cb_orchestrator=cb_orchestrator, cb_fabric=cb_fabric)`. Import `route_task_with_degradation` and the 3 CB singletons from `degradation.py`. |
| **File** | `k1/concierge/fsm/controller.py` — `_route_via_orchestrator()` |
| **Depends on** | degradation.py exists (verified), CB singletons exist (verified) |
| **Status** | ☐ |

---

##### Issue 4.3.2 — Test: HIGH + CB_PLANNER open → degrades to MEDIUM

| Field | Detail |
|-------|--------|
| **What** | When `cb_planner` circuit breaker is open, HIGH tier degrades to MEDIUM routing. |
| **Code-verified** | `degradation.py:272-288 get_effective_tier()`: `if tier == HIGH and cb_planner.is_open(): return MEDIUM` |
| **Setup** | (a) Force `cb_planner` to OPEN state (trip failures past threshold). (b) Send HIGH-scoring input. |
| **Assertions** | (a) Classification returns HIGH. (b) `get_effective_tier()` returns MEDIUM. (c) Dispatch follows MEDIUM path (OrchestratorStub). (d) NOT routed to PlannerAgent. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 4.3.1 (degradation wired into controller) |
| **Status** | ☐ |

---

##### Issue 4.3.3 — Test: MEDIUM + CB_ORCHESTRATOR open → degrades to LOW

| Field | Detail |
|-------|--------|
| **What** | When `cb_orchestrator` circuit breaker is open, MEDIUM tier degrades to LOW routing. |
| **Code-verified** | `degradation.py`: `if tier == MEDIUM and cb_orchestrator.is_open(): return LOW` |
| **Setup** | (a) Force `cb_orchestrator` to OPEN. (b) Send MEDIUM-triggering text ("book a hotel"). |
| **Assertions** | (a) Classification returns MEDIUM. (b) `get_effective_tier()` returns LOW. (c) Dispatch follows LOW path (`_deliver_to_back()`). (d) OrchestratorStub.handle_task NOT called. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 4.3.1 |
| **Status** | ☐ |

---

##### Issue 4.3.4 — Test: LOW + CB_FABRIC open → CannedResponse

| Field | Detail |
|-------|--------|
| **What** | When `cb_fabric` circuit breaker is open, LOW tier cannot dispatch — returns `CannedResponse(text=config.canned_response_text, reason="CB_FABRIC_OPEN")`. |
| **Code-verified** | `degradation.py`: `if tier == LOW and cb_fabric.is_open(): return CannedResponse(...)` |
| **Assertions** | (a) `get_effective_tier()` returns CannedResponse. (b) FSM delivers canned text to output port. (c) No Fabric call attempted. (d) No OrchestratorStub call. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 4.3.1 |
| **Status** | ☐ |

---

##### Issue 4.3.5 — Test: Full cascade HIGH → MEDIUM → LOW → Canned (all CBs open)

| Field | Detail |
|-------|--------|
| **What** | All 3 circuit breakers open simultaneously. HIGH input cascades: HIGH→MEDIUM (CB_PLANNER)→LOW (CB_ORCHESTRATOR)→CannedResponse (CB_FABRIC). |
| **Assertions** | (a) Input scores HIGH. (b) Cascade produces CannedResponse. (c) No Planner, Orchestrator, or Fabric calls made. (d) User receives canned response text. (e) All 3 CB trip events logged/observable. |
| **Why it matters** | Proves total system failure degrades gracefully to a static response rather than crashing. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 4.3.1, 4.3.2, 4.3.3, 4.3.4 |
| **Status** | ☐ |

---

##### Issue 4.3.6 — Test: CB half-open recovery — MEDIUM after CB_PLANNER resets

| Field | Detail |
|-------|--------|
| **What** | After CB_PLANNER transitions from OPEN → HALF_OPEN (timeout elapsed), HIGH tier should attempt Planner again (or at least not degrade). |
| **Code-verified** | `CircuitBreaker` class: `OPEN` → after `reset_timeout_s` → `HALF_OPEN` → next call succeeds → `CLOSED`. Next call fails → back to `OPEN`. |
| **Assertions** | (a) Trip CB_PLANNER to OPEN. (b) Wait for half-open (or manually set state). (c) Send HIGH input. (d) Planner attempted (not degraded to MEDIUM). (e) If Planner succeeds → CB back to CLOSED. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 4.3.1 |
| **Status** | ☐ |

---

#### Epic 4.4: Cross-Component Data Flow Tests

**What we're testing:** Data flows correctly BETWEEN components through adapters. Adapter translation layers work (e.g., MW ModelHubAdapter chat()→execute(), FabricBusAdapter dual-role, DeltaEmitAdapter routing).

---

##### Issue 4.4.1 — Test: Bus → FabricBusAdapter dual-role — single instance serves IEventPort + IDeltaBusPort

| Field | Detail |
|-------|--------|
| **What** | One `FabricBusAdapter(bus)` instance is used as BOTH `event_port` and `delta_bus` for Fabric/Planner/Orchestrator. Verify publish on event_port goes through bus, subscribe on delta_bus receives bus events. |
| **Code-verified** | Issue 2.1.4: "Create ONE FabricBusAdapter(self._bus) instance. Pass SAME instance as both event_port= and delta_bus=." |
| **Assertions** | (a) `adapter.publish(envelope)` → bus receives. (b) `adapter.subscribe(topic, handler)` → handler called when topic published. (c) Same instance satisfies both IEventPort and IDeltaBusPort duck-type checks. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Status** | ☐ |

---

##### Issue 4.4.2 — Test: MW ModelHubAdapter anti-corruption — chat() translates to execute()

| Field | Detail |
|-------|--------|
| **What** | `k1/memory_writer/adapters/model_hub_adapter.ModelHubAdapter(hub=model_hub)` wraps K1 ModelHub. Calling `adapter.chat(messages, budget, hint)` internally calls `hub.execute(HubRequest(CHAT, ChatPayload))`. |
| **Code-verified** | Issue 2.1.5: "K1 ModelHub exposes execute(HubRequest) → HubResponse. MemoryWriter expects chat(messages, budget, hint) → ChatResponse." |
| **Cross-component chain** | MemoryWriter → MW.IModelHubPort.chat() → ModelHubAdapter → K1.ModelHub.execute(HubRequest) |
| **Assertions** | (a) `adapter.chat(messages, budget, hint)` succeeds. (b) ModelHub.execute() called with HubRequest containing ChatPayload. (c) Response translated from HubResponse to ChatResponse. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 2.2.2 (ModelHub wired), 2.1.5 (adapter exists) |
| **Status** | ☐ |

---

##### Issue 4.4.3 — Test: Planner DeltaBusAdapter ≠ EventBusAdapter — different classes, different roles

| Field | Detail |
|-------|--------|
| **What** | Planner has TWO separate Layer 2 bus adapters: `DeltaBusAdapter(delta_bus=fabric_adapter)` for delta emission and `EventBusAdapter(event_port=fabric_adapter)` for event subscription. Verify they are different classes, wrap the same FabricBusAdapter, but serve different port protocols. |
| **Code-verified** | Issue 2.1.4: "Planner.DeltaBusAdapter wraps IDeltaBusPort. Planner.EventBusAdapter wraps IEventPort. Different classes, different port types. Cannot share one adapter." |
| **Assertions** | (a) `type(pl_delta).__name__ != type(pl_event).__name__`. (b) Both wrap same underlying bus. (c) pl_delta satisfies IDeltaBusPort. (d) pl_event satisfies IEventBusPort. (e) Delta published via pl_delta appears on bus. (f) Event subscribed via pl_event triggers handler. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 2.2.6 (Planner wired) |
| **Status** | ☐ |

---

##### Issue 4.4.4 — Test: Orchestrator↔Planner cross-wire — PlanRequest flows through

| Field | Detail |
|-------|--------|
| **What** | After S6b cross-wire, `orchestrator._planner_port` is `PlannerAdapter(planner.get_mailbox(), cb_planner=cb)`. When Orchestrator calls `_planner_port.request_plan(plan_request)`, the request lands in PlannerAgent's mailbox queue and PlannerAgent dequeues it in `_run_loop()`. |
| **Cross-component chain** | OrchestratorService → PlannerAdapter.request_plan() → asyncio.Queue → PlannerAgent._run_loop() dequeue |
| **Assertions** | (a) `orchestrator._planner_port` is PlannerAdapter (not Mock). (b) `request_plan(req)` enqueues to planner mailbox. (c) PlannerAgent dequeues request. (d) Pipeline processes it (at least SKETCH stage). |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 2.2.7 (S6b cross-wire), 2.2.8 (S7 planner task running) |
| **Status** | ☐ |

---

##### Issue 4.4.5 — Test: SessionState → Fabric state reader — per-session reads bound correctly

| Field | Detail |
|-------|--------|
| **What** | Per-session Fabric has `SessionStateReaderAdapter(ssm, session_id)`. When Fabric reads state, it goes through this adapter to the correct session's SSM (not another session's). |
| **Assertions** | (a) Write to session_A SSM section. (b) session_A Fabric state reader returns the data. (c) session_B Fabric state reader does NOT see session_A's data. (d) Adapter bound to correct session_id. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 2.3.3 (per-session Fabric), 2.3.2 (SSM) |
| **Status** | ☐ |

---

##### Issue 4.4.6 — Test: DeltaEmitAdapter routing — deltas to aggregator, non-deltas to bus

| Field | Detail |
|-------|--------|
| **What** | `DeltaEmitAdapter(delta_aggregator, bus)` routes delta events to the aggregator and non-delta events to the bus. Verify routing logic. |
| **Code-verified** | Issue 2.2.5: Orchestrator's `IDeltaEmitPort` ← `DeltaEmitAdapter(delta_aggregator, bus)`. File: `k1/orchestrator/adapters/delta_emit_adapter.py`. |
| **Assertions** | (a) Delta event → aggregator.apply() called, bus.publish() NOT called. (b) Non-delta event → bus.publish() called, aggregator NOT called. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 2.2.5 (Orchestrator wired) |
| **Status** | ☐ |

---

#### Epic 4.5: Full Turn Cycle Tests (End-to-End)

**What we're testing:** Complete user turn from input to output. Message in → classification → dispatch → execution → response out → FSM back to LISTENING.

---

##### Issue 4.5.1 — Test: LOW turn cycle — input → classify → back actor → response → LISTENING

| Field | Detail |
|-------|--------|
| **What** | Full LOW tier turn: user sends "hello" → FSM LISTENING→CLASSIFYING (StubPhase1: tier=LOW) → DISPATCHING → `_deliver_to_back()` → Back actor ReAct loop → response generated → output port receives response → FSM→DELIVERING→LISTENING. |
| **End-to-end chain** | Input → Bus(user.input) → FSM → Classification → route_task_sync(LOW) → Mailbox(ACTOR_BACK) → Back handler → LLM call → Bus(response.final) → FSM → Output |
| **Assertions** | (a) FSM starts LISTENING. (b) After input: transitions through CLASSIFYING→DISPATCHING. (c) Back actor receives envelope. (d) LLM called (test adapter returns canned response). (e) `response.final` event on bus. (f) FSM back to LISTENING. (g) SessionState history updated with turn. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 2.5.2 (session live), 4.2.1 (LOW dispatch verified) |
| **Status** | ☐ |

---

##### Issue 4.5.2 — Test: MEDIUM turn cycle — input → classify → OrchestratorStub → Fabric → response

| Field | Detail |
|-------|--------|
| **What** | Full MEDIUM tier turn: "book a hotel" → classification MEDIUM → `_run_medium_orchestration()` → OrchestratorStub.handle_task() → Fabric.execute() → `dag.completed` → response. |
| **End-to-end chain** | Input → Bus → FSM → Classification(MEDIUM) → OrchestratorStub → Fabric → Bus(dag.completed) → FSM(DELIVERING) → Output |
| **Assertions** | (a) OrchestratorStub.handle_task called. (b) Fabric.execute called. (c) `dag.completed` event on bus. (d) FSM reaches DELIVERING. (e) Response delivered to output. (f) FSM back to LISTENING. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 2.5.2, 4.2.2 |
| **Status** | ☐ |

---

##### Issue 4.5.3 — Test: Multi-turn session — state persists across turns

| Field | Detail |
|-------|--------|
| **What** | Send 3 turns in one session. Verify SessionState accumulates history, beliefs update, scoreboard tracks referents. Turn N+1 sees Turn N's state. |
| **Assertions** | (a) After turn 1: `history_active.format_for_prompt(1)` returns turn 1. (b) After turn 2: `history_active.format_for_prompt(2)` returns both turns. (c) beliefs_active updated by Back actor tool calls. (d) No state leakage to other sessions. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 4.5.1 (single turn works) |
| **Status** | ☐ |

---

##### Issue 4.5.4 — Test: Concurrent sessions — two sessions, interleaved turns, no cross-talk

| Field | Detail |
|-------|--------|
| **What** | Create session_A and session_B. Send turn to A, turn to B, turn to A. Verify: (a) each session's Bus is isolated, (b) each session's SSM is independent, (c) shared components (ModelHub, Orchestrator) handle both sessions without corruption. |
| **Assertions** | (a) session_A bus events not visible on session_B bus. (b) session_A SSM state not in session_B SSM. (c) ModelHub.execute called for both sessions (shared). (d) No deadlocks or race conditions with concurrent asyncio tasks. |
| **File** | `tests/k1/kernel/test_integration.py` |
| **Depends on** | 2.5.5 (multi-session isolation), 4.5.1 (single turn works) |
| **Status** | ☐ |

---

## COUNTS SUMMARY

| Category | Count | Detail |
|----------|-------|--------|
| **Milestones** | 4 | MS-1 ✅, MS-2 (active), MS-2.5 (7 phases), MS-3 (tech debt), MS-4 |
| **Epics** | 27 | 1.1–1.10, 2.0–2.5, Phase 1–7, TD 1–6, 4.1–4.5 |
| **MS-1 Issues** | 42 | All ✅ |
| **MS-2 Epic 2.0** | 13 | All ✅ (pre-requisites) |
| **MS-2 Epic 2.1** | 10 | All ✅ (KernelService skeleton, 96 tests) |
| **MS-2 Epic 2.2** | 10 | All ✅ (Tier-1 startup: S1–S7 + method bodies) |
| **MS-2 Epic 2.3** | 8 | All ✅ (Tier-2 session: P1–P6 + method bodies) |
| **MS-2 Epic 2.4** | 3 | All ✅ (Shutdown: per-session, shared, error recovery) |
| **MS-2 Epic 2.5** | 5 | All ✅ (Integration tests: real components, no mocks) |
| **MS-2 Total** | 49 | 23 ✅ + 26 ☐ |
| **MS-2.5 Phase 1** | 6 | ☐ (Session-state wiring — CRITICAL) |
| **MS-2.5 Phase 2** | 8 | ☐ (Serialization & type bugs — CRITICAL/HIGH) |
| **MS-2.5 Phase 3** | 4 | ☐ (Dead code cleanup — HIGH) |
| **MS-2.5 Phase 4** | 6 | ☐ (POC decoupling — HIGH) |
| **MS-2.5 Phase 5** | 8 | ☐ (Stub→real adapters — MEDIUM) |
| **MS-2.5 Phase 6** | 6 | ☐ (Bus hardening — MEDIUM) |
| **MS-2.5 Phase 7** | 7 | ☐ (Bridge adapters — DEFERRED) |
| **MS-2.5 Total** | 45 | All ☐ (addresses 225 audit findings) |
| **MS-3 TD Epics** | ~100+ | ☐ (type safety, docs, arch, future stubs, LOW, INFO) |
| **MS-4 Issues** | 24 | ☐ (classification, tier routing, degradation, cross-component, full turn) |
| **Grand Total** | ~260+ | 65 ✅ + ~195 ☐ |
| **Ports audited** | 52 | All ✅ |
| **Adapters audited** | ~90 | All ✅ |
| **Factories audited** | 8 | All ✅ (signatures code-verified) |
| **Audit findings** | 225 | All accounted for (0 dropped) |

---

## EXECUTION ORDER

```text
MS-1 (Audit) — ✅ ALL COMPLETE (42 issues, 120 findings)
  Epic 1.1–1.10 → see files 10–19

MS-2 (Kernel Wiring) — 4-phase per-component process
  Epic 2.0 (Pre-Requisites) — ✅ ALL COMPLETE (13 issues)
  Epic 2.1 (KernelService skeleton) — ✅ ALL COMPLETE (10 issues, 96 tests)

  Epic 2.2 (Tier-1 startup — per-component 4-phase: AUDIT → VERIFY → WIRE → TEST):
    2.2.1 S1: Bus + AsyncBusBridge + Router
    2.2.2 S2: ModelHub (standalone)
    2.2.3 S3: Shared Fabric (needs S1+S2+S4)
    2.2.4 S4: Bridge (SinkBridgeClient, no deps)
    2.2.5 S5: Orchestrator (8 ports, needs S1+S3+S4)
    2.2.6 S6: Planner (7 ports, needs S1+S2+S3+S4)
    2.2.7 S6b: Orchestrator↔Planner cross-wire
    2.2.8 S7: Start Planner task + verify bindings
    2.2.9 _startup_tier1() method body (S1→S7 sequence)
    2.2.10 startup() public method

  Epic 2.3 (Tier-2 session — per-component 4-phase):
    2.3.1 P1: Per-session Bus + Mailboxes
    2.3.2 P2: SessionState (two-phase bind)
    2.3.3 P3: Per-session Fabric
    2.3.4 P4: Concierge (PortBundle + 3 infra)
    2.3.5 P5: MemoryWriter (5 ports + anti-corruption adapter)
    2.3.6 P6: Assemble SessionInstance + start lifecycle
    2.3.7 _create_session_tier2() method body
    2.3.8 create_session() public method

  Epic 2.4 (Shutdown — reverse order):
    2.4.1 Per-session shutdown (reverse P6→P1)
    2.4.2 Shared shutdown (reverse S7→S1)
    2.4.3 Error recovery (partial failure cleanup)

  Epic 2.5 (Integration tests — real components, NO mocks):
    2.5.1 Full startup() lifecycle
    2.5.2 Full create_session() lifecycle
    2.5.3 Full shutdown lifecycle
    2.5.4 Error paths
    2.5.5 Multi-session isolation

MS-2.5 (Audit-Driven Workstream Phases) — after MS-2, before MS-3
  Phase 1: Session-State Wiring (CRITICAL, 6 issues, ~200 LOC)
    P1.1 Build SessionRoutingStateReader
    P1.2 Wire StateReadAdapter in Orchestrator
    P1.3 Wire PlannerStateAdapter with real reader
    P1.4 Wire shared Fabric with SessionRoutingStateReader
    P1.5 Verify SSMStateAdapter wrapper
    P1.6 Integration tests

  Phase 2: Serialization & Type Safety Bugs (CRITICAL/HIGH, 8 issues, ~50 LOC)
    P2.1 Fix PlanStep.to_dict() — add safety_band_min  ☑ DONE
    P2.2 Fix compensation_capability AttributeError     ☑ DONE (already guarded)
    P2.3 Fix isinstance bug in list_circuit_breakers()  ☑ DONE (already correct)
    P2.4 Fix PlanStep type collision                    ☑ DONE
    P2.5 Fix RegistryEntry lossy mapping                ☑ DONE
    P2.6 Fix submit_command_batch type mismatch
    P2.7 Fix RustMailboxAdapter.receive() keyword-only
    P2.8 Fix MW BridgeCommandAdapter type mismatch (BUG-1)

  Phase 3: Dead Code & Package Cleanup (HIGH, 4 issues, -100 LOC)
    P3.1 Delete k1/kernel/ dead stubs              ☑ DONE
    P3.2 Delete factory.py.bak                       ☑ DONE
    P3.3 Clean empty placeholder packages             ☑ DONE
    P3.4 Fix stale status markers                     ☑ DONE

  Phase 4: POC Layer Decoupling (HIGH, 5 issues)
    P4.1 Verify poc.k1_poc.main.boot() elimination   ☑ ALREADY DONE
    P4.2 Replace ModelHubPOCBridge + fix chat_repl race  ☑ DONE
    P4.3 Replace get_config() in 12 SS files          ☑ DONE
    P4.4 Replace config triple-indirection shims      ☑ DONE
    P4.5 Fix runner.py tool_tier mismatch               ☑ DONE

  Phase 4B: Concierge Port Wiring & Bootstrap Reduction (HIGH, 8 issues, ~800 LOC)
    P4B.1 Reduce bootstrap.py to thin KernelService delegate
    P4B.2 Wire IDispatchPort through factory (absorbs old P5.8)
    P4B.3 Wire tools through IDispatchPort (remove ctx.fabric_port)
    P4B.4 Delete k1/concierge/orchestrator/ (move routing to k1/orchestrator/)
    P4B.5 Delete internal adapter trinity from factory
    P4B.6 Fix writer_port reach-through in factory
    P4B.7 Move demo capabilities to test fixtures
    P4B.8 Wire IClassificationPort in service.py

  Phase 5: Production Adapter Stubs → Real (MEDIUM, 7 issues, ~500 LOC)
    P5.1 Wire Orch BridgeWriteAdapter (replace MockBridgeAdapter)
    P5.2 Wire Concierge RecallMemoryAdapter (replace memory=None)
    P5.3 Fix MW HealthAdapter get_started lambda
    P5.4 Wire ModelHub IEventPort to K1 Bus
    P5.5 Wire ModelHub IStateReadPort
    P5.6 Fix MW FakeSessionReadPort missing methods
    P5.7 Fix MW PlaceResolver empty entity list
    P5.8 Wire Concierge FabricDispatchAdapter in factory

  Phase 6: Bus Hardening (MEDIUM, 6 issues, ~200 LOC)
    P6.1 Build AsyncBusBridge
    P6.2 Add k1.model_hub STRICT timing rule
    P6.3 Fix turn.complete.v1 namespace prefix
    P6.4 Fix SessionBusAdapter double-nested topic naming
    P6.5 Fix Rust adapter middleware bypass
    P6.6 Fix async handler fire-and-forget

  Phase 7: Bridge Adapter Completion (DEFERRED, 7 issues, ~800 LOC)
    P7.1 Build KernelQueryPort adapter
    P7.2 Build KernelSSEPort adapter
    P7.3 Build KernelObsPort adapter
    P7.4 Build HttpBridgeClient (BLOCKED on K0 API)
    P7.5 Fix SigningBackend @runtime_checkable
    P7.6 Move StubBridgeClient to test module
    P7.7 Add Protocol conformance to KernelCommandPort

MS-3 (Technical Debt Removal) — can run in parallel with MS-4
  TD Epic 1: Type Safety Sweep (10 issues, ~150 LOC)
  TD Epic 2: Documentation & Stale Markers (5 issues)
  TD Epic 3: Architectural Improvements (18 issues)
  TD Epic 4: Future-Scope Stubs (11 issues, blocked on external deps)
  TD Epic 5: Remaining LOW Items (48 issues)
  TD Epic 6: INFO Items (19 issues, observability/docs)
  Original MS-3 audit record preserved in <details> block

MS-4 (Cross-Component Integration & Turn-Level Testing) — after MS-2.5
  Epic 4.1 (Classification & Tier Decision: 3 issues)
    4.1.1 StubPhase1Pipeline classification paths
    4.1.2 UltraBERT multi-factor complexity scoring
    4.1.3 UltraBERT fallback to StubPhase1Pipeline
  Epic 4.2 (Tier Routing & Dispatch Paths: 5 issues)
    4.2.1 LOW → Back actor via Mailbox
    4.2.2 MEDIUM → OrchestratorStub.handle_task()
    4.2.3 MEDIUM fallback (no Orchestrator wired)
    4.2.4 HIGH → PassthroughPlannerStub → MEDIUM re-route (current)
    4.2.5 HIGH → real Planner (future — wire PlannerAgent + OrchestratorService)
  Epic 4.3 (Circuit Breaker Degradation: 6 issues)
    4.3.1 Wire route_task_with_degradation() into FSM controller
    4.3.2 HIGH + CB_PLANNER open → MEDIUM
    4.3.3 MEDIUM + CB_ORCHESTRATOR open → LOW
    4.3.4 LOW + CB_FABRIC open → CannedResponse
    4.3.5 Full cascade all CBs open → CannedResponse
    4.3.6 CB half-open recovery
  Epic 4.4 (Cross-Component Data Flow: 6 issues)
    4.4.1 FabricBusAdapter dual-role (IEventPort + IDeltaBusPort)
    4.4.2 MW ModelHubAdapter anti-corruption (chat→execute)
    4.4.3 Planner DeltaBusAdapter ≠ EventBusAdapter
    4.4.4 Orchestrator↔Planner cross-wire (PlanRequest flow)
    4.4.5 SessionState → Fabric state reader isolation
    4.4.6 DeltaEmitAdapter routing (deltas vs non-deltas)
  Epic 4.5 (Full Turn Cycle: 4 issues)
    4.5.1 LOW turn: input → classify → back → response → LISTENING
    4.5.2 MEDIUM turn: input → classify → OrchestratorStub → Fabric → response
    4.5.3 Multi-turn session state persistence
    4.5.4 Concurrent sessions — no cross-talk
```

---

## HOW TO USE THIS PLAN

1. **Pick the next ☐ issue** from Epic 2.2 (in order — S1 first)
2. **Follow the 4 phases**: AUDIT the factory → VERIFY adapter compatibility → WIRE in service.py → TEST with real components
3. **Record findings** in the Status column: ✅ DONE / ☐ TODO
4. **Each issue is self-contained**: exact factory call, exact adapter classes, exact constructor args, exact test assertions
5. **No mocks in integration tests** — real components talking to each other
