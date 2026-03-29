# POC → K1 Production Migration Plan

**Branch**: `POC_Migration` (from `develop`)  
**Strategy**: Port-First in POC, Copy Once  
**Principle**: Add ports at POC boundaries → verify tests green → single copy to `k1/concierge/` → swap adapters  
**Created**: 2026-03-29  
**Status**: SKELETON — Milestones defined, Epics & Issues TBD  

---

## Migration Philosophy

> The POC is the organ. K1 is the skeleton. We transplant organs into the skeleton, not rebuild organs from bone.

- **Do NOT rewrite** working POC internals (FSM, ReAct, Prompt Builder, OPP, HITL, Weave)
- **Do add** port interfaces at the 4 boundary points where POC makes direct calls
- **Do write** two adapters per port: POC adapter (keeps tests green) + K1 adapter (targets production layer)
- **Do copy** the entire POC into `k1/concierge/` in one go after all ports are wired
- **Do verify** each milestone with its own test gate before proceeding

---

## Milestone Overview

| # | Milestone | Theme | Gate |
|---|-----------|-------|------|
| M0 | Pre-Flight | Baseline audit, test inventory, dependency map | All POC tests pass on `POC_Migration` branch |
| M1 | Port: IModelPort | Extract LLM boundary | Tests pass with POC model adapter |
| M2 | Port: ICapabilityPort | Extract Fabric/tool boundary | Tests pass with POC capability adapter |
| M3 | Port: IBusPort | Normalize bus interface | Tests pass with POC bus adapter |
| M4 | Port: IStoragePort Audit | Verify SS ports already clean | SS port contract tests pass |
| M5 | The Big Copy | POC → `k1/concierge/` | All imports resolve, all tests pass from new location |
| M6 | K1 Fabric Wiring | Swap `ICapabilityPort` → real Fabric | Capabilities resolve through `k1/fabric/` |
| M7 | K1 Model Hub Wiring | Swap `IModelPort` → Model Hub | LLM calls route through `k1/model_hub/` |
| M8 | K1 Orchestrator Wiring | MEDIUM tier through Orchestrator | MEDIUM tasks route through `k1/orchestrator/` |
| M9 | K1 Planner Wiring | HIGH tier through Planner | HIGH tasks route through `k1/planner/` (future) |
| M10 | Integration & Hardening | E2E tests, perf benchmarks, cleanup | Full regression green, latency within budget |

---

## M0 — Pre-Flight

> Establish baseline: what do we have, what passes, what depends on what.

### Epics
<!-- TBD: Fill in epics and issues -->

### Issues
<!-- TBD -->

---

## M1 — Port: IModelPort

> Extract LLM adapter boundary. All callers use `IModelPort` protocol instead of direct `GeminiConciergeAdapter`.

**Boundary**: `poc/k1_poc/llm/adapter.py` → Gemini SDK  
**Callers**: `react/loop.py`, `fsm/controller.py`  
**Port location**: `poc/k1_poc/llm/ports/model_port.py`  
**POC adapter**: `poc/k1_poc/llm/adapters/gemini_direct_adapter.py` (wraps existing code)  
**K1 adapter** (M7): `k1/concierge/llm/adapters/model_hub_adapter.py`  

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M2 — Port: ICapabilityPort

> Extract capability resolution boundary. Back's `invoke_capability()` calls port instead of flat dict lookup.

**Boundary**: `poc/k1_poc/fabric/family_capabilities.py` → `CAPABILITY_HANDLERS` dict  
**Callers**: `tools/implementations.py` (`execute_invoke_capability`), `tools/dispatcher.py`  
**Port location**: `poc/k1_poc/fabric/ports/capability_port.py`  
**POC adapter**: `poc/k1_poc/fabric/adapters/dict_capability_adapter.py` (wraps existing dict)  
**K1 adapter** (M6): `k1/concierge/fabric/adapters/fabric_gateway_adapter.py`  

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M3 — Port: IBusPort

> Normalize bus instantiation to match `k1/bus/ports/bus.py` interface.

**Boundary**: `poc/k1_poc/bus/` → direct `LocalBus` + `TimingChain` instantiation  
**Callers**: `kernel/bootstrap.py`, `fsm/controller.py`, `actors/*.py`  
**Port location**: `poc/k1_poc/bus/ports/bus_port.py`  
**Status**: POC bus IS the k1 bus implementation — mostly an import-path alignment  

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M4 — Port: IStoragePort Audit

> Session State already has ports/adapters in POC. Verify contracts are clean and aligned with K1 expectations.

**Existing ports**: `poc/k1_poc/sessionstate/ports/`  
**Existing adapters**: `poc/k1_poc/sessionstate/adapters/`  
**Work**: Audit interface alignment, add any missing contract tests  

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M5 — The Big Copy

> Single mechanical move: `poc/k1_poc/` → `k1/concierge/`. Fix imports. Verify all tests pass from new location.

