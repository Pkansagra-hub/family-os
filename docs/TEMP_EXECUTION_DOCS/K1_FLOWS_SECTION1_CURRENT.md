# K1 Flows — Section 1 (Core Conversation) Current State

**Source-of-truth design doc:** [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md) §1 (lines 9–433)
**Inventory:** [K1_FLOWS_ENUMERATED.md](K1_FLOWS_ENUMERATED.md) §1
**Architectural override:** [docs/plans_completed_donotrefer/temp_tier_fix_plan.md](../plans_completed_donotrefer/temp_tier_fix_plan.md) — the K1_FLOWS.md tier model is **superseded** by the implicit-tier design (see Addendum at end of this file).
**Verification basis:** subagent code-scan of `k1/concierge/`, `k1/orchestrator/`, `k1/planner/`, `k1/fabric/`, plus authoritative `k1/concierge/_scan_temp/*.md` reference scan
**Empirical proof:** real Gemini boot via `scripts/kernel_smoke_drive.py --hub --turns 5` (ALL GREEN) plus P1.1/P1.2 weather-prompt trace from the tier-fix plan
**Date:** 2026-04-24

Legend: ✅ wired (live + observable) · ⚠️ partial (works but diverges from doc) · ❌ missing (not in production code) · 🔵 aspirational (named in design only)

---

## Section 1 Status Summary

| F# | Name | Status | One-line gap |
|---|---|---|---|
| F01 | User Input → ACKING | ⚠️ partial | No `ACKING` state — work happens in DISPATCHING; no 22ms budget; `StubPhase1Pipeline` is default, real `UltraBERTPhase1Pipeline` exists but not wired |
| F02 | Uncertainty Check & Clarification | ⚠️ partial | No `UncertaintyEstimator` / `EntropyMinQuestionPlanner`; `clarification.detected` trigger never published anywhere |
| F03 | Interrupt Handling | ✅ / 🔵 | User-input interrupt path **wired & smoke-proven**; sub-agent `DELTA_BUS` / `AGGREGATION_WINDOW` are aspirational |
| F04 | LOW Tier Fast Path | ⚠️ partial | Not Fabric-direct — LOW routes to Back actor (ReAct loop), which calls Fabric |
| F05 | MEDIUM Tier Reasoning | ⚠️ partial | Real `OrchestratorService` mailbox exists; FSM silently falls back to Back if `_orchestrator is None` |
| F06 | HIGH Tier Planning | ⚠️ partial | 4-stage Planner + DAGExecutor are real, but FSM uses `PassthroughPlannerStub` and reroutes HIGH → MEDIUM |
| F07 | CRISIS Tier Safety Protocol | ✅ | Inline `_deliver_crisis_response` with hardcoded 988 text; no SAFETY_MAILBOX/WFQ |
| F08 | LOW Response Delivery | ⚠️ partial | No tier branching; no `response.stream`; no `user.ack` topic — return to LISTENING is FSM-internal |
| F09 | MED/HIGH Response Delivery | ⚠️ partial | No standalone aggregator (uses `FSMTurnState.pending_results` + `WeaveBatcher` 500ms); `decide_response_final` ✅ all 13 branches |
| F10 | Preliminary Ack Generation | ❌ | No `preliminary_ack` event in production; only present in `poc/concierge_fsm_poc/` |

**Headline:** Section 1 has 1 fully-wired flow (F07), 1 mostly-wired (F03), 7 partial flows that work-but-diverge from the design diagram, and 1 missing flow (F10). The conversation loop **does work end-to-end** (proven by smoke run); the architecture doc is more aspirational/normative than the as-built code.

---

## F01 — User Input → ACKING ⚠️ partial

