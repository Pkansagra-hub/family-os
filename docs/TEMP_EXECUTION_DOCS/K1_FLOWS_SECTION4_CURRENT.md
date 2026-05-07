# K1 Flows — Section 4 (Orchestrator) Current State

**Source-of-truth design doc:** [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md) §4 (lines 1886–2425)
**Inventory:** [K1_FLOWS_ENUMERATED.md](K1_FLOWS_ENUMERATED.md) §4
**Companions:** [K1_FLOWS_SECTION1_CURRENT.md](K1_FLOWS_SECTION1_CURRENT.md) · [K1_FLOWS_SECTION2_CURRENT.md](K1_FLOWS_SECTION2_CURRENT.md) · [K1_FLOWS_SECTION3_CURRENT.md](K1_FLOWS_SECTION3_CURRENT.md)
**Verification basis:** subagent code-scan with **mandatory kernel-side wiring inspection** (`k1/kernel/service.py`, `k1/orchestrator/factory.py`, `k1/concierge/factory.py`)
**Date:** 2026-04-27

Legend: ✅ wired · ⚠️ partial · ❌ missing · 🔵 stub-only / aspirational

---

## Section 4 Status Summary

| F# | Name | Status | One-line gap |
|---|---|---|---|
| F43 | Task Announcement & Bidding | ❌ missing | No `TaskAnnouncer`/`BidCollector`; `OrchestratorService._route_task()` is direct tier dispatch only |
| F44 | Multi-Criteria Scoring & Selection | ❌ missing | No `MCScorer`/`AgentSelector` in dispatch path; `find_alternatives()` exists but is constraint-repair, not agent selection |
| F45 | Parallel DAG Execution | ✅ wired | `DAGExecutor` with Kahn waves + `asyncio.gather` + `Semaphore(10)`; guards list empty in M2 |
| F46 | Saga Pattern Recovery | ⚠️ partial | `_compensate()` method exists, called after waves, increments saga metric; **body invokes no concrete compensating actions** (shell), no `ORCH_SAGA_COMPENSATING` event emitted |
| F47 | Constraint Manager Iteration | ✅ wired | `ConstraintResolver.resolve_iteratively()` (3-cycle) + `find_alternatives()` weighted scoring; HIL fallback after exhaustion |
| F48 | Solution Validation (LLM + Rule) | ⚠️ partial | `ConstraintResolver` does rule-only validation; **`SolutionValidator` class doesn't exist; LLM semantic leg absent** |
| F49 | Constraint HIL Fallback | ✅ wired | Two HIL paths: orchestrator emits `HILRequest` via delta_port + `HILCoordinator` 8-step cycle in concierge FSM |
| F50 | Workflow Scheduling & Trigger | ✅ wired | `WorkflowScheduler` with `croniter` tick loop; `CRON/EVENT/MANUAL` triggers (no `PROACTIVE`) |
| F51 | Workflow Run Supervisor | ✅ wired | `WorkflowRunSupervisor.start_run()`; single-active-run abort policy; immutable `RunManifest` |
| F52 | Workflow Compiler → DAG | ✅ wired | `WorkflowCompiler.compile()` → `CommittedPlan` (not named `ExecutionDAG`); idempotent, hash-based |

### Headline counts

| Status | Count | Flows |
|---|---|---|
| ✅ wired | **6** | F45, F47, F49, F50, F51, F52 |
| ⚠️ partial | **2** | F46, F48 |
| ❌ missing | **2** | F43, F44 |

**Headline finding:** the **workflow subsystem is the strongest layer in K1 so far** — Compiler → Supervisor → Scheduler → DAGExecutor → ConstraintResolver are all real, wired through `OrchestratorFactory.create_production()` step 14b, and started via `OrchestratorService.init()`. The two ❌ gaps (F43/F44 multi-agent bidding/scoring) are **architectural-aspiration only** — no announcement/bid/scoring infrastructure exists; dispatch is direct tier routing. F46 saga compensation is structurally hooked but the body is empty.

