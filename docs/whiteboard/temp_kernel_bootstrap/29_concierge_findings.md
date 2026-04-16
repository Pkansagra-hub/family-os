# 29 — Concierge Architecture Findings

> Pre-Phase-5 structural audit. Compiled from 3 parallel sub-agent analyses + audit
> cross-reference with `09_wiring_plan.md`.

---

## 1. Bootstrap / Service / Factory — Three Boot Paths

### 1.1 Current State

| File | Lines | Role | Used By |
|------|-------|------|---------|
| `k1/kernel/bootstrap.py` | ~960 | Legacy flat boot — creates everything inline | `chat_repl.py`, `runner.py` |
| `k1/kernel/service.py` | ~1380 | Production hexagonal boot — Tier 1 shared + Tier 2 per-session | (not yet called from any entry point) |
| `k1/concierge/factory.py` | ~880 | Concierge composition root — 16-step wiring, receives ports | Called by `service.py` at P4 |

### 1.2 Boot Flow Comparison

**Legacy path** (`chat_repl.py` / `runner.py`):

```
chat_repl → bootstrap.start_kernel(cfg)
  → BusFactory, _create_model(), _create_session_state(), _create_fabric()
  → Inline: FSM, Phase1, Ledger, ToolContext×2, Dispatchers, HITL, Weave, Delta, DeadLetter, OrchestratorStub
  → KernelRuntime assembled
  → _mailbox_consumer() as asyncio.Task
```

**Production path** (`KernelService`):

```
KernelService.startup() → _startup_tier1()
  S1: Bus + AsyncBusBridge + MailboxRouter
  S2: ModelHubFactory.create_with_ports(credential, event, state_read, metrics, config)
  S4: Bridge (SinkBridgeAdapter or OfflineBridgeAdapter)
  S3: FabricFactory.create_shared(event, bridge, model_gw, prompt, delta_bus, state_reader)
  S5: OrchestratorFactory.create_production(...)
  S6: PlannerFactory.create_production(...)
  S6b: Cross-wire Orch↔Planner
  S7: Start planner task

KernelService.create_session(session_id) → _create_session_tier2()
  P1: Per-session Bus + Router + Mailboxes
  P2: SessionStateFactory.create_with_ports(...)
  P3: FabricFactory.create_with_ports(per-session adapters)
  P4: ConciergeFactory.create_with_ports(bus, router, PortBundle, config, fabric, orch)
  P5: MemoryWriterFactory.create(...)
  P6: concierge.start() + memory_writer.start()
```

### 1.3 Overlap Analysis

| Concern | bootstrap.py | factory.py | service.py | Verdict |
|---------|-------------|-----------|------------|---------|
| FSM creation | ✅ inline | ✅ Step 1 | delegates to factory | **DUPLICATE** |
| HITL wiring | ✅ inline lambdas | ✅ extracted helpers | — | **DUPLICATE** |
| Delta aggregator/applicator | ✅ inline | ✅ `_build_delta_applicator` | — | **DUPLICATE** |
| Weave/Activity | ✅ inline | ✅ Step 12 | — | **DUPLICATE** |
| DeadLetter | ✅ inline | ✅ Step 13 | — | **DUPLICATE** |
| OrchestratorStub | ✅ inline | ✅ Step 14 | — | **DUPLICATE** |
| ToolContext | ✅ inline | ✅ Steps 7-8 | — | **DUPLICATE** |
| Experience | ✅ inline | ✅ Step 9 | — | **DUPLICATE** |
| Model creation | ✅ `_create_model_hub()` | — | ✅ `ModelHubFactory` | **OVERLAP** (different paths) |
| Fabric creation | ✅ `_create_fabric()` POC mock | — | ✅ `FabricFactory` production | **OVERLAP** (POC vs real) |
| SessionState | ✅ `_create_session_state()` | — | ✅ `SessionStateFactory` | **OVERLAP** |
| Bus/Router | ✅ `BusFactory` | receives them | ✅ `BusFactory` | Both correct |

**Conclusion:** `bootstrap.py` is a legacy flat boot that duplicates almost every wiring step that `factory.py._construct_concierge()` handles cleanly. `service.py` is the correct production architecture.

### 1.4 POC/Shim Imports Still Present

| File | POC Imports | Status |
|------|------------|--------|
| `bootstrap.py` | `POCMockBridgeAdapter`, `create_demo_registry`, `convert_all_poc_capabilities`, `TestModelHubBridge`, `OrchestratorStub` | ⚠️ Active POC dependencies |
| `service.py` | None | ✅ Clean |
| `factory.py` | `OrchestratorStub` only | ⚠️ Stub dependency |
| `chat_repl.py` | None (imports from bootstrap) | ✅ Clean |

### 1.5 Recommendation

