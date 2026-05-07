# 12 — Test Coverage Map (K1 Concierge)

> Generated: 2026-04-04
> Source: `tests/k1/concierge/` (75 files), `tests/poc/` (1 file), in-source (2 files)

---

## 1. Aggregate Statistics

| Metric | Count |
|---|---|
| **Test files (tests/k1/concierge/)** | 75 |
| **  — Root directory** | 63 |
| **  — adapters/ subdirectory** | 5 |
| **  — ports/ subdirectory** | 6 |
| **POC test file (tests/poc/)** | 1 |
| **In-source test helpers (k1/concierge/llm/)** | 2 |
| **Total test classes** | 548 |
| **Total test functions** | 2,679 |
| **Total test lines** | 38,286 |

---

## 2. Milestone Naming Convention

Tests follow a `test_mXX_eYY_*.py` naming scheme where:

| Prefix | Milestone | Subsystem / Theme |
|---|---|---|
| `test_m00_*` | M00 | V3 conformance — full FSM integration invariants |
| `test_m01_*` | M01 | Builders, event validator, ledger replay, topics |
| `test_m02_*` | M02 | Guard matrix, dead letter, response-final, task state/artifacts |
| `test_m03_*` | M03 | Bus/port compliance, resume context, parallel safety, shared utils, validator, test adapter |
| `test_m04_*` | M04 | Session-state binding, write path, session bundle, prompt-SS |
| `test_m05_*` | M05 | Arbiter (interrupt/intent arbitration), interrupt paths, normal paths, multi-device |
| `test_m08_*` | M08 | Weave subsystem — signal, decision, dynamic batch, policy integration |
| `test_m09_*` | M09 | Recovery — cancel, suspension, HITL, history/pending, task state, orchestrator |
| `test_m10_*` | M10 | UltraBERT pipeline, SS writes, tier routing, adapter, extra heads, task dispatch/receiver |
| `test_m11_*` | M11 | Delta subsystem — session delta, applicator, writer registry, overflow, observability |
| `test_m15_*` | M15 | Experience layer — emotional processor, affective mirror, narrative weaver, etc. |
| `test_c1_*` | C1 | Port protocol compliance (cross-cutting) |

**Note:** M06, M07, M12–M14 have NO test files in `tests/k1/concierge/` (but do exist in `tests/poc/`).

The `eYY` suffix is the **epic number** within a milestone (e.g., `test_m02_e21` = Milestone 2, Epic 2.1).

---

## 3. Complete File Inventory

### 3.1 Root Directory (63 files)

| # | File | Classes | Funcs | Lines | Subsystem Tested |
|---|---|---|---|---|---|
| 1 | `test_c1_port_protocols.py` | 11 | 35 | 376 | Port protocol compliance (all 5 adapter pairs) |
| 2 | `test_calendar_tools.py` | 8 | 26 | 471 | Tools — calendar (create event, schedule reminder, trip summary) |
| 3 | `test_contract_converter.py` | 2 | 30 | 178 | Fabric — POC dict-to-CapabilityContract converter |
| 4 | `test_fabric_port.py` | 3 | 10 | 108 | Fabric — IFabricPort protocol signatures |
| 5 | `test_fabric_wiring_e2e.py` | 4 | 16 | 232 | Fabric — end-to-end registration, execute, batch, discovery |
| 6 | `test_family_tools.py` | 9 | 30 | 410 | Tools — family (messaging, check-in, member info) |
| 7 | `test_gap_detection_scenarios.py` | 8 | 13 | 334 | Tools — gap detection & clarification generation |
| 8 | `test_m00_v3_conformance.py` | 17 | 55 | 1,992 | Full V3 FSM conformance (interrupt, cancel, weave, dedup, routing) |
| 9 | `test_m01_builders.py` | 2 | 9 | 147 | Bus — builders registry & output |
| 10 | `test_m01_event_validator.py` | 10 | 31 | 464 | Events — schema registry, event validation, HITL wiring |
| 11 | `test_m01_ledger_replay.py` | 7 | 38 | 897 | Ledger — store, writer, projections, replay, controller integration |
| 12 | `test_m01_topics.py` | 4 | 17 | 111 | Bus — topic counts, timing, priority mapping, subscriptions |
| 13 | `test_m02_e21_guard_matrix.py` | 10 | 54 | 583 | FSM — guard table completeness, dispatch, transitions |
| 14 | `test_m02_e22_dead_letter.py` | 10 | 48 | 647 | FSM — dead letter topic, payload schema, consumer, overflow |
| 15 | `test_m02_e23_response_final.py` | 10 | 57 | 772 | FSM — response-final truth table, idempotency, finalize turn |
| 16 | `test_m02_e24_conformance.py` | 8 | 47 | 1,095 | FSM — conformance (guard matrix, dead letter, interrupt, cancel, HITL, weave) |
| 17 | `test_m02_task_artifacts.py` | 9 | 34 | 362 | Session state — task artifacts section |
| 18 | `test_m02_task_state.py` | 9 | 54 | 402 | Session state — task state section |
| 19 | `test_m03_bus_port_compliance.py` | 9 | 45 | 457 | Bus — IBus, IMailbox, IMailboxRouter, middleware, setup |
| 20 | `test_m03_e33_resume_context.py` | 7 | 31 | 649 | Protocols — suspension manager, resume handler, cleanup |
| 21 | `test_m03_e34_parallel_safety.py` | 8 | 33 | 634 | Task — classify_tool_batch, parallel safety config, react loop |
| 22 | `test_m03_e35_shared_utils.py` | 6 | 34 | 274 | Actors — shared utils (parse_payload, safe_get_section, never_cancel) |
| 23 | `test_m03_e36_conformance.py` | 4 | 24 | 864 | Actors — front emission ordering, back routing, cancel, parallel tools |
| 24 | `test_m03_test_adapter.py` | 7 | 26 | 438 | LLM — TestConciergeAdapter (protocol, responses, streaming, recording) |
| 25 | `test_m03_validator.py` | 8 | 28 | 529 | LLM — validator (tool allowlist, required params, type check) |
| 26 | `test_m04_e41_ss_binding.py` | 3 | 32 | 402 | FSM — task bridge rebind, control extension bind, SS binding |
| 27 | `test_m04_e42_write_path.py` | 9 | 33 | 581 | Session state — ToolContext write path (beliefs, scoreboard, etc.) |
| 28 | `test_m04_e43_session_bundle.py` | 5 | 20 | 562 | Tools — session bundle (batch mutations, idempotency, rejection) |
| 29 | `test_m04_e44_prompt_ss.py` | 16 | 67 | 750 | Prompt — SS section renderers, build_stage8, tone/style hints |
| 30 | `test_m05_arbiter.py` | 11 | 75 | 859 | FSM — arbiter (decision, classify, cancel target, config) |
| 31 | `test_m05_e52_interrupt_paths.py` | 6 | 45 | 650 | FSM — interrupt paths (parallel-new, cancel, modify, defer) |
| 32 | `test_m05_e53_normal_paths.py` | 5 | 36 | 537 | FSM — normal paths (listening, clarifying, routing metadata) |
| 33 | `test_m05_e54_multi_device.py` | 8 | 48 | 830 | FSM — multi-device (tracking, conflict, HITL dedup, precedence) |
| 34 | `test_m08_e81_weave_signal.py` | 8 | 58 | 601 | Weave — signal dataclass, activity tracker, urgency, emotional gate |
| 35 | `test_m08_e82_weave_decision.py` | 7 | 71 | 854 | Weave — decision enum, policy, config, guard table, topic wiring |
| 36 | `test_m08_e83_dynamic_batch.py` | 9 | 82 | 741 | Weave — schedule flush, digest, domain extraction, templates |
| 37 | `test_m08_e84_policy_integration.py` | 9 | 88 | 1,038 | Weave — routing, re-eval, fallback, metrics, queue, integration |
| 38 | `test_m09_e91_cancel_recovery.py` | 4 | 17 | 266 | Recovery — cancel handler ledger writes, state projection |
| 39 | `test_m09_e92_suspension_recovery.py` | 3 | 17 | 299 | Recovery — suspension manager ledger writes, rebuild |
| 40 | `test_m09_e93_hitl_recovery.py` | 4 | 19 | 387 | Recovery — HITL coordinator ledger writes, L2 defense |
| 41 | `test_m09_e94_history_pending.py` | 3 | 12 | 265 | Recovery — active task IDs, FSM turn state ledger |
| 42 | `test_m09_e94_task_state.py` | 3 | 19 | 286 | Recovery — task bridge ledger writes, crash recovery |
| 43 | `test_m09_e95_recovery.py` | 5 | 21 | 494 | Recovery — crash recovery orchestrator, FSM derivation, full E2E |
| 44 | `test_m10_e101_ultrabert_pipeline.py` | 6 | 39 | 426 | Phase1 — UltraBERT mapping, extra heads, complexity, degradation |
| 45 | `test_m10_e102_ss_writes.py` | 6 | 24 | 413 | Phase1 — control section writes, scoreboard, affective, resilience |
| 46 | `test_m10_e103_tier_routing.py` | 4 | 13 | 268 | Phase1 — auto-tier dispatch, crisis short-circuit, observability |
| 47 | `test_m10_e104_adapter.py` | 8 | 28 | 346 | Phase1 — UltraBERT adapter (mapping, cache, singleton, warmup) |
| 48 | `test_m10_e105_extra_heads.py` | 5 | 30 | 450 | Phase1 — temporal head, relation head, embedding head, bootstrap |
| 49 | `test_m10_epics_7_8_9.py` | 16 | 65 | 1,055 | Task — dispatch, receiver, intent result, bundled plan, package |
| 50 | `test_m11_epics_1_2_3.py` | 15 | 74 | 1,000 | Delta — session delta, topics, emit, aggregator, batching |
| 51 | `test_m11_epics_4_5_6.py` | 18 | 101 | 1,021 | Delta — applicator, writer registry, snapshot reader, cross-actor |
| 52 | `test_m11_epics_7_8_9.py` | 17 | 79 | 1,170 | Delta — overflow handler, eviction, E2E pipelines |
| 53 | `test_m11_obs_e111.py` | 11 | 98 | 1,064 | Obs — metric envelope, collector, sliding window, aggregator, bus topics |
| 54 | `test_m11_obs_e112.py` | 8 | 55 | 962 | Obs — exit path, react loop metrics, front/back metrics, budget |
| 55 | `test_m15_experience_layer.py` | 11 | 171 | 1,492 | Experience — emotional processor, affective mirror, narrative weaver, proactive, rhythm, orchestrator |
| 56 | `test_model_hub_bridge.py` | 11 | 24 | 467 | LLM — ModelHubBridge protocol, chat/tool/structured/reason round-trip |
| 57 | `test_model_hub_ports.py` | 10 | 21 | 178 | LLM — IModelHubPort and supporting port signatures |
| 58 | `test_model_hub_types.py` | 26 | 40 | 643 | LLM — all type dataclasses (payloads, responses, chunks, model info) |
| 59 | `test_monitor_tools.py` | 13 | 53 | 841 | Tools — monitor (weather forecast, background monitor, alerts) |
| 60 | `test_poc_bridge_adapter.py` | 5 | 19 | 227 | Fabric — POC bridge adapter (structural, availability, send/query/route) |
| 61 | `test_tool_fabric_live.py` | 6 | 17 | 306 | Tools — fabric live (discover, invoke, batch, spawn, workflow) |
| 62 | `test_tool_fabric_port_wiring.py` | 6 | 29 | 499 | Tools — fabric port wiring (fabric port integration, HITL blocking) |
| 63 | `test_travel_tools.py` | 12 | 29 | 495 | Tools — travel (accommodations, restaurants, routes, spa, bookings) |

