# Concierge Micro-Diagram Set (Hyper-Detailed, End-to-End)

Source of truth used: `d:\familyos\k1\concierge\concierge.mmd` (read fully end-to-end before decomposition).

This set provides a **minimum 12 diagrams** with strict scope separation so each one is readable while preserving full pipeline fidelity.

It now also includes a **real-life step-by-step walkthrough** diagram for operational understanding.

## Enhancement pass applied (from `architecture_diagrams/k1/K1_FLOWS.md`)

All 12 diagrams were enhanced after a full end-to-end read of `K1_FLOWS.md` (F01-F154), with focus on concierge-relevant additions:

- LLM control plane additions: prompt resolution/injection/compilation, output 3-tier validation, fallback strategy.
- Event bus deepening: WFQ priorities, mailbox routing, and backpressure behavior.
- HIL deepening: planner approval/clarification loops, orchestrator intervention responses, sub-agent mediated loop.
- Experience and empathy integration: periodic turn-based updates (`%20/%25/%30`) and cognitive-capacity/rhythm hooks.
- Observability and health: cognitive trace flow, per-turn telemetry rollups, provider health state effects on routing.

## Diagram inventory

1. `01_concierge_context_and_boundaries.mmd`
   - Concierge boundary, internal services, ports, and all external systems.

2. `02_fsm_state_machine_and_transition_rules.mmd`
   - Full state graph + interruptibility + crisis override + core invariants.

3. `03_acking_ultrabert_phase1_deterministic_pipeline.mmd`
   - UltraBERT heads, safety-first gate, complexity routing, uncertainty loop, Phase-1 writes.

4. `04_clarifying_entropy_minimization_and_hil_detection.mmd`
   - Clarification question planning + pending/HIL detection + response routing.

5. `05_dispatching_low_tier_llm_tool_loop_execution.mmd`
   - LOW-tier LLM tool loop where tool calls execute action path via Fabric.

6. `06_dispatching_medium_high_orchestrator_planner_fabric_path.mmd`
   - MED/HIGH envelope flow: Orchestrator + Planner + DAG + degradation cascade.

7. `07_companioning_progressing_delivering_output_contracts.mmd`
   - Companion/progress/final output sequencing + turn.complete emissions.

8. `08_interrupt_handling_and_hil_roundtrip_routing.mmd`
   - Interrupt boundary checks + abbreviated turn end + HIL roundtrip map.

9. `09_tool_dispatcher_allowlists_schema_gates_mutation_guard.mmd`
   - Tool gating stack (state/tier/safety/schema/budget) + mutation boundary.

10. `10_k1_bus_lanes_topics_publish_subscribe_map.mmd`
    - One physical K1 bus, two logical lanes, topic families, publishers/subscribers.

11. `11_sessionstate_single_writer_two_phase_write_paths.mmd`
    - Deterministic phase-1 writes + phase-2 cognitive writes through MutationGuard.

12. `12_resilience_circuit_breakers_error_recovery_degradation.mmd`
    - CB matrix + RECOVERABLE/DEGRADED/TERMINAL handling + canned fallback ladder.

13. `13_concierge_real_life_step_by_step_how_it_works.mmd` - Real-life walkthrough (example user request, timing, uncertainty/clarifying branch, LOW vs MED/HIGH execution, HIL loop, validation, degradation, turn close).

## Coverage guarantee against source concierge

- FSM: LISTENING, ACKING, CLARIFYING, DISPATCHING, COMPANIONING, PROGRESSING, DELIVERING, INTERRUPT_HANDLING.
- Two-phase write model: UltraBERT deterministic phase + LLM cognitive tool phase.
- LLM-tool action boundary: side effects only via validated tool calls.
- LOW/MED/HIGH and CRISIS behaviors with degradation policy.
- HIL request/response routing and pending clarification correlation.
- K1 Bus model: one physical bus, event lane (`k1.*`) and delta lane (`k1.*.delta.v1`).
- Error handling and circuit-breaker driven fallbacks.

## Additional K1_FLOWS coverage now embedded

- F107-F111: LLM inference pattern alignment for Concierge/Planner/Validator/Proactive decisioning.
- F112-F127: Experience + rhythm/empathy + anticipation/speculation constraints wired into state and write-path diagrams.
- F132-F137: Event bus event taxonomy, WFQ scheduling, mailbox router semantics.
- F138-F141: HIL bidirectional loops (concierge/planner/sub-agents/orchestrator).
- F142-F144: tracing, metrics aggregation, provider health orchestration.
- F145-F154: prompt/schema control plane and validation fallback policy.

## Notes

- Folder name kept exactly as requested: `conceriege_flows`.
- If you want, next step can generate an additional **"drill-down pack"** (another 8-12 diagrams) for only:
  - Temporal/spatial inference internals,
  - Prompt-system and output-validation internals,
  - Lifecycle + crash recovery with lock_version semantics.