**`bootstrap.py` should be reduced to a thin shim** that calls `KernelService` for `chat_repl.py` and `runner.py`. The inline concierge wiring (~600 lines) is dead code relative to the production `factory.py` path. Keep only:

- `KernelRuntime` dataclass (or move to service)
- `start_kernel()` → delegates to `KernelService.startup()` + `create_session()`
- `stop_kernel()` → delegates to `KernelService.shutdown()`
- `_mailbox_consumer()` (kernel infrastructure)

---

## 2. Misplaced Subdirectories in `k1/concierge/`

### 2.1 `k1/concierge/orchestrator/` — **SHOULD NOT BE HERE**

| Metric | Value |
|--------|-------|
| Files | 7 (types, ports, interfaces, routing, stub, degradation, **init**) |
| What it does | MEDIUM-tier task orchestration: `OrchestratorStub`, `route_task()`, `CircuitBreaker`, 9 port protocols, 6 ABC interfaces |
| Already exists | `k1/orchestrator/` (production orchestrator with its own types, adapters, factories) |
| Used by | `k1/concierge/factory.py` (Step 14), `k1/kernel/bootstrap.py`, tests |

**Problem:** This is a **parallel reimplementation** inside concierge. The types.py header explicitly says types are "intentionally SEPARATE from k1.orchestrator.types." This creates a dual-type system where concierge has its own `TaskEnvelope`, `Budget`, `AggregatedResult` that don't match production types.

**Recommendation:** Merge into `k1/orchestrator/`. Concierge should hold only a thin adapter/port reference, not the full orchestrator implementation.

### 2.2 `k1/concierge/llm/` — **SIGNIFICANT DUPLICATION with model_hub**

| Metric | Value |
|--------|-------|
| Files | 10 (types, ports, gemini_adapter, model_hub_adapter, model_hub_bridge, model_selection, test_adapter, test_bridge, validator) |
| What it does | Parallel LLM type system: `IConciergeModelPort`, `ConciergeModelRequest/Response`, `ToolCallResult`, `ModelMessage`, `ToolSchema` |
| Duplicates | `k1/model_hub/` which has `IModelHubPort`, `HubRequest/Response`, model selection, typed results |
| Bridge adapters | 2 adapters (`ModelHubAdapter`, `ModelHubPOCBridge`) exist solely to translate between the two type systems |

**Problem:** Dual type system creates needless translation layers. Every LLM call goes through: `ConciergeModelRequest` → adapter → `HubRequest` → model_hub → `HubResponse` → adapter → `ConciergeModelResponse`.

**What should stay:** `ToolSchema` (concierge-specific), `LLMOutputValidator` (concierge-specific), test adapters.
**What should go:** `IConciergeModelPort` → use `IModelHubPort`; `ConciergeModelRequest/Response` → use `HubRequest/Response`; `GeminiConciergeAdapter` → already exists as model_hub plugin; `model_selection.py` → merge with model_hub.

### 2.3 `k1/concierge/fabric/` — **BRIDGE LAYER (temporary)**

| Metric | Value |
|--------|-------|
| Files | 8 (ports, capability_registry, contract_converter, poc_bridge_adapter, demo_capabilities, family_capabilities, web_capabilities) |
| What it does | POC Fabric: 40 mock capabilities + in-memory registry + bridge adapter to K1 Fabric |
| Standalone exists | `k1/fabric/` (production fabric with FabricFactory, ports, adapters) |

**Problem:** 40 capability definitions + mock handlers are **test/demo fixtures** living in production code. `POCMockBridgeAdapter` is the only remaining POC bridge adapter in the codebase.