**Note:** `test_two_way_concierge.py` (4 classes, 12 funcs, 335 lines) exists at root testing two-way concierge (task queue, notifications, registry, concurrent ops). It duplicates the POC file.

### 3.2 adapters/ Subdirectory (5 files)

| # | File | Classes | Funcs | Lines | Subsystem Tested |
|---|---|---|---|---|---|
| 1 | `test_null_bridge_write.py` | 2 | 6 | 47 | Null adapter — IBridgeWritePort no-op |
| 2 | `test_null_delta_bus.py` | 2 | 3 | 26 | Null adapter — IDeltaBusPort no-op |
| 3 | `test_null_event_subscription.py` | 2 | 5 | 41 | Null adapter — IEventSubscriptionPort no-op |
| 4 | `test_null_state_reader.py` | 2 | 5 | 37 | Null adapter — ISessionStateReader no-op |
| 5 | `test_snapshot_state_read.py` | 2 | 8 | 96 | Adapter — snapshot-based IStateReadPort |

### 3.3 ports/ Subdirectory (6 files)

| # | File | Classes | Funcs | Lines | Subsystem Tested |
|---|---|---|---|---|---|
| 1 | `test_dispatch_adapter.py` | 2 | 5 | 71 | Port — IDispatchPort (mock + fabric) |
| 2 | `test_input_adapter.py` | 2 | 6 | 86 | Port — IInputPort (test + bus) |
| 3 | `test_memory_adapter.py` | 2 | 6 | 87 | Port — IMemoryPort (mock + recall) |
| 4 | `test_output_adapter.py` | 2 | 7 | 90 | Port — IOutputPort (test + bus) |
| 5 | `test_port_protocols.py` | 2 | 16 | 151 | Port — all protocol isinstance checks (16 adapters) |
| 6 | `test_state_adapter.py` | 2 | 6 | 68 | Port — IStatePort (in-memory + SSM) |

### 3.4 POC Test (1 file)

| # | File | Classes | Funcs | Lines | Subsystem Tested |
|---|---|---|---|---|---|
| 1 | `tests/poc/test_two_way_concierge.py` | 4 | 12 | 335 | POC background tasks, notifications, concurrency |

### 3.5 In-Source Test Helpers (NOT pytest tests — no `test_` functions)

| # | File | Classes | Purpose |
|---|---|---|---|
| 1 | `k1/concierge/llm/test_adapter.py` | `TestConciergeAdapter` | Deterministic LLM adapter for tests (no real API calls) |
| 2 | `k1/concierge/llm/test_model_hub_bridge.py` | `TestModelHubBridge` | IModelHubPort wrapper around TestConciergeAdapter |

These are **test infrastructure** — imported by test files but contain zero `test_*` functions themselves.

---

## 4. Coverage by Subsystem

### 4.1 Source Modules → Test Mapping

