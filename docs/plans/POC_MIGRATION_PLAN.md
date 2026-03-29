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
> **Gate**: All POC tests pass on `POC_Migration` branch. Dependency map validated. Test inventory documented.

### Baseline Numbers

| Metric | Count |
|--------|-------|
| External test files (`tests/poc/`) | 73 |
| External test functions | 3,054 |
| Internal harness test files (`poc/k1_poc/testing/harness/`) | 10 |
| Internal harness test functions | 207 |
| **Total test functions** | **3,261** |
| Production .py files (`poc/k1_poc/`, excl demo/testing) | ~138 |
| Demo-only .py files (`poc/k1_poc/demo/`) | ~9 |
| Test harness .py files | ~21 |
| Config files (`poc/k1_poc/config/`) | 3 (loader.py, __init__.py, defaults.yaml) |
| POC folders (top-level in `poc/k1_poc/`) | 22 |
| K1 concierge .py files (existing) | 5 (all empty `__init__.py`) |
| External PyPI dependencies | 1 (google.genai, lazy-loaded) |
| K1 framework dependencies | k1.bus.* only |

### Epic E0.1 — Run Full Test Suite on POC_Migration Branch

> Verify that the branch merge didn't break anything. Establish the exact green/red/skip baseline.

**Issue E0.1.1** — Run `tests/poc/` full suite, record pass/fail/skip counts  
- Run: `python -m pytest tests/poc/ -v --tb=short`  
- Record: total, passed, failed, skipped, errors  
- File: capture output to `docs/test_results/m0_external_baseline.txt`  
- Touch points: none (read-only audit)

**Issue E0.1.2** — Run `poc/k1_poc/testing/harness/` internal suite  
- Run: `python -m pytest poc/k1_poc/testing/harness/ -v --tb=short`  
- Record: total, passed, failed, skipped, errors  
- File: capture output to `docs/test_results/m0_internal_baseline.txt`  

**Issue E0.1.3** — Document any existing failures as known-issues  
- If any tests fail, create a `docs/plans/M0_KNOWN_FAILURES.md` listing each failure with root cause  
- Classify each as: `migration-blocker` (must fix before M1) or `pre-existing` (existed before merge)  

### Epic E0.2 — Validate Dependency Map

> Confirm the auto-generated dependency map at `poc/k1_poc/docs/DEPENDENCY_MAP.md` (dated 2026-02-23) is still accurate after recent changes.

**Issue E0.2.1** — Regenerate import graph and diff against existing  
- Script: walk all `.py` under `poc/k1_poc/`, extract `from poc.k1_poc.X import` lines  
- Compare against `poc/k1_poc/docs/DEPENDENCY_MAP.md` Section 4 (folder-to-folder matrix)  
- Touch points: every `.py` file under `poc/k1_poc/` (read-only scan)  
- Output: updated `DEPENDENCY_MAP.md` if any new cross-folder imports found  

**Issue E0.2.2** — Verify zero circular dependencies  
- From the import graph, check that no folder cycle exists (A→B→C→A)  
- Known safe pattern: `kernel/bootstrap.py` imports everything (hub), but nothing imports `kernel/`  
- If circular dep found: document and flag as migration-blocker  

**Issue E0.2.3** — Document k1.* framework imports  
- List every `from k1.*` import across POC code  
- Currently known: `k1.bus.envelope`, `k1.bus.factory`, `k1.bus.impl.local_bus`, `k1.bus.impl.local_mailbox`, `k1.bus.ports.bus`, `k1.bus.ports.mailbox`, `k1.bus.timing.defaults`, `k1.bus.timing.timing_chain`, `k1.bus.adapters`  
- Touch points: `fsm/controller.py`, `actors/back.py`, `bus/setup.py`, `kernel/bootstrap.py`  
- Purpose: these are the imports that WON'T change path during the Big Copy (M5) since k1.bus stays at k1.bus  

### Epic E0.3 — Classify POC Files: Copy vs Stay vs Drop

> Every file in `poc/k1_poc/` must be tagged as one of: COPY (goes to k1/concierge), STAY (remains in poc/ for demo), DROP (dead code).

**Issue E0.3.1** — Tag all `poc/k1_poc/demo/` files as STAY  
- Files: `coordinator.py`, `coordinator_old.py`, `interactive.py`, `display.py`, `output_channel.py`, `iot_stubs.py`, `smith_family.py`, `preloaded_memories.py`, `runner.py`, `web/` directory  
- Rationale: demo harness, Smith family data, interactive UI — not production  
- Touch points: none (classification only)  

**Issue E0.3.2** — Tag all `poc/k1_poc/testing/` files as STAY  
- Files: `harness/engine.py`, `harness/test_*.py`, `fixtures/*.py`  
- Rationale: test utilities — reference tests/poc/ instead after migration  

**Issue E0.3.3** — Tag production files as COPY  
- Tag the following 22 directories as COPY targets:  
  `actors/`, `bus/`, `compression/`, `config/`, `delta/`, `events/`, `experience/`, `fabric/`, `fsm/`, `identity/`, `kernel/`, `ledger/`, `llm/`, `obs/`, `orchestrator/`, `prompt/`, `protocols/`, `react/`, `scheduler/`, `sessionstate/`, `task/`, `tools/`  
- Touch points: none (classification only)  