**What should stay:** `IFabricPort` (concierge's port definition — proper hexagonal architecture).
**What should go:** `CapabilityRegistry` + all capabilities → test fixtures or `k1/fabric/`; `POCMockBridgeAdapter` + `contract_converter` → `k1/fabric/` or delete when real Fabric is wired.

### 2.4 `k1/concierge/tools/` — **BELONGS HERE**

| Metric | Value |
|--------|-------|
| Files | 8 (dispatcher, implementations, parallelism, result_protocol, schemas_front, schemas_back) |
| What it does | 10 Front + 7 Back tool schemas, 7-step dispatch pipeline, parallel safety, tool implementations |

**Assessment:** Tools are the concierge's LLM-facing interface. Schemas define what actors can call, dispatcher enforces budgets/allowlists, implementations write to SessionState. This is squarely concierge domain. Only concern: tight coupling to `k1.concierge.llm.types.ToolSchema`.

### 2.5 Summary Table

| Subdirectory | Belongs in Concierge? | Target Location | Severity |
|-------------|----------------------|-----------------|----------|
| `orchestrator/` | **NO** | Merge with `k1/orchestrator/` | HIGH |
| `llm/` | **PARTIALLY** | Eliminate dual types; use `k1/model_hub` directly | HIGH |
| `fabric/` | **TEMPORARILY** | Mock data → test fixtures; bridge → `k1/fabric/` | MEDIUM |
| `tools/` | **YES** | Keep; extract `ToolSchema` to shared contracts | LOW |

---

## 3. Audit Cross-Reference (from `_scan_temp/`)

Key findings from the 12 concierge audit scan files:

| Finding | Impact |
|---------|--------|
| HIGH tier orchestrator path is **interface-only** (NOT WIRED) | `route_task(HIGH)` creates correct budget but K1 Orchestrator is never called |
| 3 of 6 experience components are stubs | `NarrativeWeaver`, `AnticipatoryResponder`, `ProactiveAgent` — no-ops |
| `EpisodicCompressor` is a stub with no tests | Cross-cutting concern (MW also needs it) |
| Proactive scheduler is a stub | Platform concern, not concierge-specific |
| 5 null adapters exist for temporal coupling | Bootstrap ordering matters — shared components start before per-session state |
| `_FabricGatewayAdapter` type translation | Converts between POC `CapabilityRequest(name=...)` and K1 `CapabilityRequest(capability_name=...)` — will break when real Orch is wired |

---

## 4. Comparison with 09_wiring_plan.md

### What the plan ALREADY covers

| Plan Issue | Relates to Finding | Status |
|-----------|-------------------|--------|
| P5.1 — Wire Orch BridgeWriteAdapter | Fixes one mock adapter in service.py | ☐ |
| P5.2 — Wire RecallMemoryAdapter | Fixes memory=None in concierge | ☐ |
| P5.8 — Wire FabricDispatchAdapter | Partially addresses concierge/orchestrator boundary | ☐ |
| P4.2 — Replace ModelHubPOCBridge ✅ | Eliminated one bridge in concierge/llm | ☑ DONE |
| P4.4 — Config triple-indirection ✅ | Fixed config shim chain | ☑ DONE |

### What the plan does NOT cover (new findings)

| # | Finding | Severity | Suggested Phase |
|---|---------|----------|-----------------|
| **N1** | `bootstrap.py` is a legacy flat boot duplicating `factory.py` + `service.py` — `chat_repl.py` and `runner.py` should migrate to `KernelService` | HIGH | New Phase (pre-P5 or post-P7) |
| **N2** | `k1/concierge/orchestrator/` is a parallel reimplementation of `k1/orchestrator/` with incompatible types | HIGH | New Phase (MS-5 or dedicated) |
| **N3** | `k1/concierge/llm/` dual type system with `k1/model_hub/` creating needless translation layers | HIGH | New Phase (MS-5 or dedicated) |
| **N4** | `k1/concierge/fabric/` holds 40 mock capabilities + `POCMockBridgeAdapter` in production code | MEDIUM | Partially addressed by P5.8; rest is MS-5 |
| **N5** | `_FabricGatewayAdapter` type translation between POC and K1 `CapabilityRequest` will break when real Orch is wired | MEDIUM | Should be fixed alongside P5.8 |
| **N6** | HIGH tier orchestrator path is interface-only (not wired) | INFO | Documented limitation; needs real Orch+Planner |
| **N7** | 3 experience stubs + 1 compression stub + 1 scheduler stub live in concierge | LOW | MS-5 cleanup or dedicated extraction |

### Recommendation for ordering

1. **N1 (bootstrap reduction)** should happen BEFORE Phase 5 — otherwise P5 fixes go into `service.py` while `bootstrap.py` remains a divergent copy
2. **N2, N3** are structural and can be done as a dedicated "concierge extraction" phase after P7, or as MS-5
3. **N4, N5** should be addressed alongside P5.8 (FabricDispatchAdapter wiring)
4. **N6, N7** are documented limitations, not blockers

---

## 5. Concierge Scope Summary

### Intended Scope (what concierge SHOULD own)

- User-facing conversation management (Front/Back Actors)
- Intent classification + FSM routing (11 states, 33 transitions)
- Multi-turn context tracking (SessionState writes)
- HITL coordination
- Task dispatch TO external systems (Fabric, Orchestrator) via ports
- Prompt assembly + LLM interaction via ports
- Response delivery (weave, present, stream)
- Protocols (cancel, suspend, trust, lease, OPP)
- Observability/metrics for conversation quality

### What it currently ALSO owns (shouldn't)

- Full MEDIUM-tier orchestrator implementation (`orchestrator/`)
- Parallel LLM type system + adapters (`llm/`)
- 40 mock capabilities + registry (`fabric/`)
- 3 experience stubs, 1 compression stub, 1 scheduler stub

### Size impact

- Current: ~35,000 lines across 181 source files
- After extraction: ~32,000 lines (orchestrator ~800, LLM types ~500, fabric mocks ~1,500)
