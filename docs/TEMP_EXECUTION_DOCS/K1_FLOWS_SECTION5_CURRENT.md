# K1 Flows — Section 5 (Planner 4-Stage) Current State

**Source-of-truth design doc:** [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md) §5 (lines 2427–2830)
**Inventory:** [K1_FLOWS_ENUMERATED.md](K1_FLOWS_ENUMERATED.md) §5
**Companions:** [K1_FLOWS_SECTION1_CURRENT.md](K1_FLOWS_SECTION1_CURRENT.md) · [K1_FLOWS_SECTION2_CURRENT.md](K1_FLOWS_SECTION2_CURRENT.md) · [K1_FLOWS_SECTION3_CURRENT.md](K1_FLOWS_SECTION3_CURRENT.md) · [K1_FLOWS_SECTION4_CURRENT.md](K1_FLOWS_SECTION4_CURRENT.md)
**Verification basis:** subagent code-scan with **mandatory kernel-side wiring inspection** (`k1/kernel/service.py`, `k1/planner/factory.py`, `k1/concierge/factory.py`)
**Date:** 2026-04-27

Legend: ✅ wired · ⚠️ partial · ❌ missing · 🔵 stub-only / aspirational

---

## Section 5 Status Summary

| F# | Name | Status | One-line gap |
|---|---|---|---|
| F53 | Stage 1 Sketch Plan | ✅ wired | `SketchService` (not `PlannerAgent.sketch()`); 6-round agentic tool loop; LLM via `LLMGatewayAdapter`; **but unreachable from FSM HIGH path — see critical gap** |
| F54 | Stage 2 Expand with Tools | ✅ wired | `ExpandService` separate stage; `IFabricRetrievalPort` capability lookup; deterministic enrichment + arbiter revise loop |
| F55 | Stage 3 Validation | ✅ wired | `ValidateService` (not `PlanValidator`); true hybrid — Phase 1 Kahn's deterministic gate + Phase 2 single LLM arbiter (STRUCTURED) |
| F56 | Stage 4 Commit to K0 | ⚠️ partial | `CommitService` assembles `CommittedPlan` + emits `TOPIC_PLAN_READY`; **WAL persists via `SinkBridgeAdapter` outbox; K0 P05 undeployed (MS-3)** |
| F57 | Requirement Clarification HIL | ✅ wired | Planner-side `HILCoordinator.request_clarification()`; LLM-formed question; max 2 rounds, 60s timeout |
| F58 | Plan Approval HIL (AMBER/RED) | ✅ wired | `ValidateService._check_and_run_hil_approval()` triggered when side-effect step has `safety_band_min != GREEN` or arbiter `safety_assessment="caution"`; 120s timeout |
| F59 | Execution Monitoring HIL | ⚠️ partial | Concierge `HILCoordinator` is **reactive on `TOPIC_TASK_SUSPENDED`, not continuous DAG monitoring**; silent step failures get no HIL |

### Headline counts

| Status | Count | Flows |
|---|---|---|
| ✅ wired | **5** | F53, F54, F55, F57, F58 |
| ⚠️ partial | **2** | F56, F59 |
| ❌ missing | **0** | — |

---

## 🚨 Critical Finding — Planner Pipeline is Unreachable from FSM HIGH Path