**Issue E0.3.4** — Identify dead code candidates for DROP  
- Scan for files not imported by anything (orphans)  
- Check `coordinator_old.py` (superseded by `coordinator.py`)  
- Check any `*.py.bak` or commented-out files  
- Output: list of DROP candidates with justification  

### Epic E0.4 — Audit K1 Concierge Target Structure

> Understand what already exists in `k1/concierge/` and what needs to be created/replaced.

**Issue E0.4.1** — Document existing k1/concierge/ contents  
- Current state: 5 empty `__init__.py` files in `k1/concierge/`, `k1/concierge/affective/`, `k1/concierge/empathy/`, `k1/concierge/rhythm/`, `k1/concierge/tools/`  
- Docs: `concierge.md`, `concierge.mmd`, `concierge_fsm_flows.md`, `README.md`  
- Decision needed: do we keep/merge existing docs or replace entirely from POC?  

**Issue E0.4.2** — Map POC directories → K1 concierge directories  
- Create mapping table:  

  | POC Source | K1 Target | Notes |
  |---|---|---|
  | `poc/k1_poc/actors/` | `k1/concierge/actors/` | New directory |
  | `poc/k1_poc/bus/` | `k1/concierge/bus/` | New; wraps k1/bus/ |
  | `poc/k1_poc/compression/` | `k1/concierge/compression/` | New |
  | `poc/k1_poc/config/` | `k1/concierge/config/` | Merge with k1/config/? |
  | `poc/k1_poc/delta/` | `k1/concierge/delta/` | New |
  | `poc/k1_poc/events/` | `k1/concierge/events/` | New |
  | `poc/k1_poc/experience/` | `k1/concierge/experience/` | Replaces empty `affective/`, `empathy/`, `rhythm/` |
  | `poc/k1_poc/fabric/` | `k1/concierge/fabric/` | New; bridge to k1/fabric/ |
  | `poc/k1_poc/fsm/` | `k1/concierge/fsm/` | New |
  | `poc/k1_poc/identity/` | `k1/concierge/identity/` | New |
  | `poc/k1_poc/kernel/` | `k1/concierge/kernel/` | New; bootstrap becomes concierge entry point |
  | `poc/k1_poc/ledger/` | `k1/concierge/ledger/` | New |
  | `poc/k1_poc/llm/` | `k1/concierge/llm/` | New; port+adapter for model hub |
  | `poc/k1_poc/obs/` | `k1/concierge/obs/` | New |
  | `poc/k1_poc/orchestrator/` | `k1/concierge/orchestrator/` | New; bridge to k1/orchestrator/ |
  | `poc/k1_poc/prompt/` | `k1/concierge/prompt/` | New |
  | `poc/k1_poc/protocols/` | `k1/concierge/protocols/` | New |
  | `poc/k1_poc/react/` | `k1/concierge/react/` | New |
  | `poc/k1_poc/scheduler/` | `k1/concierge/scheduler/` | New |
  | `poc/k1_poc/sessionstate/` | `k1/concierge/sessionstate/` | New; already has ports |
  | `poc/k1_poc/task/` | `k1/concierge/task/` | New |
  | `poc/k1_poc/tools/` | `k1/concierge/tools/` | Replaces empty `k1/concierge/tools/` |

**Issue E0.4.3** — Decide: config merge strategy  
- POC has `poc/k1_poc/config/defaults.yaml` (59 tunable parameters)  
- K1 has `k1/config/` (separate config structure)  
- Decision: Does concierge carry its own config, or merge into k1/config/?  
- This affects import paths in `config/loader.py` and every file that calls `get_config()`  

### Epic E0.5 — Audit Smith Family Demo Isolation (Completed)

> Verify POC engine is not contaminated by demo-specific data.

**Issue E0.5.1** — ✅ Confirm engine layer has zero Smith family data  
- Result: FSM, ReAct, Prompt Builder (builder.py), SessionState, Bus, Delta, OPP, HITL, Weave — all **CLEAN**  
- `prompt/sections.py` has Smith names in **few-shot examples only** (teaches patterns, not data injection)  
- `fabric/family_capabilities.py` has mock return values with Smith defaults — replaced entirely by M6 (Fabric Wiring)  

**Issue E0.5.2** — ✅ Confirm data injection is parameter-driven  
- `KernelConfig.seed_memories` — accepts any family's data, no hardcoding  
- `build_persona_from_profile(family_profile)` — accepts any profile dict  
- `recall_fn` — generic keyword-match engine, receives memories as parameter  
- Demo data enters ONLY through `demo/coordinator.py` → `KernelConfig`  

### Epic E0.6 — Integration Test: Branch Health Verification

> Final gate: confirm the POC_Migration branch is healthy and ready for M1.

**Issue E0.6.1** — Run full test suite (external + internal), require 100% pass  
- Depends on: E0.1.1, E0.1.2, E0.1.3 (any migration-blockers must be fixed first)  
- Command: `python -m pytest tests/poc/ poc/k1_poc/testing/harness/ --tb=short`  
- Gate: 3,261 tests pass (or documented known-failures classified as pre-existing)  

**Issue E0.6.2** — Run import smoke test  
- Script: `python -c "from poc.k1_poc.kernel.bootstrap import start_kernel; print('OK')"` 
- Verifies the full import chain resolves on this branch  
- Touch points: validates `kernel/bootstrap.py` → all 12 cross-folder deps  

**Issue E0.6.3** — Tag baseline  
- Git tag: `m0-preflight-baseline`  
- Ensures we can always diff back to the pre-migration state  

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