| Source Module | Test File(s) | Coverage Level |
|---|---|---|
| **actors/** | | |
| `actors/back.py` | `test_m03_e36_conformance`, `test_m00_v3_conformance` | ✅ Covered (via FSM conformance) |
| `actors/back_pool.py` | `test_m10_epics_7_8_9` (task dispatch/receiver) | ✅ Covered |
| `actors/back_router.py` | `test_m03_e36_conformance` | ✅ Covered |
| `actors/front.py` | `test_m03_e36_conformance`, `test_m00_v3_conformance` | ✅ Covered |
| `actors/ready_queue.py` | `test_m10_epics_7_8_9` | ✅ Covered |
| `actors/shared.py` | `test_m03_e35_shared_utils` | ✅ Covered (34 funcs) |
| **adapters/** | | |
| `adapters/bus_input.py` | `ports/test_input_adapter`, `test_c1_port_protocols` | ✅ Covered |
| `adapters/bus_output.py` | `ports/test_output_adapter`, `test_c1_port_protocols` | ✅ Covered |
| `adapters/fabric_dispatch.py` | `ports/test_dispatch_adapter`, `test_c1_port_protocols` | ✅ Covered |
| `adapters/hub_llm.py` | `test_model_hub_bridge` | ✅ Covered |
| `adapters/local_delta.py` | `adapters/test_null_delta_bus` (null path) | ⚠️ Partial (no live delta test) |
| `adapters/null_bridge_write.py` | `adapters/test_null_bridge_write` | ✅ Covered |
| `adapters/null_delta_bus.py` | `adapters/test_null_delta_bus` | ✅ Covered |
| `adapters/null_event_subscription.py` | `adapters/test_null_event_subscription` | ✅ Covered |
| `adapters/null_state_reader.py` | `adapters/test_null_state_reader` | ✅ Covered |
| `adapters/recall_memory.py` | `ports/test_memory_adapter` | ✅ Covered |
| `adapters/snapshot_state_read.py` | `adapters/test_snapshot_state_read` | ✅ Covered |
| `adapters/ssm_state.py` | `ports/test_state_adapter` | ✅ Covered |
| `adapters/test_classification.py` | `ports/test_port_protocols` (isinstance) | ✅ Covered |
| `adapters/test_delta.py` | `ports/test_port_protocols` | ⚠️ Only isinstance check |
| `adapters/test_dispatch.py` | `ports/test_dispatch_adapter`, `test_c1_port_protocols` | ✅ Covered |
| `adapters/test_input.py` | `ports/test_input_adapter`, `test_c1_port_protocols` | ✅ Covered |
| `adapters/test_llm.py` | `test_m03_test_adapter` | ✅ Covered (26 funcs) |
| `adapters/test_memory.py` | `ports/test_memory_adapter`, `test_c1_port_protocols` | ✅ Covered |
| `adapters/test_output.py` | `ports/test_output_adapter`, `test_c1_port_protocols` | ✅ Covered |
| `adapters/test_state.py` | `ports/test_state_adapter`, `test_c1_port_protocols` | ✅ Covered |
| `adapters/ultrabert_classification.py` | `test_m10_e104_adapter`, `ports/test_port_protocols` | ✅ Covered |
| **bus/** | | |
| `bus/builders.py` | `test_m01_builders` | ✅ Covered |
| `bus/deserialize.py` | — | ❌ No dedicated test |
| `bus/setup.py` | `test_m03_bus_port_compliance` | ✅ Covered |
| `bus/topics.py` | `test_m01_topics` | ✅ Covered |
| **compression/** | | |
| `compression/episodic_compressor.py` | — | ❌ No test |
| **config/** | | |
| `config/loader.py` | Tested indirectly (many files use config) | ⚠️ Indirect only |
| **delta/** | | |
| `delta/aggregator.py` | `test_m11_epics_1_2_3` | ✅ Covered |
| `delta/applicator.py` | `test_m11_epics_4_5_6` | ✅ Covered |
| `delta/emitters.py` | `test_m11_epics_1_2_3` | ✅ Covered |
| `delta/overflow.py` | `test_m11_epics_7_8_9` | ✅ Covered |
| `delta/session_delta.py` | `test_m11_epics_1_2_3` | ✅ Covered |
| `delta/snapshot_reader.py` | `test_m11_epics_4_5_6` | ✅ Covered |
| `delta/topics.py` | `test_m11_epics_1_2_3` | ✅ Covered |
| `delta/writer_registry.py` | `test_m11_epics_4_5_6` | ✅ Covered |
| **events/** | | |
| `events/base.py` | `test_m01_event_validator` | ✅ Covered |
| `events/conversation.py` | `test_m01_event_validator` | ✅ Covered |
| `events/hitl.py` | `test_m01_event_validator` | ✅ Covered |
| `events/mutation.py` | `test_m01_event_validator` | ✅ Covered |
| `events/pool.py` | `test_m01_event_validator` | ✅ Covered |
| `events/registry.py` | `test_m01_event_validator` | ✅ Covered |
| `events/task.py` | `test_m01_event_validator` | ✅ Covered |
| `events/validator.py` | `test_m01_event_validator` | ✅ Covered |
| `events/weave.py` | `test_m01_event_validator` | ✅ Covered |
| **experience/** | | |
| `experience/affective_mirror.py` | `test_m15_experience_layer` | ✅ Covered |
| `experience/anticipatory_responder.py` | `test_m15_experience_layer` | ✅ Covered |
| `experience/emotional_processor.py` | `test_m15_experience_layer` | ✅ Covered |
| `experience/layer.py` | `test_m15_experience_layer` | ✅ Covered |
| `experience/narrative_weaver.py` | `test_m15_experience_layer` | ✅ Covered |
| `experience/proactive_agent.py` | `test_m15_experience_layer` | ✅ Covered |
| `experience/rhythm_controller.py` | `test_m15_experience_layer` | ✅ Covered |
| **fabric/** | | |
| `fabric/capability_registry.py` | `test_fabric_wiring_e2e` | ✅ Covered |
| `fabric/contract_converter.py` | `test_contract_converter` | ✅ Covered |
| `fabric/demo_capabilities.py` | `test_fabric_wiring_e2e` | ✅ Covered (indirectly) |
| `fabric/family_capabilities.py` | `test_family_tools` | ✅ Covered (indirectly) |
| `fabric/poc_bridge_adapter.py` | `test_poc_bridge_adapter` | ✅ Covered |
| `fabric/ports.py` | `test_fabric_port` | ✅ Covered |
| `fabric/web_capabilities.py` | `test_fabric_wiring_e2e` | ✅ Covered (indirectly) |
| **fsm/** | | |
| `fsm/arbiter.py` | `test_m05_arbiter` | ✅ Covered (75 funcs) |
| `fsm/control_extension.py` | `test_m04_e41_ss_binding` | ✅ Covered |
| `fsm/controller.py` | `test_m00_v3_conformance`, `test_m02_e24_conformance` | ✅ Covered (heavy) |
| `fsm/dead_letter.py` | `test_m02_e22_dead_letter` | ✅ Covered |
| `fsm/dead_letter_consumer.py` | `test_m02_e22_dead_letter` | ✅ Covered |
| `fsm/errors.py` | — | ⚠️ No dedicated test (used by other modules) |
| `fsm/front_lock.py` | `test_m02_e23_response_final` | ✅ Covered |
| `fsm/history_writer.py` | `test_m01_ledger_replay` | ✅ Covered |
| `fsm/idempotency.py` | `test_m02_e23_response_final` | ✅ Covered |
| `fsm/interrupt_handler.py` | `test_m05_e52_interrupt_paths` | ✅ Covered |
| `fsm/phase1.py` | `test_m05_e53_normal_paths`, `test_m10_e101_ultrabert_pipeline` | ✅ Covered |
| `fsm/response_final_table.py` | `test_m02_e23_response_final` | ✅ Covered |
| `fsm/states.py` | `test_m02_e21_guard_matrix` | ✅ Covered |
| `fsm/task_bridge.py` | `test_m04_e41_ss_binding`, `test_m09_e94_task_state` | ✅ Covered |
| `fsm/transition_table.py` | `test_m02_e21_guard_matrix` | ✅ Covered |
| `fsm/turn_state.py` | `test_m09_e94_history_pending` | ✅ Covered |
| `fsm/ultrabert_adapter.py` | `test_m10_e104_adapter` | ✅ Covered |
| `fsm/ultrabert_phase1.py` | `test_m10_e101_ultrabert_pipeline` | ✅ Covered |
| **identity/** | | |
| `identity/dynamic_identity.py` | — | ❌ No test |
| **kernel/** | | |
| `kernel/bootstrap.py` | — | ❌ No dedicated test |
| `kernel/runner.py` | — | ❌ No dedicated test |
| **ledger/** | | |
| `ledger/projections.py` | `test_m01_ledger_replay`, `test_m09_*` | ✅ Covered |
| `ledger/recovery.py` | `test_m09_e95_recovery` | ✅ Covered |
| `ledger/store.py` | `test_m01_ledger_replay` | ✅ Covered |
| `ledger/writer.py` | `test_m01_ledger_replay` | ✅ Covered |
| **llm/** | | |
| `llm/gemini_adapter.py` | — | ❌ No test (live LLM adapter) |
| `llm/model_hub_bridge.py` | `test_model_hub_bridge` | ✅ Covered |
| `llm/model_selection.py` | — | ❌ No test |
| `llm/ports.py` | `test_model_hub_ports` | ✅ Covered |
| `llm/test_adapter.py` | `test_m03_test_adapter` | ✅ Covered |
| `llm/test_model_hub_bridge.py` | `test_model_hub_bridge` | ✅ Covered |
| `llm/types.py` | `test_model_hub_types` | ✅ Covered (40 funcs) |
| `llm/validator.py` | `test_m03_validator` | ✅ Covered |
| **obs/** | | |
| `obs/actor_metrics.py` | `test_m11_obs_e112` | ✅ Covered |
| `obs/metrics.py` | `test_m11_obs_e111` | ✅ Covered (98 funcs) |
| `obs/react_metrics.py` | `test_m11_obs_e112` | ✅ Covered |
| **orchestrator/** | | |
| `orchestrator/degradation.py` | — | ❌ No test |
| `orchestrator/interfaces.py` | — | ❌ No test |
| `orchestrator/ports.py` | — | ❌ No test |
| `orchestrator/routing.py` | — | ❌ No test |
| `orchestrator/stub.py` | — | ❌ No test |
| `orchestrator/types.py` | — | ❌ No test |
| **ports.py** (root) | `test_c1_port_protocols`, `ports/test_port_protocols` | ✅ Covered |
| **prompt/** | | |
| `prompt/affect.py` | `test_m04_e44_prompt_ss` | ✅ Covered |
| `prompt/back_prompt.py` | — | ❌ No dedicated test |
| `prompt/builder.py` | `test_m04_e44_prompt_ss` | ✅ Covered |
| `prompt/clarify_depth.py` | — | ❌ No dedicated test |
| `prompt/domain_rules.py` | — | ❌ No dedicated test |
| `prompt/mode.py` | `test_m04_e44_prompt_ss` | ✅ Covered (indirectly) |
| `prompt/scenario_templates.py` | — | ❌ No dedicated test |
| `prompt/sections.py` | `test_m04_e44_prompt_ss` | ✅ Covered |
| **protocols/** | | |
| `protocols/cancel_events.py` | `test_m09_e91_cancel_recovery` | ✅ Covered |
| `protocols/cancel_handler.py` | `test_m09_e91_cancel_recovery`, `test_m03_e36_conformance` | ✅ Covered |
| `protocols/cancellation.py` | `test_m09_e91_cancel_recovery` | ✅ Covered |
| `protocols/delivery_strategy.py` | — | ❌ No test |
| `protocols/hitl.py` | `test_m09_e93_hitl_recovery` | ✅ Covered |
| `protocols/hitl_coordinator.py` | `test_m09_e93_hitl_recovery` | ✅ Covered |
| `protocols/hitl_flow.py` | — | ⚠️ No dedicated test |
| `protocols/hitl_persistence.py` | — | ⚠️ No dedicated test |
| `protocols/hitl_pipeline.py` | — | ⚠️ No dedicated test |
| `protocols/hitl_wiring.py` | `test_m05_e54_multi_device` | ✅ Covered |
| `protocols/opp_pipeline.py` | — | ❌ No test |
| `protocols/suspension.py` | `test_m09_e92_suspension_recovery` | ✅ Covered |
| `protocols/suspension_events.py` | `test_m09_e92_suspension_recovery` | ✅ Covered |
| `protocols/suspension_manager.py` | `test_m03_e33_resume_context` | ✅ Covered |
| `protocols/task_lease.py` | — | ❌ No test |
| `protocols/trust_accumulator.py` | — | ❌ No test |
| `protocols/weave_batcher.py` | `test_m08_e83_dynamic_batch` | ✅ Covered |
| `protocols/weave_policy.py` | `test_m08_e82_weave_decision` | ✅ Covered |
| `protocols/weave_state.py` | `test_m08_e81_weave_signal` | ✅ Covered |
| **react/** | | |
| `react/history.py` | `test_m03_e33_resume_context` | ✅ Covered |
| `react/loop.py` | `test_m03_e34_parallel_safety`, `test_m03_e36_conformance` | ✅ Covered |
| **scheduler/** | | |
| `scheduler/proactive_scheduler.py` | — | ❌ No test |
| **task/** | | |
| `task/bundled_executor.py` | `test_m10_epics_7_8_9` | ✅ Covered |
| `task/classifier.py` | `test_m10_e103_tier_routing` | ✅ Covered |
| `task/complexity.py` | `test_m10_e101_ultrabert_pipeline` | ✅ Covered |
| `task/dependency_queue.py` | — | ❌ No test |
| `task/dispatch.py` | `test_m10_epics_7_8_9` | ✅ Covered |
| `task/envelope_bridge.py` | — | ⚠️ No dedicated test |
| `task/intent.py` | `test_m10_epics_7_8_9` | ✅ Covered |
| `task/parallel_safety.py` | `test_m03_e34_parallel_safety` | ✅ Covered |
| `task/receiver.py` | `test_m10_epics_7_8_9` | ✅ Covered |
| `task/tools.py` | — | ⚠️ No dedicated test |
| `task/topics.py` | `test_m01_topics` | ✅ Covered |
| **tools/** | | |
| `tools/dispatcher.py` | `test_tool_fabric_live`, `test_tool_fabric_port_wiring` | ✅ Covered |
| `tools/implementations.py` | `test_calendar_tools`, `test_family_tools`, `test_travel_tools`, `test_monitor_tools` | ✅ Covered |
| `tools/parallelism.py` | `test_m03_e34_parallel_safety` | ✅ Covered |
| `tools/result_protocol.py` | — | ⚠️ No dedicated test |
| `tools/schemas_back.py` | `test_m04_e43_session_bundle` | ✅ Covered |
| `tools/schemas_front.py` | `test_m04_e43_session_bundle` | ✅ Covered |

### 4.2 Package-Only Modules (init-only, no source files)

These source folders contain only `__init__.py` — they are re-export or placeholder packages:
- `affective/` — re-exports from `experience/`
- `empathy/` — re-exports from `experience/`
- `rhythm/` — re-exports from `experience/`
- `types/` — type re-exports

---

## 5. Coverage Gaps

### 5.1 Modules with NO Test Coverage (❌)

| Module | Risk | Notes |
|---|---|---|
| `bus/deserialize.py` | Medium | Envelope deserialization — tested indirectly via bus integration |
| `compression/episodic_compressor.py` | Low | Standalone compressor, likely unused in current flow |
| `identity/dynamic_identity.py` | Low | Dynamic identity switching — may be experimental |
| `kernel/bootstrap.py` | **High** | Concierge kernel bootstrap — core wiring |
| `kernel/runner.py` | **High** | Concierge kernel runner — core execution loop |
| `llm/gemini_adapter.py` | Medium | Live LLM adapter — hard to unit test |
| `llm/model_selection.py` | Medium | Model selection logic |
| `orchestrator/degradation.py` | Medium | Graceful degradation strategies |
| `orchestrator/interfaces.py` | Medium | Orchestrator interfaces |
| `orchestrator/ports.py` | Medium | Orchestrator port definitions |
| `orchestrator/routing.py` | Medium | Orchestrator routing logic |
| `orchestrator/stub.py` | Low | Stub implementation |
| `orchestrator/types.py` | Low | Type definitions only |
| `prompt/back_prompt.py` | Medium | Back-actor prompt construction |
| `prompt/clarify_depth.py` | Low | Clarification depth heuristics |
| `prompt/domain_rules.py` | Low | Domain-specific prompt rules |
| `prompt/scenario_templates.py` | Low | Scenario template strings |
| `protocols/delivery_strategy.py` | Low | Delivery strategy protocol |
| `protocols/hitl_flow.py` | Medium | HITL flow orchestration |
| `protocols/hitl_persistence.py` | Medium | HITL persistence layer |
| `protocols/hitl_pipeline.py` | Medium | HITL pipeline |
| `protocols/opp_pipeline.py` | Low | Opportunity pipeline |
| `protocols/task_lease.py` | Low | Task lease protocol |
| `protocols/trust_accumulator.py` | Low | Trust accumulation logic |
| `scheduler/proactive_scheduler.py` | Medium | Proactive scheduling |
| `task/dependency_queue.py` | Medium | Task dependency resolution |

### 5.2 Summary of Gaps

| Category | Untested Modules | Risk Level |
|---|---|---|
| **kernel/** (bootstrap, runner) | 2 | 🔴 HIGH — core wiring & execution |
| **orchestrator/** (all 6 files) | 6 | 🟡 MEDIUM — orchestration layer |
| **prompt/** (3 of 8 files) | 3 | 🟡 MEDIUM — prompt construction |
| **protocols/** (5 of 18 files) | 5 | 🟡 MEDIUM — protocol definitions |
| **llm/** (2 of 8 files) | 2 | 🟡 MEDIUM — live adapter + model selection |
| **Other** (bus, compression, identity, scheduler, task) | 7 | 🟢 LOW to MEDIUM |
| **Total untested** | **25 of ~120 source files** | ~21% gap |

---

## 6. Test Class Inventory (All 548 Classes)

### M00 — V3 Conformance (17 classes)
- `TestInterruptDuringProgressingWithCompletion`
- `TestCancelThenLateCompletionThenFailedCancelled`
- `TestSuspendInIncompatibleState`
- `TestWeaveWindowBatchWithUserInput`
- `TestSameTurnCompleteNoDuplicatePresent`
- `TestFrontEmitOrdering`
- `TestBackTaskResumeRouting`
- `TestCancelDuringBackExecution`
- `TestHITLResolveEmitsOneResume`
- `TestDegenerateResponseRecovery`
- `TestBackTextWithoutToolsBudget`
- `TestParallelToolExecution`
- `TestValidatorRejectsDisallowedTools`
- `TestBusSubscriptionRoutingInvariant`
- `TestBuilderPriorityConsistency`
- `TestTopicDeduplication`
- `TestBusEnvelopeStampingAndCausalOrder`

### M01 — Builders / Events / Ledger / Topics (23 classes)
- `TestBuildersRegistry`, `TestBuilderOutput`
- `TestSchemaRegistryIdentity`, `TestValidateEventPositive`, `TestValidateEventNegative`, `TestValidateEventChainPositive`, `TestValidateEventChainNegative`, `TestBuilderValidationWiring`, `TestHitlWiringCanonicalChecks`, `TestTypeSpecificFieldIntrospection`, `TestPackageExports`, `TestValidateCanonicalMetadataCompat`
- `TestLedgerStore`, `TestLedgerWriter`, `TestProjectHistory`, `TestProjectTaskStates`, `TestProjectPendingResults`, `TestLedgerReplay`, `TestControllerLedgerIntegration`
- `TestTopicCounts`, `TestTimingResolution`, `TestPriorityMapping`, `TestSubscriptionGroups`

### M02 — Guard / Dead Letter / Response-Final / Task State (75 classes)
- Guard (10): `TestFullGuardTableCompleteness`, `TestSubscribedTopics`, `TestGetGuardAction`, `TestBackwardCompatibility`, `TestGuardDispatchOnFSM`, `TestCancellingTransition`, `TestHandleInterrupt`, `TestNoDuplicateDagSubscription`, `TestHardcodedConstantsReplaced`, `TestGuardConformanceInvariants`
- Dead Letter (10): `TestDeadLetterTopicAndBuilder`, `TestDeadLetterPayloadSchema`, `TestControllerDeadLetterRouting`, `TestFSMTurnStateOverflow`, `TestFSMTurnStateTTL`, `TestDeadLetterConsumer`, `TestWeaveActionDeadLetter`, `TestPendingResultsQueueOverflow`, `TestWeaveBatcherOverflow`, `TestConfigIntegration`
- Response-Final (10): `TestDecideResponseFinalTruthTable`, `TestResponseFinalEntryType`, `TestResponseFinalActionEnum`, `TestControllerResponseFinal`, `TestIdempotencyLedger`, `TestControllerIdempotency`, `TestTopicGuardExtraction`, `TestFinalizeTurnExtraction`, `TestSeenUserInputIdsRemoved`, `TestE23ConfigIntegration`
- Conformance (8): `TestGuardMatrixCompleteness`, `TestDeadLetterCaptureAndReconciliation`, `TestResponseFinalTruthTable`, `TestInterruptDuringProgressing`, `TestCancelRace`, `TestDeferredHitlSurfacing`, `TestWeaveBurst`, `TestPendingResultsTTLAndOverflow`
- Task Artifacts (9): `TestArtifactType`, `TestTaskArtifactEntry`, `TestISection`, `TestWriteOps`, `TestReadOps`, `TestPrompts`, `TestSerialization`, `TestEviction`, `TestArtifactsWarm`
- Task State (9): `TestTaskStatus`, `TestTaskStateEntry`, `TestISection`, `TestWriteOps`, `TestReadOps`, `TestPrompts`, `TestSerialization`, `TestPruning`, `TestLifecycle`

### M03 — Bus / Resume / Parallel / Shared / Adapter / Validator (49 classes)
- Bus (9): `TestProtocolCompliance`, `TestIBusMethods`, `TestIMailboxRouterMethods`, `TestIMailboxMethods`, `TestMiddlewareIntegration`, `TestBuildMiddlewareChain`, `TestBusWithMiddleware`, `TestSetupRegression`, `TestReExports`
- Resume (7): `TestSuspensionManagerSingleOwner`, `TestResumeHandlerEnvelopeContext`, `TestDeprecatedContextHelpers`, `TestEmitBackResultReactHistory`, `TestMessageSerialization`, `TestCleanupTaskOnTerminalStates`, `TestResumeFlowIntegration`
- Parallel (8): `TestParallelSafetyDocstring`, `TestClassifyToolBatch`, `TestIsParallelSafe`, `TestReactLoopIntegration`, `TestConfigToggle`, `TestStaleConstants`, `TestSubmitResultGuard`, `TestReactLoopClassifiedExecution`
- Shared (6): `TestParseEnvelopePayload`, `TestSafeGetSection`, `TestNeverCancel`, `TestImportHygiene`, `TestPackageExports`, `TestSharedModuleMinimalDeps`
- Conformance (4): `TestFrontEmissionOrdering`, `TestBackTopicRouting`, `TestCancelPropagation`, `TestParallelToolSafety`
- Test Adapter (7): `TestProtocolCompliance`, `TestDefaultResponse`, `TestFixedResponses`, `TestSequenceResponses`, `TestStreaming`, `TestCallRecording`, `TestStreamRecordsCalls`
- Validator (8): `TestValidationResult`, `TestValidatorConstruction`, `TestToolAllowlist`, `TestRequiredParams`, `TestParamTypeCheck`, `TestTextOnlyResponse`, `TestFixedResponse`, `TestEdgeCases`

### M04 — Session State (33 classes)
- SS Binding (3): `TestTaskBridgeRebind`, `TestControlExtensionBind`, `TestControllerSessionStateBinding`
- Write Path (9): `TestToolContextWriterPort`, `TestLlmWritableConfig`, `TestUpdateBeliefsWritePath`, `TestUpdateScoreboardWritePath`, `TestUpdateClarificationsWritePath`, `TestUpdateNarrativeWritePath`, `TestRefineAffectWritePath`, `TestPromoteBeliefWritePath`, `TestRuntimeSectionGuard`
- Session Bundle (5): `TestBundleToolRegistration`, `TestBundleEmptyInput`, `TestBundleIdempotency`, `TestBundleBatchWiring`, `TestBundleStopOnRejection`
- Prompt-SS (16): `TestSectionRenderersTable`, `TestTaskStateRenderers`, `TestBeliefsActiveRenderers`, `TestHistoryActiveRenderers`, `TestScoreboardRenderers`, `TestClarificationsRenderers`, `TestNarrativeActiveRenderers`, `TestAffectiveNowRenderers`, `TestControlRenderers`, `TestPersonaRenderers`, `TestReadSsSections`, `TestBuildStage8`, `TestFrontHandlerSsPassthrough`, `TestToneToHints`, `TestStyleToHints`, `TestAffectiveNowRendererWithExperienceLayer`

### M05 — Arbiter / Interrupt (30 classes)
- Arbiter (11): `TestArbiterDecision`, `TestArbiterResult`, `TestInflightContext`, `TestBuildInflightContext`, `TestDomainOverlap`, `TestEntityOverlap`, `TestArbiterClassify`, `TestCancelTargetSelection`, `TestBusTopic`, `TestArbiterConfig`, `TestEdgeCases`
- Interrupt (6): `TestArbiterWiring`, `TestParallelNewPath`, `TestCancelPath`, `TestModifyInflightPath`, `TestDeferPath`, `TestE52TopicAndBuilderIntegration`
- Normal (5): `TestListeningArbiterWiring`, `TestArbiterMetadataAttachment`, `TestDetermineModeRoutingMetadata`, `TestFrontRoutingMetadataPassthrough`, `TestListeningEndToEnd`
- Multi-Device (8): `TestMetaDeviceTracking`, `TestDeviceIdPassthrough`, `TestDeviceConflictPrecedence`, `TestHighImpactConflictDetection`, `TestBuildConflictClarification`, `TestHitlWiringMultiDeviceChecks`, `TestHitlDuplicateResponseGuard`, `TestDeviceIdFSMIntegration`

### M08 — Weave (33 classes)
- Signal (8): `TestWeaveSignalDataclass`, `TestWeaveSignalFromRuntime`, `TestUserActivityTracker`, `TestIdleThresholdConstants`, `TestPendingUrgencyProfiler`, `TestTurnStateUrgency`, `TestEmotionalGate`, `TestTopicUITypingWiring`
- Decision (7): `TestWeaveDecisionEnum`, `TestWeaveDecisionResult`, `TestWeavePolicyConfig`, `TestWeavePolicyDecide`, `TestWeavePolicyWithConfig`, `TestWeaveDecidedTopicWiring`, `TestWeaveDecisionMadeEvent`
- Dynamic Batch (9): `TestScheduleWeaveFlush`, `TestDeferPath`, `TestDigestPayload`, `TestDomainExtraction`, `TestSortResultsForDelivery`, `TestGenerateUrgencyLabel`, `TestGenerateEmotionalContext`, `TestWeaveTemplatePlaceholders`, `TestScheduleFlushIntegration`
- Policy Integration (9): `TestRoutingResultDataclass`, `TestWeaveIntegrationRouter`, `TestReEvalResultDataclass`, `TestTypingPolicyReEvaluator`, `TestFallbackConstants`, `TestWeaveFallbackHandler`, `TestWeaveMetricsCollector`, `TestWeaveQueue`, `TestE84Integration`

### M09 — Recovery (22 classes)
- Cancel (4): `TestCancelHandlerLedgerWrites`, `TestCancelStateProjection`, `TestCancelRebuildFromEvents`, `TestLateCancelDedupAfterRecovery`
- Suspension (3): `TestSuspensionManagerLedgerWrites`, `TestSuspensionStateProjection`, `TestSuspensionRebuildFromEvents`
- HITL (4): `TestHILCoordinatorLedgerWrites`, `TestHITLStateProjection`, `TestHILCoordinatorRebuildFromEvents`, `TestHITLCrashRecoveryWithL2`
- History (3): `TestActiveTaskIdsFromProjection`, `TestFSMTurnStateLedgerWrites`, `TestFSMTurnStateRebuild`
- Task State (3): `TestTaskBridgeLedgerWrites`, `TestTaskStateProjectionRoundtrip`, `TestRebuildFromProjection`
- Full Recovery (5): `TestCrashRecoveryOrchestrator`, `TestFSMStateDerivation`, `TestCrashRecoveryReport`, `TestFallbackSafety`, `TestFullE2ERecovery`

### M10 — UltraBERT / Phase1 / Task Dispatch (45 classes)
- UltraBERT (6): `TestMapping`, `TestExtraHeads`, `TestComplexityClassifier`, `TestConfidenceThresholding`, `TestGracefulDegradation`, `TestArousalHeuristic`
- SS Writes (6): `TestControlSectionIntentMethods`, `TestControlSectionWrites`, `TestScoreboardWrites`, `TestAffectiveNowWrites`, `TestPartialFailureResilience`, `TestThreeSectionIntegration`
- Tier Routing (4): `TestAutoTierDispatch`, `TestCrisisShortCircuit`, `TestHighTierRouting`, `TestObservabilityEvents`
- Adapter (8): `TestMappingConstants`, `TestStubUltraBERTAdapter`, `TestK1AdapterInit`, `TestK1AdapterAnalyze`, `TestK1AdapterMetrics`, `TestLRUTTLCache`, `TestSingleton`, `TestWarmup`
- Extra Heads (5): `TestTemporalHead`, `TestRelationHead`, `TestEmbeddingHead`, `TestBootstrapWiring`, `TestEndToEndIntegration`
- Task Epics (16): `TestDispatchTaskSingle`, `TestDispatchTaskBundled`, `TestDispatchTaskChained`, `TestDispatchTaskUrgency`, `TestDispatchTaskSchema`, `TestTaskReceiverConstruction`, `TestTaskReceiverImmediate`, `TestTaskReceiverErrors`, `TestTaskReceiverChained`, `TestTaskReceiverClearAndResults`, `TestIntentResult`, `TestBundledPlanSingle`, `TestBundledPlanMultiple`, `TestBundledPlanErrors`, `TestBundledPlanProperties`, `TestPackageStructure`

### M11 — Delta / Observability (69 classes)
- Delta Epics 1-2-3 (15): `TestSessionDeltaCreation`, `TestSessionDeltaValidation`, `TestSessionDeltaDedupKey`, `TestSessionDeltaSerialization`, `TestValidDeltaConstants`, `TestDeltaTopics`, `TestEmitArtifact`, `TestEmitTaskStateChange`, `TestValidTaskStatuses`, `TestDeltaAggregatorBatching`, `TestDeltaAggregatorDedup`, `TestDeltaAggregatorCausalOrder`, `TestDeltaAggregatorStats`, `TestDeltaBatchDataclass`, `TestDeltaPackageExports`
- Delta Epics 4-5-6 (18): `TestApplyResultDataclass`, `TestDeltaApplicatorApply`, `TestDeltaApplicatorRejection`, `TestDeltaApplicatorNotify`, `TestDeltaApplicatorWriteData`, `TestWriterRole`, `TestSectionWritersMatrix`, `TestValidateWriter`, `TestEnforceWriter`, `TestSingleWriterInvariantDesignDoc`, `TestSectionSnapshotDataclass`, `TestSnapshotReaderRegister`, `TestSnapshotReaderRead`, `TestSnapshotReaderWrite`, `TestSnapshotReaderDelete`, `TestSnapshotReaderMultiple`, `TestCrossActorReadScenarios`, `TestDeltaPackageExportsUpdated`
- Delta Epics 7-8-9 (17): `TestSectionOverflowHandlerInit`, `TestSectionOverflowHandlerConstants`, `TestEvictArtifacts`, `TestEvictTerminalTasks`, `TestEvictOldestTurns`, `TestUnknownSectionPassthrough`, `TestEvictionLog`, `TestOverflowSlots`, `TestOverflowIntegrationWithApplicator`, `TestDeltaPackageImportability`, `TestDeltaPackageExports`, `TestDeltaPackageStructure`, `TestE2EArtifactPipeline`, `TestE2EDedupWithinBatchWindow`, `TestE2EMutationGuardReject`, `TestE2ESingleWriterSerialization`, `TestE2EWithOverflowHandler`
- Obs E111 (11): `TestMetricEnvelope`, `TestMetricsCollector`, `TestSlidingWindow`, `TestMetricAggregator`, `TestTurnTimer`, `TestMetricBusTopics`, `TestMetricBuilders`, `TestLabelKey`, `TestEmitMetric`, `TestBuildSessionSummary`, `TestObsPackageImport`
- Obs E112 (8): `TestClassifyExitPath`, `TestRecordReactLoopMetrics`, `TestBuildReactLoopSummary`, `TestRecordFrontMetrics`, `TestRecordBackMetrics`, `TestClassifyBudgetUtilization`, `TestE112PackageImport`, `TestE2EMetricChain`

### M15 — Experience Layer (11 classes)
- `TestEpic15_1_PackageStructure`, `TestEpic15_2_EmotionalProcessor`, `TestEpic15_3_AffectiveMirror`, `TestEpic15_4_NarrativeWeaver`, `TestEpic15_5_AnticipatoryResponder`, `TestEpic15_6_ProactiveAgent`, `TestEpic15_7_RhythmController`, `TestResponseStyleAdapter`, `TestEpic15_8_ExperienceLayerOrchestrator`, `TestEpic15_9_CadenceTests`, `TestEpic15_10_E2EWiring`

### C1 — Port Protocols (11 classes)
- `TestInputAdapterCompliance`, `TestOutputAdapterCompliance`, `TestStateAdapterCompliance`, `TestDispatchAdapterCompliance`, `TestMemoryAdapterCompliance`, `TestReExportedPortCompliance`, `TestProductionInputAdapterCompliance`, `TestProductionOutputAdapterCompliance`, `TestProductionStateAdapterCompliance`, `TestProductionDispatchAdapterCompliance`, `TestProductionMemoryAdapterCompliance`

### Non-Milestone Tests (150 classes across standalone files)
- Model Hub Bridge (11): `TestBridgeSatisfiesProtocol`, `TestChatRoundTrip`, `TestToolCallRoundTrip`, `TestStructuredRoundTrip`, `TestReasonRoundTrip`, `TestStreaming`, `TestTokenUsage`, `TestDiscoverCapabilities`, `TestHealth`, `TestTestModelHubBridge`, `TestFinishReasonMapping`
- Model Hub Ports (10): `TestRuntimeCheckable`, `TestIModelHubPortSignature`, `TestEventPortSignature`, `TestStateReadPortSignature`, `TestMetricsPortSignature`, `TestConfigPortSignature`, `TestCredentialPortSignature`, `TestHealthPortSignature`, `TestProviderPluginProtocol`, `TestSupportingTypes`
- Model Hub Types (26): `TestCapabilityType`, `TestPriority`, `TestFinishReason`, `TestMessage`, `TestToolDefinition`, `TestToolCallResult`, `TestRequestConstraints`, `TestChatPayload`, `TestToolCallPayload`, `TestStructuredOutputPayload`, `TestReasonPayload`, `TestEmbedPayload`, `TestVisionPayload`, `TestBatchPayload`, `TestModeratePayload`, `TestTokenCountPayload`, `TestCachePromptPayload`, `TestAudioInputPayload`, `TestTTSPayload`, `TestHubRequest`, `TestUsage`, `TestResponseMetadata`, `TestCapabilityResults`, `TestHubResponse`, `TestHubChunk`, `TestModelInfo`
- Monitor Tools (13): `TestWeatherForecast`, `TestInitialForecast`, `TestUpdatedForecast`, `TestMonitorStore`, `TestStartBackgroundMonitor`, `TestStopBackgroundMonitor`, `TestCheckMonitors`, `TestGetWeatherForecast`, `TestGetMonitorStatus`, `TestListActiveMonitors`, `TestExecuteMonitorTool`, `TestMonitorToolSchemas`, `TestDemoScenario`
- POC Bridge Adapter (5): `TestStructural`, `TestAvailability`, `TestSendCommand`, `TestQuery`, `TestRouteIFL`
- Tool Fabric Live (6): `TestDiscoverLive`, `TestInvokeLive`, `TestBatchInvokeLive`, `TestSpawnLive`, `TestWorkflowLive`, `TestNoFabricFallback`
- Tool Fabric Port Wiring (6): `TestDiscoverWithFabricPort`, `TestInvokeWithFabricPort`, `TestSpawnWithFabricPort`, `TestWorkflowWithFabricPort`, `TestBackwardCompat`, `TestHITLBlockingWithFabricPort`
- Travel Tools (12): `TestSearchAccommodations`, `TestGetAccommodationDetails`, `TestBookAccommodation`, `TestSearchRestaurants`, `TestGetRestaurantDetails`, `TestBookRestaurant`, `TestPlanRoute`, `TestSearchActivities`, `TestBookSpaService`, `TestExecuteTravelTool`, `TestBookingStore`, `TestTravelToolsRegistry`
- Calendar Tools (8): `TestCreateCalendarEvent`, `TestScheduleReminder`, `TestGenerateTripSummary`, `TestGetDemoTripSummary`, `TestExecuteCalendarTool`, `TestCalendarStore`, `TestCalendarToolsRegistry`, `TestTripSummaryFormatting`
- Family Tools (9): `TestSendFamilyMessage`, `TestScheduleFamilyCheckin`, `TestGetFamilyMemberInfo`, `TestComposeWeekendInstructions`, `TestSimulateCheckinResponse`, `TestExecuteFamilyTool`, `TestFamilyMessageStore`, `TestFamilyToolsRegistry`, `TestFamilyMemberData`
- Gap Detection (8): `TestScenario1_BookRestaurant`, `TestScenario2_BookAccommodation`, `TestScenario3_SuggestTransportation`, `TestScenario4_SendFamilyMessage`, `TestScenario5_ScheduleReminder`, `TestMultipleGaps`, `TestNoGaps`, `TestSessionContext`
- Contract Converter (2): `TestPocDictToContract`, `TestConvertAllPocCapabilities`
- Fabric Port (3): `TestIFabricPortRuntimeCheckable`, `TestIFabricPortSignatures`, `TestFabricIsInstance`
- Fabric Wiring E2E (4): `TestRegistration`, `TestExecute`, `TestExecuteBatch`, `TestDiscovery`
- Two-Way Concierge (4): `TestTaskQueue`, `TestNotificationQueue`, `TestTaskRegistry`, `TestConcurrentOperation`

### Adapter Tests (10 classes)
- `TestNullBridgeWriteProtocol`, `TestNullBridgeWriteBehaviour`
- `TestNullDeltaBusProtocol`, `TestNullDeltaBusBehaviour`
- `TestNullEventSubscriptionProtocol`, `TestNullEventSubscriptionBehaviour`
- `TestNullSessionStateReaderProtocol`, `TestNullSessionStateReaderBehaviour`
- `TestSnapshotStateReadProtocol`, `TestSnapshotStateReadBehaviour`

### Port Tests (12 classes)
- `TestMockDispatchAdapterBehaviour`, `TestFabricDispatchAdapterBehaviour`
- `TestInputAdapterBehaviour`, `TestBusInputAdapterBehaviour`
- `TestMockMemoryAdapterBehaviour`, `TestRecallMemoryAdapterBehaviour`
- `TestOutputAdapterBehaviour`, `TestBusOutputAdapterBehaviour`
- `TestTestAdapterProtocolCompliance`, `TestProductionAdapterProtocolCompliance`
- `TestInMemoryStateAdapterBehaviour`, `TestSSMStateAdapterBehaviour`

---

## 7. Top 10 Largest Test Files

| # | File | Funcs | Lines |
|---|---|---|---|
| 1 | `test_m00_v3_conformance.py` | 55 | 1,992 |
| 2 | `test_m15_experience_layer.py` | 171 | 1,492 |
| 3 | `test_m11_epics_7_8_9.py` | 79 | 1,170 |
| 4 | `test_m02_e24_conformance.py` | 47 | 1,095 |
| 5 | `test_m11_obs_e111.py` | 98 | 1,064 |
| 6 | `test_m10_epics_7_8_9.py` | 65 | 1,055 |
| 7 | `test_m08_e84_policy_integration.py` | 88 | 1,038 |
| 8 | `test_m11_epics_4_5_6.py` | 101 | 1,021 |
| 9 | `test_m11_epics_1_2_3.py` | 74 | 1,000 |
| 10 | `test_m11_obs_e112.py` | 55 | 962 |

---

## 8. Test Distribution by Subsystem

| Subsystem | Test Files | Classes | Funcs | % of Total |
|---|---|---|---|---|
| FSM (guard, arbiter, controller, response-final) | 11 | 99 | 551 | 20.6% |
| Weave (signal, decision, batch, policy) | 4 | 33 | 299 | 11.2% |
| Delta + Overflow | 3 | 50 | 254 | 9.5% |
| Observability (metrics, react metrics) | 2 | 19 | 153 | 5.7% |
| Tools (travel, calendar, family, monitor, fabric) | 8 | 67 | 224 | 8.4% |
| Session State (binding, write, bundle, prompt-SS) | 4 | 33 | 152 | 5.7% |
| Recovery (M09) | 6 | 22 | 105 | 3.9% |
| UltraBERT / Phase1 | 5 | 29 | 134 | 5.0% |
| Task (dispatch, receiver, parallel) | 3 | 32 | 131 | 4.9% |
| LLM (bridge, types, ports, adapter, validator) | 5 | 62 | 139 | 5.2% |
| Bus (topics, builders, compliance) | 3 | 15 | 71 | 2.7% |
| Events / Ledger | 2 | 17 | 69 | 2.6% |
| Experience Layer | 1 | 11 | 171 | 6.4% |
| Ports + Adapters | 12 | 24 | 73 | 2.7% |
| Protocol (resume, conformance) | 3 | 17 | 89 | 3.3% |
| Fabric (port, wiring, converter, POC) | 4 | 14 | 75 | 2.8% |
| Cross-cutting (C1, gap, two-way) | 3 | 23 | 60 | 2.2% |
| V3 Conformance | 1 | 17 | 55 | 2.1% |

---

## 9. Key Observations

1. **Test density is highest in FSM and Weave** — 551 + 299 = 850 test functions (31.7% of all tests), reflecting the complexity of state machine transitions and the weave delivery subsystem.

2. **Experience Layer has the single largest file** — `test_m15_experience_layer.py` with 171 functions testing all 7 components in one file.

3. **Recovery tests (M09) are systematic** — Each protocol (cancel, suspension, HITL, task state) has its own ledger-write + projection + rebuild test file, plus a full E2E orchestrator test.

4. **No M06/M07 tests in k1** — These milestones only have tests in `tests/poc/` (HITL subtask, resume path, lifecycle events, crash recovery for M06; back pool, task lease, topic router, ready queue for M07).

5. **Orchestrator is entirely untested** — All 6 files in `orchestrator/` have zero test coverage. This is the highest-risk gap.

6. **Kernel bootstrap/runner untested** — The core wiring that assembles the concierge has no dedicated tests.

7. **In-source test files are helpers, not tests** — `llm/test_adapter.py` and `llm/test_model_hub_bridge.py` are test infrastructure (imported by real tests) with zero `test_*` functions.

8. **Naming is consistent** — All test files follow `test_mXX_eYY_*.py` for milestone-scoped tests or `test_<feature>.py` for standalone feature tests. All use `class Test*` with `def test_*` method naming.

9. **Port protocol compliance is double-tested** — Both `test_c1_port_protocols.py` (11 classes, 35 funcs) and `ports/test_port_protocols.py` (2 classes, 16 funcs) test adapter-to-port compliance.

10. **~79% source file coverage** — 95 of ~120 source files have direct or indirect test coverage. The 25 untested files are concentrated in orchestrator, prompt templates, protocol definitions, and kernel wiring.
