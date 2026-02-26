# K1 POC End-to-End Wiring Checklist

**Generated:** 2026-02-23
**Source of Truth:** `concierge_poc_design_v2.md`
**Target:** Everything connects through `kernel/bootstrap.py`

---

## PART 1: Folder-to-Folder Dependency Map

```
                           +-----------+
                           |   demo/   |  (TOP -- user entry point)
                           +-----+-----+
                                 |
                                 v
                          +-----------+
                          |  kernel/  |  (bootstrap + runner)
                          +-----+-----+
                                |
            +---+---+---+---+---+---+---+---+---+---+
            |   |   |   |   |   |   |   |   |   |   |
            v   v   v   v   v   v   v   v   v   v   v
         actors/ fsm/ tools/ react/ prompt/ delta/ orchestrator/ protocols/ experience/ fabric/ sessionstate/
            |     |     |      |      |       |         |             |          |         |         |
            |     |     |      |      |       |         |             |          |         |         |
            +--+--+--+--+--+--+--+--+-+--+---+----+----+------+------+          |         |         |
               |     |     |     |    |       |         |                        |         |         |
               v     v     v     v    v       v         v                        v         v         v
             llm/  task/ bus/  (shared leaf packages -- no k1_poc internal deps)
```

### Explicit Folder Dependencies