`ConciergeController._route_via_orchestrator()` at [k1/concierge/fsm/controller.py#L2114](../../k1/concierge/fsm/controller.py#L2114) explicitly states:

> "HIGH tier → **PassthroughPlannerStub** → route via MEDIUM path (real Planner is a later milestone)"

**Current behavior:** the FSM stubs HIGH-tier dispatch by wrapping the intent as a **1-step pre-built `CommittedPlan`** and routing it through the MEDIUM path — bypassing the entire F53–F56 pipeline.

**State of the actual Planner:** F53–F56 are **fully implemented and kernel-wired**:

- `PlannerFactory.create_production()` invoked at [k1/kernel/service.py#L1083](../../k1/kernel/service.py#L1083) with all 7 ports (`llm_port`, `fabric_port`, `state_port`, `bridge_port`, `delta_port`, `event_port`, `mailbox_port`)
- S6b cross-wires real `PlannerAdapter` → `Orchestrator._planner_port` at [service.py#L1105-L1109](../../k1/kernel/service.py#L1105)
- `PlannerAgent` is **Tier-1 shared** (single instance, `asyncio.Lock` serializes plans)
- `PlannerAgent.start()` spawned as background task at [service.py#L1117](../../k1/kernel/service.py#L1117)

**Reachability today:** F53–F56 fire only if `Orchestrator` directly enqueues a `PlanRequest` onto `PlannerAgent.mailbox`. The Concierge FSM never does that for HIGH-tier — it stubs.

**Implication:** every measurement and audit of "Planner pipeline" is currently observing the **stub path**. To exercise the real planner end-to-end you must either:

1. Replace `PassthroughPlannerStub` with a real planner-mailbox enqueue in `_route_via_orchestrator()`
2. Have Orchestrator MED dispatch detect "needs planning" and route to PlannerAgent

This is the single most important fact in §5.

---

## F53 — Stage 1 Sketch Plan ✅ wired (class-name drift: `SketchService`)

| Item | Anchor |
|---|---|
| Class | `SketchService` (NOT `PlannerAgent.sketch()`) |
| Entry | [k1/planner/stages/sketch_service.py#L954](../../k1/planner/stages/sketch_service.py#L954) `SketchService.execute()` |
| Invoked by | `PipelineController._run_sketch()` ← `PlannerAgent` mailbox dequeue loop |
| LLM port | `ILLMPort` via `LLMGatewayAdapter` → `ModelHubRequestBus` → ModelHub |
| Agentic loop | `_MAX_TOOL_ROUNDS = 6`; tools: `discover_capabilities`, `query_session_context`, `recall_long_term_memory`, `find_prompts` |
| Output | `SketchResult` with `rough_steps`, `rationale`, `needs_clarification` |
| Micro path | `SketchService.micro_execute()` at [sketch_service.py#L1077](../../k1/planner/stages/sketch_service.py#L1077) — no HIL, reduced budget |
| Sharing | **Tier-1 shared** (one plan at a time via `asyncio.Lock`) |

**Caveat (V1 vs V2):** `LLMGatewayAdapter` V1 note at [k1/planner/adapters/llm_gateway_adapter.py#L9](../../k1/planner/adapters/llm_gateway_adapter.py#L9) — "V1 runs `TestLLMAdapter` in ALL environments; `LLMGatewayAdapter` is the V2 production path when Model Hub is live." Verify `model_mode="hub"` actually swaps in the real adapter.

---

## F54 — Stage 2 Expand with Tools ✅ wired

| Item | Anchor |
|---|---|
| Class | `ExpandService` |
| Entry | [k1/planner/stages/expand_service.py#L1130](../../k1/planner/stages/expand_service.py#L1130) `ExpandService.execute()` |
| Capability lookup | `IFabricRetrievalPort` wired via `FabricRetrievalAdapter` at [k1/kernel/service.py#L1070](../../k1/kernel/service.py#L1070) |
| Fabric tools | `discover_capabilities`, `get_capability_schema`, `find_prompts`, `query_session_context` |
| LLM call count | up to `_MAX_TOOL_ROUNDS = 6` + 1 final structured call |
| Post-LLM enrichment | Deterministic fill of 6 infrastructure fields from `CapabilityContract` metadata |
| Arbiter revise loop | `arbiter_feedback` param supports VALIDATE → re-EXPAND |
| Fallback | `_build_degraded_plan()` if both attempts fail |
| HIL | None at this stage (`ExpandService` docs: "does NOT hold HILCoordinator") |

**Delta:** none significant; `ExpandedPlan` type matches docs.

---

## F55 — Stage 3 Validation ✅ wired (true hybrid)

| Item | Anchor |
|---|---|
| Class | `ValidateService` (NOT `PlanValidator`) |
| Entry | [k1/planner/stages/validate_service.py#L301](../../k1/planner/stages/validate_service.py#L301) `ValidateService.execute()` |
| Phase 1 (deterministic) | Kahn's DAG cycle detection + capability existence via `IFabricRetrievalPort` + structural checks + inter-step ref validation — **no LLM** |
| Phase 2 (LLM) | Single LLM arbiter call (`STRUCTURED` capability, temp=0.1, max 512 tokens) — **not** an agentic loop |
| Hybrid gate | Phase 1 fail → immediate reject, no LLM cost |
| Output schema | `VALIDATE_VERDICT_SCHEMA`: `{status, reasons, coherence_score, safety_assessment, completeness}` |
| HIL hook | `_check_and_run_hil_approval()` only when `verdict.status == APPROVED` |
| Revise loop | `arbiter_feedback` passed back to `ExpandService.execute()` |

**Delta:** doc name `PlanValidator` → code `ValidateService`. Architecture genuinely hybrid (correct per docs).

---

## F56 — Stage 4 Commit to K0 ⚠️ partial (K0 undeployed)

| Item | Anchor |
|---|---|
| Class | `CommitService` |
| Entry | `CommitService.execute()` in [k1/planner/stages/commit_service.py](../../k1/planner/stages/commit_service.py) |
| Output | `CommittedPlan` (11 fields incl. uuid, timestamps, steps, critical-path duration) |
| LLM-free | Enforced (PLAN-03) — no `ILLMPort` param, no LLM import |
| WAL persistence | `IBridgePort.persist_plan()` |
| Actual bridge | Kernel wires `SinkBridgeAdapter(outbox_path=...)` — **fire-and-forget outbox; no live K0 P05** |
| Plan delivery | Publishes `TOPIC_PLAN_READY` event → Orchestrator picks up via `PlannerAdapter` event subscription |
| K0 P05 | **Not connected** — K0 undeployed (MS-3); plan lands in `SinkBridgeAdapter` outbox or silently dropped by `OfflineBridgeAdapter` |

**Gap:** docs say "CommittedPlan → K0 P05." Today it's `CommittedPlan` → event bus + outbox file. Once K0 P05 ships, `BridgeAdapter.persist_plan()` needs an active K0-side consumer; otherwise outbox grows unbounded.

---

## F57 — Requirement Clarification HIL ✅ wired

| Item | Anchor |
|---|---|
| Class | Planner-side `HILCoordinator` at [k1/planner/services/hil_coordinator.py](../../k1/planner/services/hil_coordinator.py) |
| Trigger | `SketchService.execute()` calls `_execute_attempt(allow_hil=True)`; if LLM sets `needs_clarification=true` → `HILCoordinator.request_clarification()` |
| Event flow | Publishes `TOPIC_HIL_CLARIFICATION` via `IEventPort`; awaits `TOPIC_HIL_CLARIFICATION_RESP` |
| Round budget | PLAN-10: max 2 clarification rounds per plan, then best-effort proceeds |
| Timeout | 60s per clarification round |
| LLM question gen | `HILCoordinator` calls LLM (CHAT mode, 300 tokens) to formulate natural-language question |
| LLM failure | Skip HIL, proceed best-effort |
| Micro-replan | `micro_execute()` always passes `allow_hil=False` |

**Delta:** none. Matches documented design.

**Note:** This is the **planner-side `HILCoordinator`** — distinct from the concierge-side `HILCoordinator` used in §4 F49 / §5 F59. Two classes, same name, different files.

---

## F58 — Plan Approval HIL ✅ wired

| Item | Anchor |
|---|---|
| Trigger | `ValidateService._check_and_run_hil_approval()` at [k1/planner/stages/validate_service.py#L1091](../../k1/planner/stages/validate_service.py#L1091) |
| Conditions | Side-effect steps exist **AND** (`safety_band_min != GREEN` OR arbiter `safety_assessment=="caution"`) |
| Auto-approve | All side-effect steps `safety_band_min in ("GREEN","green")` AND arbiter `safety_assessment=="safe"` → skip HIL |
| HIL call | `self._hil_coord.request_approval(request_id, plan_summary, side_effects, safety_assessment, estimated_duration_ms)` |
| Safety field | `step.safety_band_min` on `PlanStep`; arbiter `safety_assessment` from `VALIDATE_VERDICT_SCHEMA` |
| Timeout | `_HIL_APPROVAL_TIMEOUT_S = 120` |
| Micro-replan | `micro_execute()` skips HIL entirely |

**Delta:** docs say "AMBER/RED safety band" — code uses `safety_band_min != GREEN` (same concept, informal labels).

---

## F59 — Execution Monitoring HIL ⚠️ partial (reactive only)

| Item | Anchor |
|---|---|
| Component | Concierge-side `HILCoordinator` at [k1/concierge/protocols/hitl_coordinator.py](../../k1/concierge/protocols/hitl_coordinator.py) |
| FSM attachment | `ConciergeController.set_hitl_coordinator()` at [k1/concierge/fsm/controller.py#L528](../../k1/concierge/fsm/controller.py#L528) |
| Activation trigger | `_on_task_suspended()` at [controller.py#L2716](../../k1/concierge/fsm/controller.py#L2716) — fires only on `TOPIC_TASK_SUSPENDED` event from Back/Orchestrator |
| Suspension limit | `HILCoordinator.get_hil_count()` + `_config.max_rounds` enforced at [controller.py#L2755-L2780](../../k1/concierge/fsm/controller.py#L2755) |
| Overrun | `hil_count > max_rounds` → mark complete with `max_hil_reached=True`, bypass HIL |
| `_on_dag_completed` | At [controller.py#L2228](../../k1/concierge/fsm/controller.py#L2228) — normalizes `dag.completed` → `task.complete.v1` |
| DAG monitoring | **Not continuous.** No polling/supervision loop. Silent step failures (non-suspension) get no HIL |

**Gap:** docs imply active per-step DAG monitoring. Reality is **event-reactive** — only when Back/Orchestrator emits `task.suspended.v1` does HIL kick in. If a `DAGExecutor` step fails without raising suspension, F59 never fires.

---

## Cross-cutting findings

1. **Planner pipeline (F53–F56) is fully implemented and kernel-wired but currently bypassed by FSM `PassthroughPlannerStub`.** This is the single most important §5 fact. The work is done; the integration toggle isn't flipped.
2. **Class-name drift, consistent pattern:** Doc → Code:
   - `PlannerAgent.sketch()` → `SketchService.execute()`
   - `PlanValidator` → `ValidateService`
   - `PlannerHIL` → planner-side `HILCoordinator`
   - "AMBER/RED" → `safety_band_min != GREEN`
   - "K0 P05" → `SinkBridgeAdapter` outbox + `TOPIC_PLAN_READY` event
3. **Two classes both named `HILCoordinator`:** planner-side at `k1/planner/services/hil_coordinator.py` (F57/F58) and concierge-side at `k1/concierge/protocols/hitl_coordinator.py` (F49 from §4 / F59 here). They serve different purposes — the planner one handles clarification + plan-approval; the concierge one handles task suspension/resume during execution. Naming collision is a future bug-magnet.
4. **`LLMGatewayAdapter` V1 still defaults to `TestLLMAdapter`.** Per code comment: V2 production swap-in happens when ModelHub is live. Verify `model_mode="hub"` actually exercises `LLMGatewayAdapter`, not `TestLLMAdapter`, in the kernel smoke driver.
5. **F59 is reactive, not active.** No background DAG-step supervisor loop. If telemetry/audit ever needs "planner monitoring" for slow/stalled steps, that's greenfield.
6. **Tier-1 shared `PlannerAgent` with `asyncio.Lock`.** Plans are serialized — no per-session concurrency. Important to know for load planning; unsurprising for HIGH tier.
7. **K0 commit (F56) is outbox-only.** Once K0 P05 ships and `KernelQueryPort` (HTTP) replaces `SinkBridgeAdapter`, plans will start landing live. Until then `data/` outbox accumulates.

---

## Recommended next actions (priority order)

| Pri | Action | Touches | Source |
|---|---|---|---|
| P0 | Replace `PassthroughPlannerStub` in `_route_via_orchestrator()` (HIGH path) with real `PlannerAgent.mailbox` enqueue — unblocks F53–F58 end-to-end | F53, F54, F55, F58 | new |
| P1 | Verify `LLMGatewayAdapter` (V2) actually engages when `model_mode="hub"` — not silently falling back to `TestLLMAdapter` | F53, F54, F55 | new |
| P1 | Add a kernel smoke test that exercises a HIGH-tier prompt end-to-end through the real planner pipeline (post-P0 fix) | F53–F58 | new |
| P2 | Decide F59 strategy: build active DAG supervisor (poll/heartbeat-based) OR amend doc to declare "reactive on suspension only" | F59 | new |
| P2 | Wait on K0 MS-3 P05 for F56 commit; meanwhile add outbox consumer monitoring to detect unbounded growth | F56 | unchanged |
| P3 | Rename in K1_FLOWS.md: `PlannerAgent.sketch()` → `SketchService`, `PlanValidator` → `ValidateService`, `PlannerHIL` → planner-side `HILCoordinator`, "AMBER/RED" → `safety_band_min != GREEN`, "K0 P05" → outbox + event-bus delivery | doc | new |
| P3 | Resolve `HILCoordinator` naming collision (planner vs concierge) — rename one to `PlannerHILCoordinator` / `ConciergeHILCoordinator` | F57, F58, F59 | new |
| P3 | Document that `PlannerAgent` is Tier-1 shared with `asyncio.Lock` (single concurrent plan) — important for HIGH-tier capacity planning | docs | new |

---

**Section 5 complete. Next:** §6 Sub-Agent Flows (F60–F65) — 6 flows. Sub-agent execution model, capability inheritance, and result aggregation.