**What copies** (the organs):
- `fsm/` — 18 files, FSM controller + guard matrix + states
- `react/` — ReAct loop engine + history
- `prompt/` — DynamicPromptBuilder + 10 modes
- `protocols/` — OPP (8 primitives), HITL, Weave, Suspension (18 files)
- `sessionstate/` — manager + tiers + sections + ports + adapters
- `actors/` — Front + Back handlers
- `events/` — event type definitions
- `delta/` — delta applicator + aggregation
- `experience/` — 6 experience layer stubs
- `identity/` — persona engine
- `compression/` — episodic compression
- `ledger/` — idempotency ledger
- `obs/` — observability
- `task/` — task model
- `orchestrator/` — POC simple orchestrator (becomes LOW-tier path)
- `llm/` — model port + POC adapter
- `bus/` — bus port + POC adapter (or direct k1/bus/ import)
- `fabric/` — capability port + POC adapter
- `tools/` — dispatcher + schemas + implementations
- `scheduler/` — proactive scheduler
- `config/` — YAML configs (may merge with k1/config/)

**What stays behind** (not production):
- `demo/` — test harness
- `testing/` — test utilities
- `main.py` — POC entrypoint
- `concierge_poc_architecture.mmd` — moves to `k1/concierge/docs/` or `architecture_diagrams/`

**What moves to tests**:
- All POC test files → `tests/k1/concierge/`

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M6 — K1 Fabric Wiring

> Swap `ICapabilityPort` POC adapter → real `k1/fabric/` adapter. Capabilities resolve through Fabric provider resolution.

**Work**:
- Register POC capabilities as Fabric providers
- Implement `FabricGatewayAdapter` behind `ICapabilityPort`
- `discover_capabilities()` routes through Fabric retrieval
- `invoke_capability()` routes through Fabric execution engine
- Verify all 40 capabilities resolve correctly

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M7 — K1 Model Hub Wiring

> Swap `IModelPort` POC adapter → `k1/model_hub/` adapter. LLM calls route through Model Hub with proper model selection, token budgets, and fallback.

**Work**:
- Implement `ModelHubAdapter` behind `IModelPort`
- Model selection table: Front/Back × streaming/non-streaming
- Token budget enforcement at Model Hub level
- Fallback chains (pro → flash → canned)

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M8 — K1 Orchestrator Wiring

> MEDIUM tier tasks route through `k1/orchestrator/` instead of direct Front→Back dispatch.

**Work**:
- FSM DISPATCHING emits `TaskEnvelope` to Orchestrator for MEDIUM tier
- Orchestrator resolves capabilities through Fabric (via its own `FabricGatewayPort`)
- Results flow back through `k1.orchestration.dag.completed.v1`
- LOW tier remains direct Front→Back (unchanged)
- Verify MEDIUM tier E2E: user input → orchestrator → fabric → result → delivery

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M9 — K1 Planner Wiring (Future)

> HIGH tier tasks route through `k1/planner/` 4-stage pipeline before Orchestrator execution.

**Work**:
- Planner 4-stage pipeline: Sketch → Expand → Validate → Commit
- Planner discovery tools: `discover_capabilities()`, `recall_for_planning()`, `query_planning_context()`
- CommittedPlan → Orchestrator → Fabric DAG execution
- Verify HIGH tier E2E: complex multi-step task → plan → execute → deliver

**Note**: This milestone is future. Defer until M8 is stable.

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M10 — Integration & Hardening

> Full regression, performance benchmarks, cleanup, documentation.

**Work**:
- E2E test suite: 3-turn conversation flows (LOW, MEDIUM, HIGH)
- Latency benchmarks: LOW <2s, MEDIUM <10s, HIGH <60s
- Token budget verification per tier
- Remove POC dead code from `poc/k1_poc/` (or archive)
- Update architecture diagrams to reflect final production layout
- Update README and deployment docs

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## Dependency Graph

```
M0 (Pre-Flight)
 ├── M1 (IModelPort)
 ├── M2 (ICapabilityPort)  
 ├── M3 (IBusPort)
 └── M4 (IStoragePort Audit)
      │
      ▼
M5 (The Big Copy) ← requires M1-M4 all green
 ├── M6 (Fabric Wiring)
 ├── M7 (Model Hub Wiring)
 │    │
 │    ▼
 ├── M8 (Orchestrator Wiring) ← requires M6 + M7
 │    │
 │    ▼
 └── M9 (Planner Wiring) ← requires M8 (future)
      │
      ▼
M10 (Integration & Hardening) ← requires M6-M9
```

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Import path breakage during Big Copy | HIGH | Automated find-replace script + test gate |
| Fabric provider registration mismatch | MEDIUM | Contract tests per capability before swap |
| Model Hub latency regression | MEDIUM | A/B benchmark: direct adapter vs Model Hub |
| Orchestrator state management conflicts | HIGH | Orchestrator is stateless actor — verify no SS writes |
| Test coverage gaps from POC→production move | HIGH | M0 establishes baseline coverage report |

---

## Appendix: File Count Estimates

| Source | Files | Lines (approx) |
|--------|-------|-----------------|
| `poc/k1_poc/fsm/` | 18 | ~3,500 |
| `poc/k1_poc/react/` | 3 | ~800 |
| `poc/k1_poc/prompt/` | 9 | ~2,000 |
| `poc/k1_poc/protocols/` | 18 | ~3,000 |
| `poc/k1_poc/sessionstate/` | 20+ | ~4,000 |
| `poc/k1_poc/actors/` | 4+ | ~600 |
| `poc/k1_poc/tools/` | 7 | ~1,500 |
| `poc/k1_poc/llm/` | 3+ | ~500 |
| `poc/k1_poc/bus/` | 5+ | ~400 |
| Other (`delta/`, `events/`, etc.) | 15+ | ~2,000 |
| **Total** | **~100+** | **~18,000+** |