| Folder | Depends On (k1_poc internal) | External Deps |
|--------|------------------------------|---------------|
| **bus/** | -- (leaf) | `k1.bus.*` |
| **llm/** | -- (leaf) | `google.genai` (lazy) |
| **task/** | -- (leaf) | -- |
| **sessionstate/** | -- (leaf) | `sqlite3` |
| **fabric/** | -- (leaf) | -- |
| **experience/** | -- (leaf) | -- |
| **delta/** | -- (leaf) | -- |
| **prompt/** | `llm/` | -- |
| **react/** | `llm/`, `tools/` | -- |
| **tools/** | `llm/`, `task/` | -- |
| **orchestrator/** | `task/` | -- |
| **protocols/** | `fsm/`, `prompt/`, `task/`, `sessionstate/`, `bus/` | -- |
| **fsm/** | `bus/`, `orchestrator/`, `protocols/`, `sessionstate/`, `task/` | `k1.bus.*` |
| **actors/** | `bus/`, `llm/`, `prompt/`, `react/`, `task/`, `tools/` | `k1.bus.*` |
| **kernel/** | `actors/`, `bus/`, `delta/`, `experience/`, `fabric/`, `fsm/`, `llm/`, `orchestrator/`, `protocols/`, `sessionstate/`, `tools/` | -- |
| **demo/** | `kernel/` (+ `demo/` internal only) | -- |

---

## PART 2: Internal Wiring per Folder

### 2.1 `bus/` -- Event Bus Infrastructure (LEAF)

```
topics.py -----> builders.py -----> setup.py
  (29 consts)     (30 build_*)      (factory fns)
```

| File | Provides | Used By |
|------|----------|---------|
| [topics.py](../poc/k1_poc/bus/topics.py) | 29 TOPIC_* constants, FRONT/BACK_SUBSCRIPTIONS, priority map | builders.py, setup.py, fsm/controller.py, fsm/transition_table.py, actors/* |
| [builders.py](../poc/k1_poc/bus/builders.py) | 30 `build_*()` envelope factories + BUILDERS registry | actors/front.py, actors/back.py, fsm/controller.py |
| [setup.py](../poc/k1_poc/bus/setup.py) | `create_poc_bus()`, `create_poc_router()`, `register_poc_actors()` | main.py -> kernel/bootstrap.py |

**Internal wiring status:** COMPLETE. All 3 files chain cleanly.

---

### 2.2 `llm/` -- LLM Adapter Layer (LEAF)

```
types.py -----> ports.py -----> gemini_adapter.py / test_adapter.py
                  ^                      |
                  |                      |
             validator.py         model_selection.py
```

| File | Provides | Used By |
|------|----------|---------|
| [types.py](../poc/k1_poc/llm/types.py) | `ModelMessage`, `ToolSchema`, `ToolCallResult`, `ConciergeModelRequest/Response`, `FinishReason` | ports.py, validator.py, react/loop.py, tools/dispatcher.py |
| [ports.py](../poc/k1_poc/llm/ports.py) | `IConciergeModelPort` protocol | actors/front.py, actors/back.py, react/loop.py |
| [validator.py](../poc/k1_poc/llm/validator.py) | `LLMOutputValidator`, `ValidationResult` | actors/front.py, actors/back.py, react/loop.py |
| [test_adapter.py](../poc/k1_poc/llm/test_adapter.py) | `TestConciergeAdapter` (implements IConciergeModelPort) | kernel/bootstrap.py |
| [gemini_adapter.py](../poc/k1_poc/llm/gemini_adapter.py) | `GeminiConciergeAdapter` (implements IConciergeModelPort) | kernel/bootstrap.py |
| [model_selection.py](../poc/k1_poc/llm/model_selection.py) | `select_model()`, `MODEL_SELECTION_TABLE` | (future use) |

**Internal wiring status:** COMPLETE.

---

### 2.3 `task/` -- Task Data Structures (LEAF)

```
intent.py -----> dispatch.py -----> envelope_bridge.py
                     |
              complexity.py
                     |
              classifier.py -----> dependency_queue.py
                     |
              parallel_safety.py
                     |
              receiver.py
                     |
              bundled_executor.py
```

| File | Provides | Used By |
|------|----------|---------|
| [intent.py](../poc/k1_poc/task/intent.py) | `TaskIntent` dataclass | dispatch.py, tools/implementations.py, fsm/controller.py |
| [dispatch.py](../poc/k1_poc/task/dispatch.py) | `TaskDispatch`, `TaskComplete`, `TaskFailed` | tools/implementations.py, fsm/controller.py |
| [complexity.py](../poc/k1_poc/task/complexity.py) | `ComplexityTier`, `TIER_BUDGET`, `budget_for_tier()` | actors/front.py, tools/implementations.py |
| [classifier.py](../poc/k1_poc/task/classifier.py) | `classify_intents()`, `build_dispatches()` | (future -- FSM Phase1) |
| [topics.py](../poc/k1_poc/task/topics.py) | 10 topic constants | (used by task internal) |
| [envelope_bridge.py](../poc/k1_poc/task/envelope_bridge.py) | `dispatch_to_envelope()`, `complete_to_envelope()` | (bridge to bus envelopes) |
| [tools.py](../poc/k1_poc/task/tools.py) | `DISPATCH_TASK_SCHEMA`, `dispatch_task()` | (schema reference) |
| [parallel_safety.py](../poc/k1_poc/task/parallel_safety.py) | `classify_tool_batch()`, `is_parallel_safe()` | tools/parallelism.py |
| [receiver.py](../poc/k1_poc/task/receiver.py) | `TaskReceiver` | (future use) |
| [bundled_executor.py](../poc/k1_poc/task/bundled_executor.py) | `BundledExecutionPlan` | (MEDIUM+ tier) |
| [dependency_queue.py](../poc/k1_poc/task/dependency_queue.py) | `TaskDependencyQueue` | (chained tasks) |

**Internal wiring status:** COMPLETE.

---

### 2.4 `sessionstate/` -- Session State Management (LEAF)

```
ports/ -----+
             |
sections/ --+---> manager.py ---> factory.py
             |        |
tiers/ -----+    guard.py
             |   sizetracker.py
adapters/ --+   eviction.py
                 local_cold.py
                 migration.py
```

| File | Provides | Used By |
|------|----------|---------|
| [factory.py](../poc/k1_poc/sessionstate/factory.py) | `SessionStateFactory.create_standalone()`, `.create_for_testing()` | kernel/bootstrap.py |
| [manager.py](../poc/k1_poc/sessionstate/manager.py) | `SessionStateManager` | factory.py -> kernel/bootstrap.py |
| [guard.py](../poc/k1_poc/sessionstate/guard.py) | `MutationGuard` | manager.py, delta/applicator.py |
| [sections/](../poc/k1_poc/sessionstate/sections) | 10 HOT section classes + Persona, History | All actors via tools/implementations.py |
| sections/task_state.py | `TaskStateSection`, `TaskStateEntry`, `TaskStatus` | fsm/task_bridge.py |
| sections/task_artifacts.py | `TaskArtifactsSection`, `TaskArtifactEntry`, `ArtifactType` | fsm/task_bridge.py |

**Internal wiring status:** COMPLETE.

---

### 2.5 `fabric/` -- Capability Registry (LEAF)

```
demo_capabilities.py -----> capability_registry.py
```

| File | Provides | Used By |
|------|----------|---------|
| [capability_registry.py](../poc/k1_poc/fabric/capability_registry.py) | `CapabilityRegistry`, `create_demo_registry()` | kernel/bootstrap.py |
| [demo_capabilities.py](../poc/k1_poc/fabric/demo_capabilities.py) | `DEMO_CAPABILITIES` list | capability_registry.py |

**Internal wiring status:** COMPLETE.

---

### 2.6 `experience/` -- Experience Layer (LEAF)

```
emotional_processor.py --+
affective_mirror.py -----+
narrative_weaver.py -----+---> layer.py (ExperienceLayer)
anticipatory_responder.py+
proactive_agent.py ------+
rhythm_controller.py ----+
```

| File | Provides | Used By |
|------|----------|---------|
| [layer.py](../poc/k1_poc/experience/layer.py) | `ExperienceLayer.tick()` | kernel/bootstrap.py |
| 6 component files | Individual processors | layer.py |

**Internal wiring status:** COMPLETE.

---

### 2.7 `delta/` -- Delta Aggregation Pipeline (LEAF)

```
session_delta.py --> emitters.py --> aggregator.py --> applicator.py
                                          |
                     topics.py       snapshot_reader.py
                                     writer_registry.py
                                     overflow.py
```

| File | Provides | Used By |
|------|----------|---------|
| [session_delta.py](../poc/k1_poc/delta/session_delta.py) | `SessionDelta` dataclass | emitters.py, aggregator.py |
| [emitters.py](../poc/k1_poc/delta/emitters.py) | `emit_artifact()`, `emit_task_state_change()` | actors/back.py (indirectly via bus) |
| [aggregator.py](../poc/k1_poc/delta/aggregator.py) | `DeltaAggregator` (batch window 500ms) | kernel/bootstrap.py |
| [applicator.py](../poc/k1_poc/delta/applicator.py) | `DeltaApplicator` (preflight/write/notify callbacks) | kernel/bootstrap.py |
| [topics.py](../poc/k1_poc/delta/topics.py) | `ARTIFACT_CREATED`, `TASK_STATE_CHANGED`, `STATE_UPDATED` | kernel/bootstrap.py |
| [writer_registry.py](../poc/k1_poc/delta/writer_registry.py) | `enforce_writer()`, `SECTION_WRITERS` | (validation) |
| [snapshot_reader.py](../poc/k1_poc/delta/snapshot_reader.py) | `SnapshotReader` | (state reads) |
| [overflow.py](../poc/k1_poc/delta/overflow.py) | `SectionOverflowHandler` | applicator.py |

**Internal wiring status:** COMPLETE.

---

### 2.8 `prompt/` -- Prompt Assembly (depends on: llm/)

```
mode.py ------+
sections.py --+
affect.py ----+---> builder.py (DynamicPromptBuilder)
clarify_depth-+
domain_rules -+
scenario_templates+
back_prompt.py (standalone for Back LLM)
```

| File | Provides | Used By |
|------|----------|---------|
| [mode.py](../poc/k1_poc/prompt/mode.py) | `PromptMode`, `determine_mode()`, `TOOL_ALLOWLIST`, `get_tool_allowlist()` | actors/front.py, builder.py |
| [builder.py](../poc/k1_poc/prompt/builder.py) | `DynamicPromptBuilder.build()` -> `BuiltContext` | actors/front.py |
| [affect.py](../poc/k1_poc/prompt/affect.py) | `compute_affect_band()`, `AffectBand`, `AffectModifiers` | actors/front.py, builder.py |
| [sections.py](../poc/k1_poc/prompt/sections.py) | `PROMPT_SECTIONS`, `MODE_SECTIONS`, `MODE_EXAMPLES` | builder.py |
| [back_prompt.py](../poc/k1_poc/prompt/back_prompt.py) | `build_back_prompt()` | actors/back.py |
| [domain_rules.py](../poc/k1_poc/prompt/domain_rules.py) | `get_domain_rules()`, `DOMAIN_RULES` | builder.py |
| [clarify_depth.py](../poc/k1_poc/prompt/clarify_depth.py) | `ClarificationTracker`, `get_clarify_depth_block()` | builder.py |
| [scenario_templates.py](../poc/k1_poc/prompt/scenario_templates.py) | `SCENARIO_DATA_TEMPLATES` | builder.py |

**Internal wiring status:** COMPLETE.

---

### 2.9 `react/` -- ReAct Loop Engine (depends on: llm/, tools/)

```
history.py -----> loop.py
```

| File | Provides | Used By |
|------|----------|---------|
| [loop.py](../poc/k1_poc/react/loop.py) | `react_loop()` -> `ReactResult` | actors/front.py, actors/back.py |
| [history.py](../poc/k1_poc/react/history.py) | `build_chat_history()`, `build_chat_history_for_back()` | actors/back.py |

**Internal wiring status:** COMPLETE.

---

### 2.10 `tools/` -- Tool Dispatch (depends on: llm/, task/)

```
schemas_front.py --+
schemas_back.py ---+---> dispatcher.py
                   |        |
implementations.py-+        |
result_protocol.py-+    parallelism.py
```

| File | Provides | Used By |
|------|----------|---------|
| [schemas_front.py](../poc/k1_poc/tools/schemas_front.py) | `FRONT_TOOL_SCHEMAS` (10 ToolSchema objects) | actors/front.py, kernel/bootstrap.py |
| [schemas_back.py](../poc/k1_poc/tools/schemas_back.py) | `BACK_TOOL_SCHEMAS` (6 ToolSchema objects), `BACK_TIER_ALLOWLISTS` | actors/back.py |
| [dispatcher.py](../poc/k1_poc/tools/dispatcher.py) | `ToolDispatcher`, `create_front_dispatcher()`, `create_back_dispatcher()` | kernel/bootstrap.py, react/loop.py |
| [implementations.py](../poc/k1_poc/tools/implementations.py) | `ToolContext`, `execute_tool()`, `TOOL_REGISTRY` (16 tools) | dispatcher.py |
| [result_protocol.py](../poc/k1_poc/tools/result_protocol.py) | `ToolResult`, `tool_result_to_message()` | dispatcher.py, react/loop.py |
| [parallelism.py](../poc/k1_poc/tools/parallelism.py) | `can_parallelize()`, `partition_calls()` | (future parallel tool exec) |

**Internal wiring status:** COMPLETE.

---

### 2.11 `orchestrator/` -- Task Orchestration (depends on: task/)

```
types.py -----> ports.py -----> stub.py
                  |
            interfaces.py     routing.py
                              degradation.py
```

| File | Provides | Used By |
|------|----------|---------|
| [types.py](../poc/k1_poc/orchestrator/types.py) | `TaskEnvelope`, `Budget`, `CapabilityRequest/Result`, `AggregatedResult` | stub.py, ports.py |
| [ports.py](../poc/k1_poc/orchestrator/ports.py) | `IFabricGatewayPort`, `IStateReadPort`, `IDeltaEmitPort` (3 port interfaces) | stub.py, kernel/bootstrap.py |
| [stub.py](../poc/k1_poc/orchestrator/stub.py) | `OrchestratorStub.handle_task()` | kernel/bootstrap.py |
| [routing.py](../poc/k1_poc/orchestrator/routing.py) | `route_task()`, `route_task_sync()` | fsm/controller.py |
| [degradation.py](../poc/k1_poc/orchestrator/degradation.py) | `CircuitBreaker`, `get_effective_tier()` | (resilience) |
| [interfaces.py](../poc/k1_poc/orchestrator/interfaces.py) | `IDAGExecutor`, `IPlannerService` etc. | (MEDIUM+ tier) |

**Internal wiring status:** COMPLETE.

---

### 2.12 `protocols/` -- Complex Flow Protocols (depends on: fsm/, prompt/, task/, bus/, sessionstate/)

```
cancellation.py ----> cancel_events.py ----> cancel_handler.py
suspension.py ------> suspension_events.py -> suspension_manager.py
hitl.py -------------> hitl_coordinator.py --> hitl_flow.py --> hitl_pipeline.py
                                                               hitl_persistence.py
                                                               hitl_wiring.py
weave_batcher.py ----> weave_state.py
```

| File | Provides | Used By |
|------|----------|---------|
| [cancel_handler.py](../poc/k1_poc/protocols/cancel_handler.py) | `CancellationHandler` | fsm/controller.py |
| [suspension_manager.py](../poc/k1_poc/protocols/suspension_manager.py) | `SuspensionManager` | fsm/controller.py |
| [hitl_coordinator.py](../poc/k1_poc/protocols/hitl_coordinator.py) | `HILCoordinator` | kernel/bootstrap.py |
| [hitl_wiring.py](../poc/k1_poc/protocols/hitl_wiring.py) | `build_resume_context()`, `validate_hitl_wiring()` | actors/ |
| [weave_batcher.py](../poc/k1_poc/protocols/weave_batcher.py) | `WeaveBatcher`, `WEAVE_BATCH_WINDOW_MS` | fsm/controller.py |
| [weave_state.py](../poc/k1_poc/protocols/weave_state.py) | `PendingResultsQueue`, `get_weave_action()` | fsm/controller.py |

**Internal wiring status:** COMPLETE.

---

### 2.13 `fsm/` -- Finite State Machine Controller (HUB -- depends on: bus/, orchestrator/, protocols/, sessionstate/, task/)

```
states.py ---------> transition_table.py ------+
                                                |
front_lock.py -------> controller.py <----------+
phase1.py ----------->     |
turn_state.py ---------->  |
history_writer.py -------> |
task_bridge.py ----------> |
control_extension.py ----> |
interrupt_handler.py ----> |
errors.py -------> (used by controller + front_lock)
```

| File | Provides | Used By |
|------|----------|---------|
| [states.py](../poc/k1_poc/fsm/states.py) | `ConciergeState` (12 states enum) | transition_table.py, controller.py, actors/* |
| [transition_table.py](../poc/k1_poc/fsm/transition_table.py) | `TRANSITION_TABLE`, `is_legal()`, `target_state()`, 5 triggers | controller.py |
| [controller.py](../poc/k1_poc/fsm/controller.py) | `ConciergeController` (1285 lines), `TypedHistoryEntry` | kernel/bootstrap.py |
| [front_lock.py](../poc/k1_poc/fsm/front_lock.py) | `FrontLock` (concurrency gate) | controller.py |
| [phase1.py](../poc/k1_poc/fsm/phase1.py) | `Phase1Pipeline`, `StubPhase1Pipeline`, `TurnLock` | controller.py |
| [turn_state.py](../poc/k1_poc/fsm/turn_state.py) | `FSMTurnState` (pending_results, cancelled_tasks) | controller.py |
| [history_writer.py](../poc/k1_poc/fsm/history_writer.py) | `HistoryWriter`, history conversion functions | controller.py |
| [task_bridge.py](../poc/k1_poc/fsm/task_bridge.py) | `TaskBridge` (SS task lifecycle) | controller.py |
| [control_extension.py](../poc/k1_poc/fsm/control_extension.py) | `ConciergeControlExtension` | controller.py |
| [interrupt_handler.py](../poc/k1_poc/fsm/interrupt_handler.py) | `InterruptClassifier`, `CancelTracker`, `ProactiveWakeHandler` | controller.py |
| [errors.py](../poc/k1_poc/fsm/errors.py) | `IllegalTransitionError`, `FrontLockOverflowError` | controller.py |

**Internal wiring status:** COMPLETE.

---

### 2.14 `actors/` -- LLM Actor Handlers (depends on: bus/, llm/, prompt/, react/, task/, tools/)

```
front.py (731 lines) -- Front LLM handler (The Voice)
back.py  (869 lines) -- Back LLM handler  (The Worker)
```

| File | Provides | Used By |
|------|----------|---------|
| [front.py](../poc/k1_poc/actors/front.py) | `front_handler()`, `subscribe_front_events()`, `emit_task_cancel()`, `emit_task_resume()` | kernel/bootstrap.py (mailbox consumer) |
| [back.py](../poc/k1_poc/actors/back.py) | `back_handler()`, `back_resume_handler()`, `back_cancel_handler()`, `subscribe_back_events()` | kernel/bootstrap.py (mailbox consumer) |

**Internal wiring status:** COMPLETE.

---

### 2.15 `kernel/` -- Bootstrap & Runtime (HUB -- depends on everything)

```
bootstrap.py -----> runner.py
```

| File | Provides | Used By |
|------|----------|---------|
| [bootstrap.py](../poc/k1_poc/kernel/bootstrap.py) | `start_kernel()` -> `KernelRuntime`, `stop_kernel()`, `KernelConfig` | demo/coordinator.py, runner.py, tests |
| [runner.py](../poc/k1_poc/kernel/runner.py) | CLI entry point: `python -m poc.k1_poc.kernel.runner` | standalone use |

**Internal wiring status:** COMPLETE.

---

### 2.16 `demo/` -- Demo Coordinator (TOP -- depends on kernel/)

```
smith_family.py --------+
preloaded_memories.py --+
iot_stubs.py -----------+---> coordinator.py ---> runner.py / interactive.py
output_channel.py ------+                             |
display.py -------------+                        _e2e_smoke.py
```

**Internal wiring status:** COMPLETE.

---

## PART 3: Inter-Folder Wiring Checklist

### 3.1 Bus -> Everything (Foundation Layer)

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| B1 | bus/topics.py | fsm/controller.py | 18 TOPIC_* constants | WIRED |
| B2 | bus/topics.py | fsm/transition_table.py | 10 TOPIC_* constants | WIRED |
| B3 | bus/topics.py | actors/front.py | Topic string matching | WIRED (via bus/builders) |
| B4 | bus/topics.py | actors/back.py | Topic string matching | WIRED (via bus/builders) |
| B5 | bus/builders.py | actors/front.py | `build_ack`, `build_final_response`, `build_task_dispatch`, `build_task_cancel`, `build_task_resume`, `build_response_stream` | WIRED |
| B6 | bus/builders.py | actors/back.py | `build_task_complete`, `build_task_failed`, `build_task_suspended`, `build_tool_started`, `build_tool_completed`, `build_artifact_created` | WIRED |
| B7 | bus/builders.py | fsm/controller.py | `build_state_updated`, `build_task_failed`, `build_turn_completed`, `build_turn_started` | WIRED |
| B8 | bus/setup.py | main.py | `create_poc_bus()`, `create_poc_router()`, `register_poc_actors()` | WIRED |

### 3.2 LLM -> Actors & React (Model Layer)

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| L1 | llm/ports.py | actors/front.py | `IConciergeModelPort` type annotation | WIRED |
| L2 | llm/ports.py | actors/back.py | `IConciergeModelPort` type annotation | WIRED |
| L3 | llm/ports.py | react/loop.py | `IConciergeModelPort` parameter | WIRED |
| L4 | llm/types.py | react/loop.py | `ModelMessage`, `ToolCallResult`, `ConciergeModelRequest/Response` | WIRED |
| L5 | llm/types.py | tools/dispatcher.py | `ToolCallResult`, `ToolSchema` | WIRED |
| L6 | llm/types.py | actors/front.py | `ModelMessage` | WIRED |
| L7 | llm/types.py | actors/back.py | `ModelMessage` | WIRED |
| L8 | llm/validator.py | actors/front.py | `LLMOutputValidator` | WIRED |
| L9 | llm/validator.py | actors/back.py | `LLMOutputValidator` | WIRED |
| L10 | llm/validator.py | react/loop.py | `LLMOutputValidator`, `ValidationResult` | WIRED |

### 3.3 Tools -> Actors & React (Execution Layer)

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| T1 | tools/dispatcher.py | actors/front.py | `ToolDispatcher` instance | WIRED (via bootstrap) |
| T2 | tools/dispatcher.py | actors/back.py | `ToolDispatcher` instance | WIRED (via bootstrap) |
| T3 | tools/dispatcher.py | react/loop.py | `ToolDispatcher` parameter | WIRED |
| T4 | tools/implementations.py | kernel/bootstrap.py | `ToolContext` dataclass | WIRED |
| T5 | tools/schemas_front.py | kernel/bootstrap.py | `FRONT_TOOL_SCHEMAS` | WIRED |
| T6 | tools/schemas_back.py | actors/back.py | `BACK_TOOL_SCHEMAS`, `BACK_TIER_ALLOWLISTS` | WIRED |
| T7 | tools/result_protocol.py | react/loop.py | `ToolResult`, `tool_result_to_message()` | WIRED |

### 3.4 Prompt -> Actors (Context Assembly Layer)

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| P1 | prompt/mode.py | actors/front.py | `PromptMode`, `determine_mode()` | WIRED |
| P2 | prompt/builder.py | actors/front.py | `DynamicPromptBuilder.build()` -> `BuiltContext` | WIRED |
| P3 | prompt/affect.py | actors/front.py | `compute_affect_band()` | WIRED |
| P4 | prompt/back_prompt.py | actors/back.py | `build_back_prompt()` | WIRED |

### 3.5 Task -> Tools & FSM (Task Data Layer)

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| K1 | task/complexity.py | actors/front.py | `ComplexityTier`, `budget_for_tier()` | WIRED |
| K2 | task/complexity.py | tools/implementations.py | `ComplexityTier` | WIRED |
| K3 | task/dispatch.py | tools/implementations.py | `TaskDispatch` | WIRED |
| K4 | task/intent.py | tools/implementations.py | `TaskIntent` | WIRED |
| K5 | task/dispatch.py | fsm/controller.py | `TaskDispatch` | WIRED |
| K6 | task/intent.py | fsm/controller.py | `TaskIntent` | WIRED |
| K7 | task/complexity.py | fsm/controller.py | `ComplexityTier` | WIRED |

### 3.6 SessionState -> FSM & Tools (State Layer)

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| S1 | sessionstate/factory.py | kernel/bootstrap.py | `SessionStateFactory.create_standalone()` | WIRED |
| S2 | sessionstate/sections/task_state.py | fsm/task_bridge.py | `TaskStateEntry`, `TaskStateSection`, `TaskStatus` | WIRED |
| S3 | sessionstate/sections/task_artifacts.py | fsm/task_bridge.py | `TaskArtifactEntry`, `TaskArtifactsSection`, `ArtifactType` | WIRED |
| S4 | sessionstate/manager.py | tools/implementations.py | SS manager instance (via ToolContext) | WIRED |

### 3.7 Delta -> Bootstrap (State Write Pipeline)

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| D1 | delta/aggregator.py | kernel/bootstrap.py | `DeltaAggregator(flush_fn=applicator.apply)` | WIRED |
| D2 | delta/applicator.py | kernel/bootstrap.py | `DeltaApplicator(preflight_fn, write_fn, notify_fn)` | WIRED |
| D3 | delta/topics.py | kernel/bootstrap.py | `ARTIFACT_CREATED`, `TASK_STATE_CHANGED`, `STATE_UPDATED` | WIRED |
| D4 | delta/session_delta.py | kernel/bootstrap.py | `SessionDelta.from_dict()` | WIRED |

### 3.8 Orchestrator -> FSM & Bootstrap

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| O1 | orchestrator/routing.py | fsm/controller.py | `route_task_sync()` | WIRED |
| O2 | orchestrator/stub.py | kernel/bootstrap.py | `OrchestratorStub` instance | WIRED |
| O3 | orchestrator/ports.py | kernel/bootstrap.py | Port adapters (_FabricGatewayAdapter,_StateReadAdapter, _DeltaEmitAdapter) | WIRED |

### 3.9 Protocols -> FSM (Complex Flow Layer)

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| R1 | protocols/cancel_handler.py | fsm/controller.py | `CancellationHandler` | WIRED |
| R2 | protocols/suspension_manager.py | fsm/controller.py | `SuspensionManager` | WIRED |
| R3 | protocols/weave_batcher.py | fsm/controller.py | `WeaveBatcher`, `WEAVE_BATCH_WINDOW_MS` | WIRED |
| R4 | protocols/hitl_coordinator.py | kernel/bootstrap.py | `HILCoordinator` instance | WIRED |

### 3.10 Experience -> Bootstrap

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| E1 | experience/layer.py | kernel/bootstrap.py | `ExperienceLayer()` instance | WIRED |

### 3.11 Fabric -> Bootstrap

| Connection | From | To | What Flows | Status |
|------------|------|----|------------|--------|
| F1 | fabric/capability_registry.py | kernel/bootstrap.py | `create_demo_registry()` | WIRED |

---

## PART 4: Bootstrap Wiring -- The Complete Connection Map

### 4.1 What `start_kernel()` Creates (in order)

```
Step 1: boot() [main.py]
  ├── create_poc_bus(capture)         -> bus       [bus/setup.py -> k1.bus]
  ├── create_poc_router()             -> router    [bus/setup.py -> k1.bus]
  ├── create_poc_session_adapter(bus) -> adapter   [bus/setup.py -> k1.bus]
  └── register_poc_actors(router)     -> front_mailbox, back_mailbox

Step 2: _create_model(cfg)
  ├── IF test_mode  -> TestConciergeAdapter()      [llm/test_adapter.py]
  ├── IF GOOGLE_API_KEY -> GeminiConciergeAdapter() [llm/gemini_adapter.py]
  └── ELSE -> TestConciergeAdapter() (fallback)

Step 3: _create_session_state(cfg)
  ├── IF testing   -> SessionStateFactory.create_for_testing()  [sessionstate/factory.py]
  └── IF standalone -> SessionStateFactory.create_standalone()

Step 4: _create_capability_registry()
  └── create_demo_registry()           [fabric/capability_registry.py]

Step 5: ConciergeController(bus, router)  [fsm/controller.py]
  ├── internally creates: FrontLock, Phase1Pipeline, TaskBridge,
  │   HistoryWriter, InterruptClassifier, CancellationHandler,
  │   SuspensionManager, WeaveBatcher, FSMTurnState
  └── subscribes to bus topics via transition_table

Step 6: ToolContext(front) + ToolContext(back) [tools/implementations.py]
  ├── session_manager   = session_state
  ├── recall_fn         = _build_recall_fn(cfg)
  ├── capability_fn     = _capability_discover(registry)
  └── invoke_fn         = _capability_invoke(registry)

Step 7: create_front_dispatcher(tier, ctx)  [tools/dispatcher.py]
Step 8: create_back_dispatcher(tier, ctx)   [tools/dispatcher.py]

Step 9 (conditional): ExperienceLayer()     [experience/layer.py]

Step 10 (conditional): DeltaAggregator + DeltaApplicator  [delta/]
  ├── DeltaApplicator(preflight_fn, write_fn, notify_fn)
  └── DeltaAggregator(flush_fn=applicator.apply, batch_window_ms=500)

Step 11 (conditional): HILCoordinator       [protocols/hitl_coordinator.py]

Step 12 (conditional): OrchestratorStub     [orchestrator/stub.py]
  ├── fabric_gateway = _FabricGatewayAdapter(registry)
  ├── state_read     = _StateReadAdapter(session_state)
  └── delta_emit     = _DeltaEmitAdapter(aggregator, bus)

Step 13: _mailbox_consumer(runtime)         [kernel/bootstrap.py]
  ├── polls front_mailbox -> front_handler()  [actors/front.py]
  └── polls back_mailbox  -> back_handler()   [actors/back.py]
```

### 4.2 How a User Message Flows End-to-End

```
User Input Text
    |
    v
[1] bus.publish(build_user_input(text))              [bus/builders.py]
    |
    v
[2] TimingChain processes envelope                   [k1.bus.timing]
    |
    v
[3] front_mailbox receives (FRONT_SUBSCRIPTIONS)     [bus/topics.py]
    |
    v
[4] _mailbox_consumer -> front_handler()             [kernel/bootstrap.py -> actors/front.py]
    |
    v
[5] _parse_payload(envelope)                         [actors/front.py]
    |
    v
[6] determine_mode(fsm_state, topic, ss_signals)     [prompt/mode.py]
    |  -> PromptMode.STANDARD (typical first turn)
    v
[7] compute_affect_band(ss.affective_now)            [prompt/affect.py]
    |
    v
[8] DynamicPromptBuilder.build(mode, ss, ...)        [prompt/builder.py]
    |  -> BuiltContext(system_prompt, messages, tools, max_iterations)
    v
[9] react_loop(                                      [react/loop.py]
        actor="front",
        system_prompt=built.system_prompt,
        messages=built.messages,
        tools=built.tools,
        max_iterations=built.max_iterations,
        model=model,                                  [llm/ports.py impl]
        tool_dispatcher=front_dispatcher,             [tools/dispatcher.py]
        on_ack=<callback>,
        on_text_response=<callback>,
    )
    |
    +-- Iteration 1: model.generate()
    |     -> tool_call: acknowledge("Got it!")
    |     -> ToolDispatcher.dispatch("acknowledge", {...})
    |       -> execute_tool("acknowledge", ctx, {...})  [tools/implementations.py]
    |     -> on_ack callback fires
    |     -> bus.publish(build_ack(...))                [bus/builders.py]
    |
    +-- Iteration 2: model.generate()
    |     -> tool_calls: update_beliefs(...), update_scoreboard(...)
    |     -> ToolDispatcher.dispatch() x2
    |       -> execute_tool() x2 -> SS writes
    |
    +-- Iteration 3: model.generate()
    |     -> tool_call: dispatch_task({intents: [...]})
    |     -> ToolDispatcher.dispatch("dispatch_task", {...})
    |       -> execute_tool("dispatch_task", ctx, {...})
    |         -> returns {queued: true, task_id: "task-XYZ"}
    |     -> FSM intercepts dispatch_task result
    |     -> bus.publish(build_task_dispatch(...))      [bus/builders.py]
    |
    +-- Iteration 4: model.generate()
    |     -> text: "I'll look into that for you!"
    |     -> on_text_response callback fires
    |     -> bus.publish(build_final_response(...))     [bus/builders.py]
    |
    v
[10] ReactResult(status="complete", text="I'll look into that...")
    |
    v
[11] FSM transitions: DISPATCHING -> COMPANIONING     [fsm/controller.py]
    |
    v
[12] back_mailbox receives task.dispatch envelope      [bus routing]
    |
    v
[13] _mailbox_consumer -> back_handler()               [kernel/bootstrap.py -> actors/back.py]
    |
    v
[14] build_back_prompt(task_payload, ss_snapshot)       [prompt/back_prompt.py]
    |
    v
[15] react_loop(actor="back", ...)                     [react/loop.py]
    |
    +-- Iteration 1: model.generate()
    |     -> tool_call: invoke_capability("tool.execute.hotel_search", {...})
    |     -> bus.publish(build_tool_started(...))
    |     -> ToolDispatcher.dispatch("invoke_capability", {...})
    |       -> execute_tool("invoke_capability", ctx, {...})
    |         -> CapabilityRegistry.invoke(name, params)  [fabric/capability_registry.py]
    |     -> bus.publish(build_tool_completed(...))
    |
    +-- Iteration 2: model.generate()
    |     -> tool_call: submit_result({result_type: "complete", results: {...}})
    |     -> ToolDispatcher.dispatch("submit_result", {...})
    |
    v
[16] ReactResult from back
    |
    v
[17] bus.publish(build_task_complete(...))              [actors/back.py -> bus/builders.py]
    |
    v
[18] DeltaAggregator collects deltas (500ms window)    [delta/aggregator.py]
    |   -> DeltaApplicator.apply()                     [delta/applicator.py]
    |     -> SS writes (task_state, task_artifacts)
    |     -> bus.publish(build_state_updated(...))
    |
    v
[19] front_mailbox receives task.complete              [bus routing]
    |
    v
[20] front_handler() with PromptMode.PRESENT           [actors/front.py]
    |
    v
[21] react_loop(actor="front", mode=PRESENT)           [react/loop.py]
    |   -> text: "Here's what I found: ..."
    |   -> bus.publish(build_final_response(...))
    |
    v
[22] FSM transitions: DELIVERING -> LISTENING          [fsm/controller.py]
    |
    v
[23] Check pending_results queue                       [fsm/turn_state.py]
    |   IF non-empty -> WEAVING state
    |   IF empty -> LISTENING (idle)
    |
    v
DONE -- System idle, waiting for next user input
```

---

## PART 5: Per-Connection Verification Checklist

### Check each connection exists and works

#### TIER 1: Foundation (must work first)

| # | Check | Files Involved | How to Verify | Status |
|---|-------|----------------|---------------|--------|
| 1 | Bus creates with TimingChain | bus/setup.py, k1.bus | `boot(ordered=True)` returns bus | CHECK |
| 2 | Mailbox router registers 2 actors | bus/setup.py | `register_poc_actors()` returns 2 mailboxes | CHECK |
| 3 | Topics match builders | bus/topics.py, bus/builders.py | Every TOPIC_* has a matching `build_*` function | CHECK |
| 4 | Envelope publish + receive | bus/setup.py | Publish envelope -> receive from correct mailbox | CHECK |
| 5 | SessionState creates (standalone) | sessionstate/factory.py | `SessionStateFactory.create_standalone()` returns manager | CHECK |
| 6 | SessionState creates (testing) | sessionstate/factory.py | `SessionStateFactory.create_for_testing()` returns manager | CHECK |
| 7 | All 10 HOT sections accessible | sessionstate/sections/ | `ss.get_section("beliefs_active")` etc. all work | CHECK |
| 8 | LLM adapter creates (test) | llm/test_adapter.py | `TestConciergeAdapter()` implements IConciergeModelPort | CHECK |
| 9 | LLM adapter creates (gemini) | llm/gemini_adapter.py | `GeminiConciergeAdapter(key)` implements IConciergeModelPort | CHECK |
| 10 | Capability registry creates | fabric/capability_registry.py | `create_demo_registry()` has capabilities | CHECK |

#### TIER 2: Tool Layer (must work before actors)

| # | Check | Files Involved | How to Verify | Status |
|---|-------|----------------|---------------|--------|
| 11 | ToolContext creates for front | tools/implementations.py | Construct ToolContext(actor="front", ...) | CHECK |
| 12 | ToolContext creates for back | tools/implementations.py | Construct ToolContext(actor="back", ...) | CHECK |
| 13 | Front dispatcher creates | tools/dispatcher.py | `create_front_dispatcher(tier="LOW", ctx=...)` | CHECK |
| 14 | Back dispatcher creates | tools/dispatcher.py | `create_back_dispatcher(tier="LOW", ctx=...)` | CHECK |
| 15 | All 10 front tools registered | tools/implementations.py | TOOL_REGISTRY has all 10 front tool names | CHECK |
| 16 | All 6 back tools registered | tools/implementations.py | TOOL_REGISTRY has all 6 back tool names | CHECK |
| 17 | acknowledge() executes | tools/implementations.py | `execute_tool("acknowledge", ctx, {"message": "hi"})` | CHECK |
| 18 | update_beliefs() writes SS | tools/implementations.py | Verify beliefs_active section updated | CHECK |
| 19 | dispatch_task() returns task_id | tools/implementations.py | Returns `{queued: true, task_id: ...}` | CHECK |
| 20 | invoke_capability() calls fabric | tools/implementations.py | Calls registry.invoke() | CHECK |
| 21 | submit_result() returns result | tools/implementations.py | Returns structured result | CHECK |
| 22 | FRONT_TOOL_SCHEMAS has 10 entries | tools/schemas_front.py | `len(FRONT_TOOL_SCHEMAS) == 10` | CHECK |
| 23 | BACK_TOOL_SCHEMAS has 6 entries | tools/schemas_back.py | `len(BACK_TOOL_SCHEMAS) == 6` | CHECK |

#### TIER 3: Prompt & React Layer (must work before actors)

| # | Check | Files Involved | How to Verify | Status |
|---|-------|----------------|---------------|--------|
| 24 | PromptMode enum has 10 values | prompt/mode.py | `len(PromptMode) == 10` | CHECK |
| 25 | determine_mode() resolves correctly | prompt/mode.py | STANDARD for user.input + LISTENING | CHECK |
| 26 | TOOL_ALLOWLIST covers all 10 modes | prompt/mode.py | Every PromptMode key in TOOL_ALLOWLIST | CHECK |
| 27 | DynamicPromptBuilder.build() succeeds | prompt/builder.py | Returns BuiltContext with all fields | CHECK |
| 28 | build_back_prompt() succeeds | prompt/back_prompt.py | Returns system prompt string | CHECK |
| 29 | react_loop() completes for front | react/loop.py | Returns ReactResult with text | CHECK |
| 30 | react_loop() completes for back | react/loop.py | Returns ReactResult with data | CHECK |
| 31 | react_loop respects max_iterations | react/loop.py | Stops at limit | CHECK |
| 32 | react_loop calls on_ack callback | react/loop.py | Callback fires on acknowledge() | CHECK |
| 33 | react_loop calls on_text_response | react/loop.py | Callback fires on final text | CHECK |

#### TIER 4: FSM Layer (must work before bootstrap connects actors)

| # | Check | Files Involved | How to Verify | Status |
|---|-------|----------------|---------------|--------|
| 34 | ConciergeState has 12 states | fsm/states.py | `len(ConciergeState) == 12` | CHECK |
| 35 | TRANSITION_TABLE covers all states | fsm/transition_table.py | All 12 states have entries | CHECK |
| 36 | ConciergeController creates | fsm/controller.py | `ConciergeController(bus, router)` | CHECK |
| 37 | FrontLock serializes events | fsm/front_lock.py | try_deliver when busy=False works | CHECK |
| 38 | FrontLock queues when busy | fsm/front_lock.py | try_deliver when busy=True queues | CHECK |
| 39 | Phase1Pipeline runs | fsm/phase1.py | StubPhase1Pipeline returns Phase1Result | CHECK |
| 40 | TaskBridge dispatch_task() | fsm/task_bridge.py | Creates TaskStateEntry in SS | CHECK |
| 41 | TaskBridge complete_task() | fsm/task_bridge.py | Updates status to COMPLETED | CHECK |
| 42 | HistoryWriter writes entries | fsm/history_writer.py | TypedHistoryEntry stored and retrievable | CHECK |
| 43 | FSMTurnState tracks pending | fsm/turn_state.py | pending_results deque works | CHECK |

#### TIER 5: Delta Pipeline (must work for Back -> SS communication)

| # | Check | Files Involved | How to Verify | Status |
|---|-------|----------------|---------------|--------|
| 44 | SessionDelta creates | delta/session_delta.py | `SessionDelta(section, key, op, data)` | CHECK |
| 45 | DeltaAggregator collects | delta/aggregator.py | `aggregator.collect(delta)` | CHECK |
| 46 | DeltaAggregator deduplicates | delta/aggregator.py | Duplicate deltas merged | CHECK |
| 47 | DeltaAggregator flushes to applicator | delta/aggregator.py | flush() calls applicator.apply() | CHECK |
| 48 | DeltaApplicator writes SS | delta/applicator.py | SS section updated after apply() | CHECK |
| 49 | DeltaApplicator emits notification | delta/applicator.py | bus gets STATE_UPDATED event | CHECK |
| 50 | emit_artifact() creates delta | delta/emitters.py | Returns SessionDelta | CHECK |
| 51 | emit_task_state_change() creates delta | delta/emitters.py | Returns SessionDelta | CHECK |

#### TIER 6: Protocol Layer (complex flows)

| # | Check | Files Involved | How to Verify | Status |
|---|-------|----------------|---------------|--------|
| 52 | CancellationHandler processes cancel | protocols/cancel_handler.py | Handles cancel event | CHECK |
| 53 | SuspensionManager tracks suspensions | protocols/suspension_manager.py | Suspend/resume lifecycle | CHECK |
| 54 | HILCoordinator creates | protocols/hitl_coordinator.py | HILCoordinator(callbacks) | CHECK |
| 55 | WeaveBatcher batches results | protocols/weave_batcher.py | Collects pending results | CHECK |
| 56 | PendingResultsQueue drains | protocols/weave_state.py | get_weave_action() returns correct action | CHECK |

#### TIER 7: Orchestrator (MEDIUM+ tier)

| # | Check | Files Involved | How to Verify | Status |
|---|-------|----------------|---------------|--------|
| 57 | OrchestratorStub creates with 3 ports | orchestrator/stub.py | All 3 adapters connect | CHECK |
| 58 | OrchestratorStub.handle_task() | orchestrator/stub.py | Returns AggregatedResult | CHECK |
| 59 | route_task_sync() routes correctly | orchestrator/routing.py | LOW bypasses orchestrator | CHECK |
| 60 | CircuitBreaker degrades tier | orchestrator/degradation.py | Trips after threshold | CHECK |

#### TIER 8: Actor Handlers (Front & Back)

| # | Check | Files Involved | How to Verify | Status |
|---|-------|----------------|---------------|--------|
| 61 | front_handler() processes user.input | actors/front.py | Envelope -> ack + response | CHECK |
| 62 | front_handler() dispatches task | actors/front.py | dispatch_task tool -> bus event | CHECK |
| 63 | front_handler() presents results | actors/front.py | task.complete -> PRESENT mode | CHECK |
| 64 | front_handler() handles HITL relay | actors/front.py | task.suspended -> HITL_RELAY | CHECK |
| 65 | back_handler() processes task.dispatch | actors/back.py | Envelope -> tool calls -> submit_result | CHECK |
| 66 | back_handler() emits tool events | actors/back.py | tool_started + tool_completed events | CHECK |
| 67 | back_handler() emits task.complete | actors/back.py | submit_result -> build_task_complete | CHECK |
| 68 | back_handler() emits task.failed | actors/back.py | Error -> build_task_failed | CHECK |
| 69 | back_handler() emits task.suspended | actors/back.py | needs_human -> build_task_suspended | CHECK |
| 70 | back_resume_handler() resumes | actors/back.py | task.resume -> continue execution | CHECK |

#### TIER 9: Bootstrap Assembly (everything comes together)

| # | Check | Files Involved | How to Verify | Status |
|---|-------|----------------|---------------|--------|
| 71 | start_kernel() completes | kernel/bootstrap.py | Returns KernelRuntime with started=True | CHECK |
| 72 | KernelRuntime has all components | kernel/bootstrap.py | bus, router, model, ss, fsm, dispatchers all non-None | CHECK |
| 73 | _mailbox_consumer polls both | kernel/bootstrap.py | Consumer task is running | CHECK |
| 74 | front_mailbox -> front_handler wired | kernel/bootstrap.py | Consumer calls front_handler with correct args | CHECK |
| 75 | back_mailbox -> back_handler wired | kernel/bootstrap.py | Consumer calls back_handler with correct args | CHECK |
| 76 | Delta pipeline connected | kernel/bootstrap.py | Aggregator -> Applicator -> SS | CHECK |
| 77 | Orchestrator connected | kernel/bootstrap.py | Stub has 3 live port adapters | CHECK |
| 78 | Experience layer connected | kernel/bootstrap.py | ExperienceLayer() created | CHECK |
| 79 | HITL coordinator connected | kernel/bootstrap.py | HILCoordinator has callbacks | CHECK |
| 80 | stop_kernel() cleans up | kernel/bootstrap.py | Consumer cancelled, delta flushed, FSM torn down | CHECK |

#### TIER 10: End-to-End Flows

| # | Check | Flow | How to Verify | Status |
|---|-------|------|---------------|--------|
| 81 | Simple conversation (no task) | user.input -> ack -> final -> LISTENING | Front returns text without dispatch_task | CHECK |
| 82 | Task dispatch + complete | user.input -> ack -> dispatch -> Back runs -> complete -> present -> LISTENING | Full round trip | CHECK |
| 83 | Clarification flow | user.input -> ambiguity detected -> clarify_ask -> user answers -> clarify_resolve -> dispatch | CLARIFYING_USER states | CHECK |
| 84 | HITL suspension flow | task dispatched -> Back suspends -> Front relays -> user answers -> Back resumes | CLARIFYING_WORKER states | CHECK |
| 85 | Cancellation flow | task running -> user says cancel -> task.cancel -> Back stops -> confirm cancel | CANCELLING state | CHECK |
| 86 | Interrupt flow | task running -> new user.input -> interrupt handler -> classify -> respond | INTERRUPT_HANDLING state | CHECK |
| 87 | Weave flow | task completes while Front busy -> pending_results -> WEAVING -> weave response | WEAVING state | CHECK |
| 88 | Error presentation | Back fails -> task.failed -> Front presents error gracefully | ERROR mode | CHECK |
| 89 | Multi-turn conversation | Multiple turns with belief accumulation | Beliefs persist across turns | CHECK |
| 90 | Tier escalation | LOW -> MEDIUM with orchestrator | OrchestratorStub handles task | CHECK |

---

## PART 6: File Chain Summary (file1 -> file2 -> file3 -> ... -> bootstrap.py)

### Chain A: User Input to Front Handler

```
bus/topics.py -> bus/builders.py -> bus/setup.py -> main.py -> kernel/bootstrap.py
                                                                    |
                                                              _mailbox_consumer
                                                                    |
                                                              actors/front.py
```

### Chain B: Front Handler Internal Flow

```
actors/front.py -> prompt/mode.py (determine_mode)
               -> prompt/affect.py (compute_affect_band)
               -> prompt/builder.py (DynamicPromptBuilder.build)
                    -> prompt/sections.py
                    -> prompt/domain_rules.py
                    -> prompt/scenario_templates.py
                    -> prompt/clarify_depth.py
               -> react/loop.py (react_loop)
                    -> llm/ports.py (model.generate)
                    -> tools/dispatcher.py (ToolDispatcher.dispatch)
                         -> tools/implementations.py (execute_tool)
                              -> tools/result_protocol.py (ToolResult)
               -> bus/builders.py (build_ack, build_final_response, build_task_dispatch)
```

### Chain C: Task Dispatch to Back Handler

```
actors/front.py -> bus/builders.py (build_task_dispatch)
               -> kernel/bootstrap.py (_mailbox_consumer)
               -> actors/back.py (back_handler)
                    -> prompt/back_prompt.py (build_back_prompt)
                    -> react/loop.py (react_loop)
                         -> llm/ports.py (model.generate)
                         -> tools/dispatcher.py (ToolDispatcher.dispatch)
                              -> tools/implementations.py (execute_tool)
                                   -> fabric/capability_registry.py (registry.invoke)
                    -> bus/builders.py (build_task_complete, build_tool_*)
```

### Chain D: Task Complete to Presentation

```
actors/back.py -> bus/builders.py (build_task_complete)
              -> kernel/bootstrap.py (_mailbox_consumer)
              -> actors/front.py (front_handler, mode=PRESENT)
                   -> prompt/builder.py (PromptMode.PRESENT)
                   -> react/loop.py
                   -> bus/builders.py (build_final_response)
```

### Chain E: Delta Pipeline (Back -> Session State)

```
actors/back.py -> bus (artifact/state events)
              -> kernel/bootstrap.py (_DeltaEmitAdapter)
              -> delta/session_delta.py (SessionDelta)
              -> delta/aggregator.py (DeltaAggregator.collect)
              -> delta/aggregator.py (DeltaAggregator.flush)
              -> delta/applicator.py (DeltaApplicator.apply)
              -> sessionstate/manager.py (section writes)
              -> bus (build_state_updated notification)
```

### Chain F: FSM State Management

```
fsm/states.py -> fsm/transition_table.py -> fsm/controller.py
                                               |
                 fsm/front_lock.py ------------+
                 fsm/phase1.py ----------------+
                 fsm/turn_state.py ------------+
                 fsm/history_writer.py --------+
                 fsm/task_bridge.py -----------+
                 fsm/control_extension.py -----+
                 fsm/interrupt_handler.py -----+
                                               |
                 protocols/cancel_handler.py --+
                 protocols/suspension_manager -+
                 protocols/weave_batcher.py ---+
                                               |
                 orchestrator/routing.py ------+
```

### Chain G: Bootstrap Assembles Everything

```
kernel/bootstrap.py
  |
  +-- main.py (boot)
  |     +-- bus/setup.py -> k1.bus.*
  |
  +-- llm/test_adapter.py OR llm/gemini_adapter.py
  |
  +-- sessionstate/factory.py -> sessionstate/manager.py -> sessionstate/sections/*
  |
  +-- fabric/capability_registry.py -> fabric/demo_capabilities.py
  |
  +-- fsm/controller.py -> (all fsm/* files)
  |     +-- orchestrator/routing.py
  |     +-- protocols/cancel_handler.py
  |     +-- protocols/suspension_manager.py
  |     +-- protocols/weave_batcher.py
  |
  +-- tools/implementations.py (ToolContext)
  +-- tools/dispatcher.py (create_front/back_dispatcher)
  |
  +-- experience/layer.py (ExperienceLayer)
  |
  +-- delta/aggregator.py + delta/applicator.py
  |
  +-- protocols/hitl_coordinator.py
  |
  +-- orchestrator/stub.py (OrchestratorStub with 3 port adapters)
  |
  +-- actors/front.py (front_handler) via _mailbox_consumer
  +-- actors/back.py  (back_handler)  via _mailbox_consumer
```

---

## PART 7: Known Wiring Issues / Risks

| # | Issue | Severity | Location | Notes |
|---|-------|----------|----------|-------|
| 1 | `fsm/__init__.py` re-exports from `delta/` and `protocols/` | LOW | fsm/**init**.py | Misleading -- makes fsm look like it owns delta/protocol types |
| 2 | `fsm/task_bridge.py` imports directly from sessionstate/sections/ | MEDIUM | fsm/task_bridge.py | Tight coupling to SS internal section classes |
| 3 | Bidirectional dep fsm <-> protocols | MEDIUM | Multiple files | Not circular (different files) but tightly coupled |
| 4 | `protocols/hitl_wiring.py` imports from prompt/ | LOW | protocols/hitl_wiring.py | Couples HITL config to prompt assembly |
| 5 | _mailbox_consumer has no FSM integration | HIGH | kernel/bootstrap.py | Consumer calls actors directly, bypasses FSM event routing |
| 6 | HILCoordinator callbacks are no-ops | HIGH | kernel/bootstrap.py L136-142 | `_on_suspended` and `_on_resume` are placeholder lambdas |
| 7 | ExperienceLayer.tick() not called in consumer loop | MEDIUM | kernel/bootstrap.py | Created but never invoked during message processing |
| 8 | FSM not used as event router in consumer | HIGH | kernel/bootstrap.py | Design says FSM routes events; consumer bypasses it |
| 9 | No bus subscriptions wired in bootstrap | HIGH | kernel/bootstrap.py | `subscribe_front_events()` / `subscribe_back_events()` never called |
| 10 | DeltaEmitAdapter not connected to back_handler | MEDIUM | kernel/bootstrap.py | Back actor emits bus events directly, not through aggregator |