**Naming drift to flag:** `k1/scheduler/` and `k1/supervision/` are empty stub directories. The actual code lives in `k1/orchestrator/workflows/`. This is misleading and worth a doc/structure cleanup.

---

## F43 — Task Announcement & Bidding ❌ missing

- No `TaskAnnouncer`, no `BidCollector`, no `task.announce.v1` topic anywhere in `k1/`
- Actual path: `OrchestratorService._route_task()` at [k1/orchestrator/orchestration/orchestrator_service.py#L1288](../../k1/orchestrator/orchestration/orchestrator_service.py#L1288) → `_dispatch_medium()` or `_dispatch_high()` direct by `ComplexityTier` enum
- No agent registry enumeration, no bid window, no bid timeout — effectively a single-agent direct-dispatch system

**Gap:** the documented multi-agent marketplace pattern is pure design intent. Building it would require: agent registry, bid envelope schema, bid collection window with timeout, then F44 scoring.

---

## F44 — Multi-Criteria Scoring & Selection ❌ missing (in dispatch path)

- No `MCScorer`, no `AgentSelector` in dispatch path
- `_dispatch_medium` selects capability via direct `query_registry()` lookup with safety-band gate only — no scoring step
- **Adjacent code that could be evolved:** `ConstraintResolver.find_alternatives()` at [k1/orchestrator/orchestration/constraint_resolver.py#L542](../../k1/orchestrator/orchestration/constraint_resolver.py#L542) computes weighted scores (`W_SCHEMA=0.6` + `W_SAFETY=0.2` + `W_NAME=0.2`) — but it's **constraint-repair fallback** for missing capabilities, not runtime agent selection

**Gap:** if multi-agent selection becomes a real requirement, `find_alternatives()` is the closest scaffolding to extend. Today there's nothing in the live dispatch path.

---

## F45 — Parallel DAG Execution ✅ wired (the heavy hitter, all real)

| Component | Anchor |
|---|---|
| `DAGExecutor` class | [k1/orchestrator/orchestration/dag_executor.py#L117](../../k1/orchestrator/orchestration/dag_executor.py#L117) |
| `build_waves()` (Kahn topological sort, pure) | [dag_executor.py#L272](../../k1/orchestrator/orchestration/dag_executor.py#L272) |
| `execute()` (wave-sequential outer) | [dag_executor.py#L325](../../k1/orchestrator/orchestration/dag_executor.py#L325) |
| `execute_wave()` (`asyncio.gather`) | [dag_executor.py#L727](../../k1/orchestrator/orchestration/dag_executor.py#L727) |
| `asyncio.Semaphore(10)` per-wave concurrency | `_MAX_CONCURRENT_PER_WAVE = 10` in same file |
| Kernel wiring | [k1/orchestrator/factory.py#L335](../../k1/orchestrator/factory.py#L335): `dag_executor = DAGExecutor(...)` then injected into `OrchestratorService(dag_executor=...)` at [factory.py#L432](../../k1/orchestrator/factory.py#L432) |

**Caveats:**
- `guards` list is empty in M2 (stub hook for M3 timeout/resource guards)
- `step_runner` is type-hinted `Any`; called at [dag_executor.py#L897](../../k1/orchestrator/orchestration/dag_executor.py#L897) — concrete implementation needs separate verification
- Safety band re-read per wave (`_check_safety_band`) and `$`-reference param resolution via `ParamResolver` are present

---

## F46 — Saga Pattern Recovery ⚠️ partial

| Item | Finding |
|---|---|
| `_compensate()` method | Exists at [k1/orchestrator/orchestration/dag_executor.py#L1142](../../k1/orchestrator/orchestration/dag_executor.py#L1142) |
| Called from execute path | Unconditionally after wave loop at [dag_executor.py#L533](../../k1/orchestrator/orchestration/dag_executor.py#L533) |
| Metrics | `_metrics.increment_saga_compensation(count=...)` |
| WAL marker | `bridge_port.write_wal("DAG_COMPLETE", {"status": "FAILED"})` |
| `ORCH_SAGA_COMPENSATING` event | Documented in `kernel.md#L1684` but **no emit call found in code** |
| Compensating action body | **No `compensate_step` call found** — `_compensate()` body likely returns empty list / no-op |
| Test coverage | None found for saga rollback |

**Gap:** the hook is wired, the metric increments, but no actual compensating action runs. Treat as "WAL marker only" until `_compensate()` body is implemented to dispatch real undo operations through `_step_runner` or `_fabric_port`.

---

## F47 — Constraint Manager Iteration ✅ wired

| Component | Anchor |
|---|---|
| `ConstraintResolver` class | [k1/orchestrator/orchestration/constraint_resolver.py#L224](../../k1/orchestrator/orchestration/constraint_resolver.py#L224) |
| `resolve_iteratively()` (3-cycle max) | [constraint_resolver.py#L648](../../k1/orchestrator/orchestration/constraint_resolver.py#L648) |
| `validate()` entrypoint | [constraint_resolver.py#L303](../../k1/orchestrator/orchestration/constraint_resolver.py#L303) |
| `find_alternatives()` (weighted scoring) | [constraint_resolver.py#L542](../../k1/orchestrator/orchestration/constraint_resolver.py#L542) |
| HIL fallback after exhaustion | `trigger_hil_fallback()` at [constraint_resolver.py#L460](../../k1/orchestrator/orchestration/constraint_resolver.py#L460) |
| Kernel wiring | [k1/orchestrator/factory.py#L349-L356](../../k1/orchestrator/factory.py#L349) |

**Naming drift:** docs call it `ConstraintManager`; code is `ConstraintResolver`. Same concept.
**Caveat:** `SCHEMA_OVERLAP_DEFAULT_V1 = 0.5` is a neutral placeholder — real schema introspection deferred to V2. Cross-category alternatives also deferred.

---

## F48 — Solution Validation (LLM + Rule) ⚠️ partial

- **No `SolutionValidator` class anywhere in live code.** Only referenced in `k1/structure.md#L93` (planning doc).
- The "validator" that actually runs is `ConstraintResolver.validate()` chain: `check_capabilities()` → `find_alternatives()` (scored) → `resolve_iteratively()` → `compute_time_budget()`
- This is **rule-based validation only**. The documented LLM semantic-validation leg (context coherence, intent alignment, ambiguity detection) does not exist
- Wired via factory step at [k1/orchestrator/factory.py#L364](../../k1/orchestrator/factory.py#L364)

**Gap:** if LLM-judged validation is a real requirement, it would need a new `SolutionValidator` class wrapping ModelGateway calls in addition to (or layered over) the existing `ConstraintResolver`.

---

## F49 — Constraint HIL Fallback ✅ wired (richer than documented)

Two distinct HIL paths exist and are both wired in production:

**Orchestrator-side HIL emit** (matches the documented F49):
- `ConstraintResolver` emits `HILRequest` via `delta_port` after `MAX_CYCLES=3` resolution failures
- Anchors: `DEFAULT_MAX_CYCLES=3` and `HIL_TIMEOUT_MS=60_000` in [constraint_resolver.py](../../k1/orchestrator/orchestration/constraint_resolver.py)

**Concierge/FSM-side HIL closed cycle** (richer than documented):
- `HILCoordinator` implements full 8-step closed cycle: validate safety band → check suspension limits → build `HILRequest` → persist → delegate `SuspensionManager` → emit `task.suspended.v1` → handle user response → emit `task.resume.v1`
- Anchors: [k1/concierge/protocols/hitl_coordinator.py](../../k1/concierge/protocols/hitl_coordinator.py), attach point [k1/concierge/fsm/controller.py#L529-L540](../../k1/concierge/fsm/controller.py#L529), `handle_needs_human` path [controller.py#L2750-L2786](../../k1/concierge/fsm/controller.py#L2750), construction in [k1/concierge/factory.py#L658-L660](../../k1/concierge/factory.py#L658)

**Gap:** explicit cross-boundary tracing for how an orchestrator-emitted `HILRequest` (delta_port) lands in the concierge FSM's suspension flow could use clearer documentation. Functionally both legs work.

---

## F50 — Workflow Scheduling & Trigger ✅ wired (heavy, all real)

| Component | Anchor |
|---|---|
| `WorkflowScheduler` class | [k1/orchestrator/workflows/workflow_scheduler.py#L97](../../k1/orchestrator/workflows/workflow_scheduler.py#L97) |
| `start()` | [workflow_scheduler.py#L139](../../k1/orchestrator/workflows/workflow_scheduler.py#L139) |
| `_tick_loop()` | [workflow_scheduler.py#L176](../../k1/orchestrator/workflows/workflow_scheduler.py#L176) |
| `_tick()` | [workflow_scheduler.py#L185](../../k1/orchestrator/workflows/workflow_scheduler.py#L185) |
| Construction | [k1/orchestrator/factory.py#L372-L380](../../k1/orchestrator/factory.py#L372) (`tick_interval_s=config.scheduler_tick_interval_ms/1000`) |
| Started by kernel | `scheduler.start()` inside `OrchestratorService.init()` at [orchestrator_service.py#L481](../../k1/orchestrator/orchestration/orchestrator_service.py#L481) |
| Trigger types | `CRON | EVENT | MANUAL` in [workflow_types.py](../../k1/orchestrator/workflows/workflow_types.py) |

**Highlights:** `croniter` CRON evaluation, timezone awareness via `zoneinfo` (stdlib), crash-recovery first-tick fires missed triggers, per-trigger `MailboxFullError` isolation, `compute_next_fire()` pure function, ticks enqueue `WorkflowRunRequest` at `priority=INTERACTIVE`.

**Gaps:**
- No `PROACTIVE` (AI-initiated) trigger type — docs mention it; code has only `CRON/EVENT/MANUAL`
- `k1/scheduler/__init__.py` is an empty stub directory (misleading)

---

## F51 — Workflow Run Supervisor ✅ wired

| Component | Anchor |
|---|---|
| `WorkflowRunSupervisor` class | [k1/orchestrator/workflows/workflow_supervisor.py#L87](../../k1/orchestrator/workflows/workflow_supervisor.py#L87) |
| `start_run(request) -> StartRunResult` | [workflow_supervisor.py#L118](../../k1/orchestrator/workflows/workflow_supervisor.py#L118) |
| `RunManifest` (frozen) + `RunStatus` enum | [workflow_types.py#L235](../../k1/orchestrator/workflows/workflow_types.py#L235) |
| Construction (5 deps: registry, compiler, storage, delta, bridge) | [k1/orchestrator/factory.py#L385-L393](../../k1/orchestrator/factory.py#L385) |
| Engine wiring | [k1/orchestrator/workflows/workflow_engine.py#L382-L383](../../k1/orchestrator/workflows/workflow_engine.py#L382) |

**Behaviors:** single-active-run policy (old run aborted via `_abort_run()` if RUNNING); immutable `RunManifest` status transitions (STARTING/RUNNING/COMPLETING/COMPLETED/FAILED); `complete_run()` / `fail_run()` persist via storage port; `deliver_result()` handles session-aware vs deferred routing (PROD-4); `_abort_run()` is idempotent.

**Gaps vs doc:**
- "Lease" abstraction is single-active-abort, not a formal lock primitive
- Timeout / resource-limit guards live in `DAGExecutor.guards` (currently empty in M2), not in supervisor
- `RunManifest.compiled_hash` field not verified
- `k1/supervision/__init__.py` is an empty stub directory

---

## F52 — Workflow Compiler → DAG ✅ wired

| Component | Anchor |
|---|---|
| `WorkflowCompiler` class | [k1/orchestrator/workflows/workflow_compiler.py#L77](../../k1/orchestrator/workflows/workflow_compiler.py#L77) |
| `compile()` async | [workflow_compiler.py#L112](../../k1/orchestrator/workflows/workflow_compiler.py#L112) |
| Construction (5 deps: fabric, delta, storage, state_port, clock) | [k1/orchestrator/factory.py#L364-L370](../../k1/orchestrator/factory.py#L364) |
| Used by supervisor | [workflow_supervisor.py#L44](../../k1/orchestrator/workflows/workflow_supervisor.py#L44) |
| Output executed by | `DAGExecutor` consumes the compiled `CommittedPlan` |

**Behaviors:** takes frozen `WorkflowSpec` → resolves `DynamicExpr` at execution time → validates capabilities against Fabric Registry → classifies gaps (`CAPABILITY_REMOVED`, `PERMISSION_CHANGE`) → produces `CommittedPlan` of resolved `PlanStep` instances. Hash-based integrity (`hashlib`). Idempotent (same clock → same output). Gap detection via `IWorkflowStoragePort.save_gap()`.

**Gaps vs doc:**
- No `ExecutionDAG` named type — `CommittedPlan` is the DAG representation
- No NL → spec compilation; compiler assumes structured `WorkflowSpec` input (NL → spec is upstream Planner job)
- Parallelism optimization happens in `DAGExecutor` Kahn waves, not in compiler
- V2 schema-level gap detection (field renames) deferred

---

## Cross-cutting findings

1. **Workflow subsystem is the strongest layer audited so far.** Compiler + Supervisor + Scheduler + DAGExecutor + ConstraintResolver are real, wired, and started by `OrchestratorService.init()`. Six of ten flows are ✅ wired.
2. **Multi-agent bidding/scoring (F43/F44) is pure design intent.** Dispatch is direct tier routing. If "agent marketplace" stays a goal, building announcement/bid/scoring is greenfield.
3. **Saga compensation (F46) is hooked but hollow.** `_compensate()` runs and increments metric but does no actual rollback. No `ORCH_SAGA_COMPENSATING` event emitted. Tests don't exercise it.
4. **`SolutionValidator` LLM leg (F48) doesn't exist.** What runs is `ConstraintResolver` rule-based validation. Decide whether to keep doc or build the LLM leg.
5. **Naming drift to clean up:**
   - `k1/scheduler/` and `k1/supervision/` are **empty stubs**; real code is in `k1/orchestrator/workflows/`
   - Doc `ConstraintManager` ↔ code `ConstraintResolver`
   - Doc `ExecutionDAG` ↔ code `CommittedPlan`
   - Doc `MCScorer` ↔ adjacent `find_alternatives()` (different purpose)
6. **HIL is healthier than documented.** `HILCoordinator` implements full 8-step closed cycle with task-suspended/resume events; orchestrator HIL emit feeds it via delta_port.
7. **DAGExecutor `guards` list is empty (M2).** Timeout/resource limits aren't enforced yet — important for F51 supervisor robustness once production load grows.

---

## Recommended next actions (priority order)

| Pri | Action | Touches | Source |
|---|---|---|---|
| P1 | Implement `_compensate()` body — call `_step_runner.compensate()` or fabric undo, emit `ORCH_SAGA_COMPENSATING`, add at least one test | F46 | new |
| P1 | Populate `DAGExecutor.guards` with at least timeout + max-retries guards (M3 milestone) | F45, F51 | planned |
| P2 | Decide F48 LLM-validator: build `SolutionValidator` (LLM+rule hybrid) OR amend doc to drop the LLM leg | F48 | new |
| P2 | Decide F43/F44 multi-agent: build announcement/bid/scoring OR amend doc to drop and call out single-agent direct-dispatch | F43, F44 | new |
| P3 | Either delete `k1/scheduler/` and `k1/supervision/` empty stubs OR move workflow code there to match doc | structure | new |
| P3 | Rename in K1_FLOWS.md: `ConstraintManager` → `ConstraintResolver`, `ExecutionDAG` → `CommittedPlan` | doc | new |
| P3 | Add `PROACTIVE` trigger type if AI-initiated workflow runs are needed; otherwise drop from doc | F50 | new |
| P3 | Document orchestrator → concierge HIL handoff path explicitly (delta_port HIL → FSM suspension) | F49 | doc |

---

**Section 4 complete. Next:** §5 Planner (4-Stage) Flows (F53–F59) — 7 flows. F53–F56 are the four planner stages (sketch/expand/validate/commit), F57–F59 are HIL legs.