### As-built path
1. Bus topic `k1.concierge.user_input` received → [k1/concierge/fsm/controller.py#L1103](../../k1/concierge/fsm/controller.py#L1103) `_on_user_input()`
2. Transition table: `LISTENING → DISPATCHING` on `user.input` ([transition_table.py](../../k1/concierge/fsm/transition_table.py)) — **no `ACKING` state exists**
3. `_run_phase1_with_arbiter()` ([controller.py#L1819](../../k1/concierge/fsm/controller.py#L1819)) runs Phase 1 inside `TurnLock` while controller is already in DISPATCHING
4. `Phase1Pipeline.classify(text)` defaults to `StubPhase1Pipeline`; real `UltraBERTPhase1Pipeline` lives at [k1/concierge/fsm/ultrabert_phase1.py](../../k1/concierge/fsm/ultrabert_phase1.py) but requires explicit M10 E10.1 wiring + GPU
5. Adapter: `K1UltraBERTAdapter` → `familyos_ultrabert.Client` (real); `StubUltraBERTAdapter.analyze()` returns `None`

### Documented vs actual
| Doc claim | Reality |
|---|---|
| `ACKING` state | Does not exist — DISPATCHING does the work |
| 22ms budget enforced | No timeout / SLA wrapper around `classify()` |
| UltraBERT 22ms classification | Real pipeline exists but stub is default |

### Gap
- Either rename ACKING → DISPATCHING in the design doc, OR introduce ACKING as a distinct ephemeral state for the Phase 1 window.
- Wire `UltraBERTPhase1Pipeline` as default when GPU/model present (M10 E10.1).
- Add deadline timer around `_phase1_pipeline.classify()` if 22ms is a real SLO.

---

## F02 — Uncertainty Check & Clarification ⚠️ partial

### As-built path
- `CLARIFYING_USER` state exists ([states.py](../../k1/concierge/fsm/states.py), value 6)
- Transition `* → CLARIFYING_USER` on trigger `clarification.detected` ([transition_table.py#L78](../../k1/concierge/fsm/transition_table.py#L78))
- **`clarification.detected` is never emitted by any current code path** (grep: zero callers) → state is unreachable in live runs
- Mechanism present today: Front LLM (in `CLARIFY_ASK` mode, [k1/concierge/prompt/mode.py](../../k1/concierge/prompt/mode.py)) decides to call `update_clarifications` tool ([implementations.py#L341](../../k1/concierge/tools/implementations.py#L341)) → writes to SS `clarifications` section (= `PENDING_CLARIFICATIONS`)
- `_get_clarification_state()` in [front.py](../../k1/concierge/actors/front.py) reads back the SS section to feed next prompt

### Documented vs actual
| Doc component | Reality |
|---|---|
| `UNCERTAINTY_ESTIMATOR` (entropy-based, threshold ≥ 0.2) | 🔵 Does not exist |
| `ENTROPY_MIN_QUESTION_PLANNER` (1–2 questions) | 🔵 Does not exist — Front LLM authors questions |
| `PENDING_CLARIFICATIONS` store | ✅ Exists as SS `clarifications` section |
| FSM transition into clarification flow | ⚠️ Wired in transition table, never triggered |

### Gap
- Emit `TRIGGER_CLARIFICATION_DETECTED` from Front actor when LLM elects to clarify (or from a future UncertaintyEstimator).
- UncertaintyEstimator + EntropyMinQuestionPlanner are entirely greenfield work.

---

## F03 — Interrupt Handling ✅ (user path) / 🔵 (sub-agent path)

### As-built path (user-input mid-turn)
1. `user.input` arrives while in COMPANIONING/PROGRESSING → `_handle_interrupt()` ([controller.py#L1576](../../k1/concierge/fsm/controller.py#L1576))
2. `ConversationArbiter` ([fsm/arbiter.py](../../k1/concierge/fsm/arbiter.py), M5) classifies **deterministically** (no LLM): CANCEL / MODIFY_INFLIGHT / DEFER / PARALLEL_NEW
3. `_handle_arbiter_parallel_new()` transitions INTERRUPT_HANDLING → DISPATCHING in one synchronous step ([controller.py#L1598](../../k1/concierge/fsm/controller.py#L1598))
4. Legacy `InterruptClassifier` (keyword-based, [interrupt_handler.py](../../k1/concierge/fsm/interrupt_handler.py)) still instantiated but superseded by Arbiter at runtime

### Documented vs actual
| Doc component | Reality |
|---|---|
| `INTERRUPT_HANDLING` state | ✅ Exists (states.py value 9) |
| User topic-change → CANCEL / DEFER routing | ✅ Wired via Arbiter |
| `DELTA_BUS` (sub-agent clarification aggregation) | 🔵 Does not exist — zero matches |
| `AGGREGATION_WINDOW` | 🔵 Does not exist |
| Sub-agent interrupt → CLARIFYING_WORKER | ⚠️ CLARIFYING_WORKER **is** implemented, but reached via `task.suspended` (HITL) not delta_bus |
| Durable "Graceful State Save" hold | ⚠️ INTERRUPT_HANDLING is transient (single sync 2-step), no explicit snapshot serialization |

### Gap
- `DELTA_BUS` + `AGGREGATION_WINDOW` are unimplemented architectural concepts.
- Sub-agent clarifications today flow through `task.suspended` → `_on_task_suspended()`, not the documented delta-bus aggregation.

---

## F04 — LOW Tier Fast Path ⚠️ partial

### As-built path
- LOW tier routing: [orchestrator/routing.py#L207–L225](../../k1/concierge/orchestrator/routing.py#L207) `_route_low()` emits `k1.orchestration.task.dispatch.v1`
- FSM dispatch: [controller.py#L2189–L2195](../../k1/concierge/fsm/controller.py#L2189) `_route_via_orchestrator()` → `_deliver_to_back(canonical_env)` (Back actor handles, no Orchestrator involved)
- Back actor (ReAct loop) calls Fabric via `invoke_capability()` with 1-call budget for fast path

### Documented vs actual
| Doc claim | Reality |
|---|---|
| FSM → Fabric **direct**, bypass Orchestrator AND Back | ❌ FSM → Back actor (ReAct) → Fabric |
| Model Gateway shortcut | ❌ No `MODEL_GATEWAY` component; Back invokes IModelHubPort itself |
| LOW tier latency advantage | ✅ Functionally equivalent — single Fabric call, no Orchestrator overhead |

### Gap
- Either accept Back-as-fast-path in the doc, or introduce a true FSM-direct Fabric dispatch for LOW.

---

## F05 — MEDIUM Tier Reasoning ⚠️ partial

### As-built path
- MEDIUM routing: [controller.py#L2171–L2183](../../k1/concierge/fsm/controller.py#L2171) — if `self._orchestrator is None` → **silently falls back to Back** (LOW path); else `asyncio.create_task(_run_medium_orchestration(...))`
- Real `OrchestratorService` ([k1/orchestrator/orchestration/orchestrator_service.py#L227–L258](../../k1/orchestrator/orchestration/orchestrator_service.py#L227)) has real `IMailboxPort` + StepRunner — **not a stub**
- Calls `self._orchestrator.handle_task(task_envelope)`

### Documented vs actual
| Doc claim | Reality |
|---|---|
| Orchestrator mailbox + StepRunner | ✅ Real |
| Pre-DISPATCHING LLM reasoning step | ❌ Tier set by Phase 1, no separate reasoning hop |
| MEDIUM as a distinct observable branch | ⚠️ Only if `_orchestrator` is injected; else degrades to Back |

### Gap
- Confirm production factory always injects `_orchestrator` (otherwise MED silently behaves like LOW).
- Document or remove the silent fallback.

---

## F06 — HIGH Tier Planning ⚠️ partial

### As-built path
- HIGH at FSM: [controller.py#L2119–L2136](../../k1/concierge/fsm/controller.py#L2119) `PassthroughPlannerStub` wraps intent as 1-step plan, then **re-routes via MEDIUM path** (`route_task_sync(dispatch, ComplexityTier.MEDIUM)`)
- Comment in code: *"real Planner is a later milestone"*
- **Real components exist but aren't reached from FSM:**
  - `OrchestratorService.dispatch_high()` two-phase protocol ([orchestrator_service.py#L229–L232](../../k1/orchestrator/orchestration/orchestrator_service.py#L229))
  - Real `DAGExecutor` with `build_waves()`, parallel waves, saga compensation ([dag_executor.py](../../k1/orchestrator/orchestration/dag_executor.py))
  - 4 real planner stages: [planner/stages/sketch_service.py](../../k1/planner/stages/sketch_service.py), `expand_service.py`, `validate_service.py`, `commit_service.py`
  - Factory wires both StepRunner and DAGExecutor: [orchestrator/factory.py#L316–L335](../../k1/orchestrator/factory.py#L316)

### Documented vs actual
| Doc claim | Reality |
|---|---|
| FSM → Orchestrator → 4-stage Planner → DAGExecutor | ❌ FSM short-circuits via `PassthroughPlannerStub` to MEDIUM path |
| 4-stage Planner exists | ✅ Real (Sketch / Expand / Validate / Commit) |
| DAGExecutor with parallel waves + saga | ✅ Real |
| Two-phase HIGH dispatch | ✅ Implemented in OrchestratorService but not invoked |

### Gap
- Replace `PassthroughPlannerStub` re-route in `_route_via_orchestrator()` with a call into `OrchestratorService.dispatch_high()`.
- Plumbing is the only blocker — destination components are production-ready.

---

## F07 — CRISIS Tier Safety Protocol ✅ wired

### As-built path
- Phase 1 returns `safety_band == "CRISIS"` → early return: [controller.py#L1802–L1808](../../k1/concierge/fsm/controller.py#L1802)
- `_deliver_crisis_response()` ([controller.py#L2004–L2027](../../k1/concierge/fsm/controller.py#L2004)) emits `final_response` with `source="crisis_protocol"` and **hardcoded** 988 Suicide & Crisis Lifeline canned text
- `_SAFETY_BAND_MAP`: `"CRISIS" → PrivacyBand.RED` ([controller.py#L1647](../../k1/concierge/fsm/controller.py#L1647))
- Config: `crisis_iterations: {"CRISIS": 3}` ([config/loader.py#L314](../../k1/concierge/config/loader.py#L314))

### Documented vs actual
| Doc claim | Reality |
|---|---|
| ULTRABERT_SAFETY → CRISIS_DETECTOR → SAFETY_OVERRIDE → TIER_CRISIS | ⚠️ All collapsed into Phase 1 `safety_band` check; no distinct CrisisDetector class |
| `CrisisHandler` class | ❌ Inlined in controller |
| `SAFETY_MAILBOX` (WFQ URGENT priority) | ❌ Direct bus emit, no priority queue |
| Canned response from Model Gateway | ❌ Hardcoded string in controller |
| Escalation path | ❌ Not present |

### Gap (acceptable for current bootstrap)
- Crisis path **bypasses LLM entirely** and emits safe text immediately — production-acceptable.
- SAFETY_MAILBOX/WFQ + escalation are future hardening, not blocking.

---

## F08 — LOW Tier Response Delivery ⚠️ partial

### As-built path
1. Back emits `task.complete` → [controller.py#L2551–L2557](../../k1/concierge/fsm/controller.py#L2551) transitions COMPANIONING/PROGRESSING → DELIVERING
2. `_deliver_to_front(envelope)` ([controller.py#L2559](../../k1/concierge/fsm/controller.py#L2559)) — Front actor invoked with envelope (incl. tool results)
3. Front `front_handler()` calls `IModelHubPort` to author response, emits `k1.response.final.v1`
4. `_on_response_final` ([controller.py#L3258](../../k1/concierge/fsm/controller.py#L3258)) → `decide_response_final` branch 7 ([response_final_table.py#L100](../../k1/concierge/fsm/response_final_table.py#L100)) → `_finalize_turn()` → `_drain_front_lock_queue()` → LISTENING

### Documented vs actual
| Doc claim | Reality |
|---|---|
| Distinct LOW-tier delivery path | ❌ No tier branching in delivery — same handler for all tiers |
| `TOOL_RESULT_BUFFER` component | ❌ Results live in `FSMTurnState.pending_results` |
| MODEL_GATEWAY direct call | ❌ Front actor → IModelHubPort |
| `response.stream` topic emitted | ❌ Never emitted; only `k1.response.final.v1` |
| `user.ack` topic emitted to return to LISTENING | ❌ Topic does not exist; transition is FSM-internal via `decide_response_final` |

### Gap
- `user.ack` documentation is **misleading/aspirational** — actual mechanism is `response.final` → branch 7/8 → finalize.
- `response.stream` is unimplemented; would require Front actor streaming token emission.

---

## F09 — MEDIUM/HIGH Response Delivery ⚠️ partial

### As-built path
- Same `task.complete` → DELIVERING entry as F08
- Multi-result aggregation: `FSMTurnState.pending_results` list + `WeaveBatcher` 500ms window ([protocols/weave_batcher.py](../../k1/concierge/protocols/weave_batcher.py))
- When `response.final` fires with `has_pending_results=True`: `decide_response_final` branch 4 → WEAVING → `_schedule_weave_flush()` → `_flush_weave_now()` ([controller.py#L3720–L3810](../../k1/concierge/fsm/controller.py#L3720)) drains all pending results into single weave envelope for Front
- `decide_response_final` ✅ **all 13 branches implemented** in [response_final_table.py](../../k1/concierge/fsm/response_final_table.py) as pure function
- PROGRESSING state delta handling: `tool.started` enters PROGRESSING; `k1.agent.*.delta.v1` topics drive deltas ✅

### Documented vs actual
| Doc claim | Reality |
|---|---|
| `decide_response_final` 13 branches | ✅ Complete |
| Multi-step result aggregation | ⚠️ No standalone aggregator class — `pending_results` + WeaveBatcher do the job |
| MODEL_GATEWAY 2–8K token context | ❌ Front actor calls model directly |
| `user.ack` → LISTENING | ❌ Same as F08 — does not exist |
| PROGRESSING deltas | ✅ Wired |

### Gap
- Aggregation is implicit (state field + batcher) rather than an explicit named component — acceptable; doc could be updated.

---

## F10 — Preliminary Ack Generation ❌ missing in production

### As-built path
- **Zero matches** for `preliminary_ack` in `k1/concierge/**/*.py`
- Only present in POC: [poc/concierge_fsm_poc/tests/test_loop.py#L316](../../poc/concierge_fsm_poc/tests/test_loop.py#L316), [poc/concierge_fsm_poc/tests/test_integration.py#L57](../../poc/concierge_fsm_poc/tests/test_integration.py#L57) — `Event.PRELIMINARY_ACK_SENT`, transition `DISPATCHING → COMPANIONING` via this event
- Production: DISPATCHING → COMPANIONING is triggered by `task.dispatch` (Front emits `build_task_dispatch` envelope), not a preliminary ack
- Front (`front.py` step 10) emits `build_task_dispatch` then `build_final_response` — full conversational response, no tier-gated separate ack

### Documented vs actual
| Doc claim | Reality |
|---|---|
| MED/HIGH triggers `MODEL_GATEWAY` → preliminary ack → COMPANIONING | ❌ Not wired |
| Tier-gated ack (LOW skips) | ❌ No tier check |
| Conversational continuity prompt | ⚠️ Front LLM may say "Working on it" naturally inside `response.final`, but it's not a distinct event |

### Gap (to realize F10)
1. Add tier detection in `_run_phase1_with_arbiter` or Front dispatch path.
2. Emit dedicated `preliminary_ack` event for MED/HIGH.
3. Wire DISPATCHING → COMPANIONING transition on that event (POC has the FSM table for this).
4. Keep Back execution parallel.

---

## Cross-Cutting Findings

1. **Naming drift is the dominant gap**: many "components" in K1_FLOWS.md (UNCERTAINTY_ESTIMATOR, ENTROPY_MIN_QUESTION_PLANNER, MODEL_GATEWAY, TOOL_RESULT_BUFFER, SAFETY_MAILBOX, CrisisHandler, DELTA_BUS, AGGREGATION_WINDOW) **don't exist as classes** — their responsibilities are either inlined in `controller.py`, handled by Front/Back actors, or simply absent.
2. **`user.ack` topic does not exist anywhere** — F08/F09 documentation of it is wrong; turn termination is entirely internal to FSM via `decide_response_final` branch 7/8 → `_finalize_turn()`.
3. **`response.stream` is unimplemented** — only `k1.response.final.v1` exists. Streaming is not a current capability.
4. **HIGH-tier Planner is the biggest "exists-but-not-wired" gap**: real 4-stage Planner + DAGExecutor + `dispatch_high()` are production-ready; FSM short-circuits past them via `PassthroughPlannerStub`.
5. **MEDIUM tier silent fallback risk**: if `self._orchestrator is None`, MED degrades to Back (LOW behavior) without warning.
6. **Phase 1 is the silent gate for everything** — it sets tier, safety_band, intent. Whether `StubPhase1Pipeline` or real `UltraBERTPhase1Pipeline` runs determines whether F02 (uncertainty), F07 (crisis), and F04–F06 (tier dispatch) have meaningful inputs.
7. **What works end-to-end (smoke-proven):** F01 (as DISPATCHING) → F03 (user-interrupt arm) → F04 (Back-as-fast-path variant) → F08 (FSM-internal return-to-LISTENING). Five-turn Gemini run completed cleanly through this skeleton.

---

## Recommended Next Actions (priority order)

| Pri | Action | Touches |
|---|---|---|
| P0 | Wire `UltraBERTPhase1Pipeline` as default when adapter healthy | F01, F02, F07, F22 (tier source) |
| P0 | Replace `PassthroughPlannerStub` with `OrchestratorService.dispatch_high()` invocation | F06 |
| P1 | Emit `clarification.detected` from Front when LLM calls `update_clarifications` | F02 |
| P1 | Loud-fail (or auto-construct stub Orchestrator) when `_orchestrator is None` in MED | F05 |
| P2 | Port preliminary-ack from `poc/concierge_fsm_poc` into production FSM | F10 |
| P3 | Update K1_FLOWS.md to either rename components to match code OR mark them aspirational | Whole doc |
| P3 | Decide whether `response.stream` and `user.ack` are real future work or doc artifacts | F08, F09 |

---

**Section 1 complete. Next:** §2 UltraBERT Classification Flows (F11–F32) — 22 flows, will need 4–5 subagents.

---

## Addendum — Tier-Plan Re-Rating (2026-04-24)

After reading [docs/plans_completed_donotrefer/temp_tier_fix_plan.md](../plans_completed_donotrefer/temp_tier_fix_plan.md), several Section 1 ratings change. The K1_FLOWS.md design doc predates the **implicit-tier model** that has now been implemented (P1.1+P1.2 shipped, P2.1+P2.2 shipped; only P3 — strip the residual tier machinery — remains). Per Decisions A/B/C of the plan:

| Decision | Implication for K1_FLOWS §1 |
|---|---|
| **A** UltraBERT keeps intent / safety / affect / NER / embedding heads — **only `complexity_tier` is removed** | Tier-classification node in F01/F22 is **intentionally deprecated**, not a gap |
| **B** Tier is **implicit in Front's tool choice**: `invoke_capability` IS LOW; `dispatch_task` IS MED; `dispatch_task(plan=True)` IS HIGH | F04 / F05 / F06 routing diagrams in K1_FLOWS.md are **superseded** — tier is decided by which tool the Front LLM picks, not by a classifier output |
| **C** No new "answer composition" stage — **Front's existing ReAct loop composes** after Fabric returns | F08 LOW delivery diagram (FSM → MODEL_GATEWAY → DELIVERING) is **superseded** — Front's next ReAct iteration IS the delivery |
| **D** No tier dimension on tool allowlists — single `FRONT_TOOLS` / `BACK_TOOLS` per actor | Tier-allowlist plumbing (`FRONT_TIER_ALLOWLISTS`) is scheduled for deletion in P3 |

### Re-rated Section 1 status

| F# | Old rating | New rating | Why changed |
|---|---|---|---|
| F01 User Input → ACKING | ⚠️ partial | **⚠️ partial (correctly so)** | Still no `ACKING` state; UltraBERT pipeline is real; tier-classification gap is **by design, not missing work** |
| F02 Uncertainty & Clarification | ⚠️ partial | **⚠️ partial (by-design)** | `UncertaintyEstimator` / `EntropyMinQuestionPlanner` are deliberately *not* being built — Front LLM (CLARIFY_ASK mode) IS the estimator. Only gap: `clarification.detected` trigger emission |
| F03 Interrupt | ✅/🔵 | **✅/🔵** unchanged | DELTA_BUS still aspirational |
| F04 LOW Tier Fast Path | ⚠️ partial | **✅ wired (revised semantics)** | Real LOW is now `Front → invoke_capability → Fabric → ReAct compose`. The "FSM → Fabric direct bypass" in K1_FLOWS.md is **wrong-by-design**; the Front-direct path is the locked-in production design and is smoke-proven (P1.2) |
| F05 MEDIUM Tier | ⚠️ partial | **✅ wired (revised semantics)** | Front picks `dispatch_task` → Back. Silent-fallback risk if `_orchestrator is None` is the only remaining gap |
| F06 HIGH Tier | ⚠️ partial | **⚠️ partial** unchanged | Real Planner+DAGExecutor exist but `PassthroughPlannerStub` still reroutes HIGH → MED. Targeted by P3 (or earlier) |
| F07 CRISIS | ✅ | **✅** unchanged | |
| F08 LOW Response Delivery | ⚠️ partial | **✅ wired (revised semantics)** | Per Decision C, "delivery" for LOW is the Front ReAct loop's next compose iteration. Already smoke-proven (weather prompt: 3 iters, 243-char composed reply). The K1_FLOWS.md "FSM → MODEL_GATEWAY → DELIVERING" diagram is **superseded** |
| F09 MED/HIGH Delivery | ⚠️ partial | **⚠️ partial** unchanged | `decide_response_final` 13 branches ✅; weave aggregation ✅; `user.ack`/`response.stream` topics still don't exist |
| F10 Preliminary Ack | ❌ missing | **🔵 deprecated-by-design (Decision C)** | "No new composition stage." A separate `preliminary_ack` event would duplicate what Front's first pre-dispatch turn already does ("Working on it…"). The POC implementation is **not** being ported — the Front LLM authors any acknowledgment naturally |

### Revised Section 1 scoreboard

| Status | Count | Flows |
|---|---|---|
| ✅ wired | **5** | F03 (user-arm), F04, F05, F07, F08 |
| ⚠️ partial | **3** | F01 (no ACKING state, by design wrt tier), F02 (clarification trigger missing), F06 (Planner not wired in FSM), F09 (`user.ack`/`response.stream` aspirational) |
| 🔵 by-design / aspirational | **2** | F03 sub-agent path (DELTA_BUS), F10 (preliminary ack — Decision C says don't build it) |
| ❌ truly missing | **0** | — |

### Updated next-action priorities

| Pri | Action | Touches | Source |
|-----|---|---|---|
| P0 | **Execute P3** of tier-fix plan: delete `_compute_complexity()`, `complexity_tier` field, `KernelConfig.tool_tier`, `FRONT_TIER_ALLOWLISTS`, tier reads in `dispatch_task` | F01, F22 (§2), tooling | tier-fix plan §P3 |
| P0 | Replace `PassthroughPlannerStub` with `OrchestratorService.dispatch_high()` invocation | F06 | unchanged |
| P1 | Wire `UltraBERTPhase1Pipeline` as default when adapter healthy (still needed for intent/safety/affect/NER — just NOT for tier) | F02, F07, §2 heads | revised |
| P1 | Emit `clarification.detected` from Front when LLM calls `update_clarifications` | F02 | unchanged |
| P1 | Loud-fail when `_orchestrator is None` in MED routing | F05 | unchanged |
| P3 | Update K1_FLOWS.md to describe the **implicit-tier** model and remove ACKING/MODEL_GATEWAY/UNCERTAINTY_ESTIMATOR component names | whole doc | tier-fix plan |
| — | **Drop** "port preliminary-ack from POC" — Decision C deprecates it | F10 | tier-fix plan §1 C |
| — | **Drop** "build UncertaintyEstimator + EntropyMinQuestionPlanner" — Front LLM is the estimator | F02 | tier-fix plan §1 (extension of B/C logic) |

**Net effect:** Section 1 is in much better shape than the first pass suggested. The "partial" ratings were largely **doc drift**, not implementation gaps. The real remaining work is P3 (tier strip) + F06 HIGH-tier wiring + F02 clarification trigger.
