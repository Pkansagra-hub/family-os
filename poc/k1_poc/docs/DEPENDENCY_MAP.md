# K1 POC Dependency Map

> Auto-generated analysis of all Python source files in `poc/k1_poc/`.
> Covers 16 folders, ~145 non-generated `.py` files.
> Generated: 2026-02-23

---

## Table of Contents

1. [Folder Inventory & Exports](#1-folder-inventory--exports)
2. [Per-File Cross-Module Imports](#2-per-file-cross-module-imports)
3. [Bootstrap Dependency Chain](#3-bootstrap-dependency-chain)
4. [Dependency Matrix (folder-to-folder)](#4-dependency-matrix)
5. [External k1.* Dependencies](#5-external-k1-dependencies)
6. [Missing or Broken Import Chains](#6-missing-or-broken-import-chains)

---

## 1. Folder Inventory & Exports

### `actors/` (2 files)

| File | Defines |
|------|---------|
| `front.py` | `front_handler`, `subscribe_front_events`, `emit_task_cancel`, `emit_task_resume`, `_parse_payload`, `_extract_scenario_data`, `_build_resolution` |
| `back.py` | `back_handler`, `back_resume_handler`, `back_cancel_handler`, `subscribe_back_events`, `emit_tool_started`, `emit_tool_completed`, `emit_artifact_created`, `store_pending_context`, `BACK_MAX_ITERATIONS` |

**`__init__.py` exports:** All of the above (full re-export of front.py + back.py public API).

---

### `bus/` (3 files)

| File | Defines |
|------|---------|
| `topics.py` | 28 topic constants (`TOPIC_USER_INPUT`, `TOPIC_TASK_DISPATCH`, etc.), `STRICT_TOPICS`, `RELAXED_TOPICS`, `FRONT_SUBSCRIPTIONS`, `BACK_SUBSCRIPTIONS`, `get_priority` |
| `builders.py` | 28 envelope builder functions (`build_user_input`, `build_task_dispatch`, etc.), `BUILDERS` dict |
| `setup.py` | `create_poc_bus`, `create_poc_router`, `create_poc_session_adapter`, `register_poc_actors`, `ACTOR_FRONT`, `ACTOR_BACK` |

**`__init__.py` exports:** Full re-export of all topics, builders, and setup functions.

---

### `delta/` (7 files)

| File | Defines |
|------|---------|
| `session_delta.py` | `SessionDelta`, `VALID_DELTA_SECTIONS`, `VALID_DELTA_OPERATIONS` |
| `topics.py` | `ARTIFACT_CREATED`, `TASK_STATE_CHANGED`, `STATE_UPDATED`, `ALL_DELTA_TOPICS` |
| `emitters.py` | `emit_artifact`, `emit_task_state_change`, `VALID_TASK_STATUSES` |
| `aggregator.py` | `DeltaAggregator`, `DeltaBatch`, `DEFAULT_BATCH_WINDOW_MS` |
| `applicator.py` | `DeltaApplicator`, `ApplyResult` |
| `writer_registry.py` | `WriterRole`, `SingleWriterViolation`, `SECTION_WRITERS`, `validate_writer`, `enforce_writer` |
| `snapshot_reader.py` | `SectionSnapshot`, `SnapshotReader` |
| `overflow.py` | `SectionOverflowHandler` |

**`__init__.py` exports:** All of the above.

---

### `demo/` (9 files)

| File | Defines |
|------|---------|
| `coordinator.py` | `K1DemoCoordinator`, `get_k1_demo_coordinator`, `reset_coordinator` |
| `coordinator_old.py` | Old version of coordinator (deprecated) |
| `interactive.py` | `InteractiveDemoLoop` |
| `display.py` | Console display helpers (`print_demo_header`, `colorize`, etc.) |
| `output_channel.py` | `OutputChannel`, `TimelineEntry`, `ConsoleRenderer`, `IRenderer` |
| `iot_stubs.py` | `IoTMonitorStub`, `ScriptedIoTEvent`, `register_storyline_capabilities` |
| `smith_family.py` | `SMITH_FAMILY_PROFILE`, `SMITH_SESSION_CONFIG`, `DEVICE_REGISTRY`, `resolve_member` |
| `preloaded_memories.py` | `PRELOADED_MEMORIES` |
| `runner.py` | `main` (entry point: `python -m poc.k1_poc.demo.runner`) |
| `_e2e_smoke.py` | `smoke_test` |

**`__init__.py` exports:** `K1DemoCoordinator`, `get_k1_demo_coordinator` only.

---

### `experience/` (7 files)

| File | Defines |
|------|---------|
| `emotional_processor.py` | `EmotionalProcessor`, `EmotionalTrajectory` |
| `affective_mirror.py` | `AffectiveMirror`, `ToneAdjustment` |
| `narrative_weaver.py` | `NarrativeWeaver`, `NarrativeContext` |
| `anticipatory_responder.py` | `AnticipatoryResponder`, `Anticipation` |
| `proactive_agent.py` | `ProactiveAgent`, `FillMessage` |
| `rhythm_controller.py` | `RhythmController`, `TimingParams` |
| `layer.py` | `ExperienceLayer` (orchestrator for all 6 components) |

**`__init__.py` exports:** All output dataclasses, component classes, and `ExperienceLayer`.

**Internal deps:** `layer.py` imports from all 6 component files. No cross-folder deps (self-contained).

---

### `fabric/` (2 files)

| File | Defines |
|------|---------|
| `capability_registry.py` | `CapabilityRegistry`, `create_demo_registry` |
| `demo_capabilities.py` | `DEMO_CAPABILITIES`, 7 mock handler functions |

**`__init__.py` exports:** `CapabilityRegistry`, `create_demo_registry`, `DEMO_CAPABILITIES`.

**Internal deps:** None to other k1_poc folders. Self-contained.

---

### `fsm/` (11 files)

| File | Defines |
|------|---------|
| `states.py` | `ConciergeState` (12-state enum) |
| `errors.py` | `IllegalTransitionError`, `FrontLockOverflowError` |
| `front_lock.py` | `FrontLock`, priority constants |
| `turn_state.py` | `FSMTurnState` |
| `transition_table.py` | `TRANSITION_TABLE`, trigger constants, `is_legal`, `target_state` |
| `controller.py` | `ConciergeController`, `TypedHistoryEntry` |
| `control_extension.py` | `ConciergeControlExtension` |
| `history_writer.py` | `HistoryWriter`, `history_to_front_messages`, `history_to_back_context` |
| `interrupt_handler.py` | `InterruptClassifier`, `CancelTracker`, `ProactiveWakeHandler` |
| `phase1.py` | `Phase1Pipeline`, `Phase1Result`, `StubPhase1Pipeline`, `TurnLock` |
| `task_bridge.py` | `TaskBridge` |

**`__init__.py` exports:** FSM-native symbols only (states, controller, turn state, locks, transition table, control extension, history/interrupt/task bridge, and Phase1 pipeline). No cross-package re-exports from `delta/` or `protocols/`.

---

### `kernel/` (2 files)

| File | Defines |
|------|---------|
| `bootstrap.py` | `KernelConfig`, `KernelRuntime`, `start_kernel`, `stop_kernel`, internal adapters |
| `runner.py` | CLI entry point (`python -m poc.k1_poc.kernel.runner`) |

**`__init__.py` exports:** `KernelConfig`, `KernelRuntime`, `start_kernel`, `stop_kernel`.

---

### `llm/` (5 files)

| File | Defines |
|------|---------|
| `types.py` | `Capability`, `FinishReason`, `ThinkingLevel`, `ToolSchema`, `ModelMessage`, `ConciergeModelRequest`, `ToolCallResult`, `ToolResultMessage`, `ConciergeModelResponse`, `StreamChunk`, `tool_result_to_message`, `response_to_assistant_message` |
| `ports.py` | `IConciergeModelPort` (protocol/interface) |
| `test_adapter.py` | `TestConciergeAdapter` |
| `gemini_adapter.py` | `GeminiConciergeAdapter` (lazy import of google-genai) |
| `model_selection.py` | `select_model`, `DEFAULT_MODEL`, `MODEL_SELECTION_TABLE` |
| `validator.py` | `LLMOutputValidator`, `ValidationResult` |

**`__init__.py` exports:** All of the above (GeminiConciergeAdapter lazily).

---

### `orchestrator/` (5 files)

| File | Defines |
|------|---------|
| `types.py` | `Budget`, `TaskEnvelope`, `CapabilityRequest`, `CapabilityResult`, `StepResult`, `AggregatedResult`, `CannedResponse`, `PlanRequest`, `PlanStep`, `CommittedPlan` |
| `ports.py` | 9 port interfaces (`IFabricGatewayPort`, `IStateReadPort`, `IDeltaEmitPort`, etc.) |
| `stub.py` | `OrchestratorStub`, `BudgetExceededError` |
| `routing.py` | `route_task`, `route_task_sync`, `DispatchRecord` |
| `degradation.py` | `CircuitBreaker`, `route_task_with_degradation`, `get_effective_tier` |
| `interfaces.py` | `IDAGExecutor`, `IPlannerService`, `IWorkflowEngine`, etc., `HIGH_TIER_EVENTS` |

**`__init__.py` exports:** Full re-export of all types, ports, routing, degradation, interfaces.

---

### `prompt/` (7 files)

| File | Defines |
|------|---------|
| `mode.py` | `PromptMode` (10-variant enum), `determine_mode`, `TOOL_ALLOWLIST`, `get_tool_allowlist`, `get_max_iterations` |
| `affect.py` | `AffectBand`, `compute_affect_band`, `AffectModifiers`, `compute_affect_modifiers`, `AFFECT_TONE_BLOCKS`, `AFFECT_MODE_INTERACTIONS` |
| `sections.py` | `PROMPT_SECTIONS`, `MODE_SECTIONS`, `ANTI_PATTERN_KEYS`, `MODE_EXAMPLES` |
| `scenario_templates.py` | `SCENARIO_DATA_TEMPLATES` |
| `clarify_depth.py` | `ClarificationDepthState`, `ClarificationTracker`, `CLARIFY_DEPTH_BLOCKS` |
| `domain_rules.py` | `DOMAIN_RULES`, `get_domain_rules`, `DOMAIN_SAFETY_FLOORS`, `DOMAIN_APPLICABLE_MODES` |
| `builder.py` | `DynamicPromptBuilder`, `BuiltContext`, `SSReadConfig`, `SS_READ_CONFIGS`, `apply_affect_modifiers` |
| `back_prompt.py` | `build_back_prompt` |

**`__init__.py` exports:** All of the above.

---

### `protocols/` (11 files)

| File | Defines |
|------|---------|
| `cancellation.py` | `CancellationToken`, `CancelReason`, `TaskCancelledError` |
| `cancel_events.py` | `TaskCancelEvent`, `TaskFailedCancelledEvent` |
| `cancel_handler.py` | `CancellationHandler` |
| `suspension.py` | `SuspensionType`, `SuspensionRequest`, `SuspensionResolution`, limits/errors |
| `suspension_events.py` | `TaskSuspendedEvent`, `TaskResumeEvent` |
| `suspension_manager.py` | `SuspensionManager` |
| `weave_batcher.py` | `WeaveBatcher`, `WeaveResult`, prompt templates |
| `weave_state.py` | `WeaveAction`, `PendingResult`, `PendingResultsQueue`, `STATE_ACTION_TABLE` |
| `hitl.py` | `SafetyBand`, `HILRequest`, `HILResponse`, `HIL_TIMEOUTS` |
| `hitl_coordinator.py` | `HILCoordinator`, `HILCoordinatorConfig` |
| `hitl_flow.py` | `HILFlowType`, context builders, request factories, resolution parsers |
| `hitl_persistence.py` | `TaskStatus`, `TaskStateEntry`, crash recovery |
| `hitl_pipeline.py` | Approval/selection pipeline functions |
| `hitl_wiring.py` | `ResumeContext`, `HILModeConfig`, wiring validation |

**`__init__.py` exports:** Full re-export of all protocols.

---

### `react/` (2 files)

| File | Defines |
|------|---------|
| `loop.py` | `react_loop`, `ReactResult`, iteration constants |
| `history.py` | `build_chat_history`, `build_chat_history_for_back` |

**`__init__.py` exports:** All of the above.

---

### `sessionstate/` (~35 files across 5 subpackages)

| Subpackage | Key Files |
|------------|-----------|
| `sections/` (15 files) | 12 section classes + `task_state`, `task_artifacts`, `artifacts_warm` |
| `tiers/` (3 files) | `HotTier`, `WarmTier`, `LocalColdTier` |
| `ports/` (5 files) | `IStoragePort`, `IEventPort`, `IWriterPort`, `ILifecyclePort`, `IK0SyncPort` |
| `adapters/` (5 files) | `SQLiteStorageAdapter`, `InMemoryStorageAdapter`, `LocalEventAdapter`, `DirectWriterAdapter`, `StandaloneLifecycle` |
| Root files | `manager.py`, `factory.py`, `guard.py`, `sizetracker.py`, `eviction.py`, `migration.py`, `events.py`, `metrics.py`, `logging.py`, `snapshot.py`, `reconstruction.py`, `local_cold.py`, `cli.py` |

**`__init__.py` exports:** Massive: ~60+ symbols covering manager, factory, events, engines, sections, tiers, ports, adapters.

**Internal deps:** Sections import from generated flatbuffers only. All other sessionstate files use relative imports (`from .` / `from ..`). No imports FROM other k1_poc folders.

---

### `task/` (10 files)

| File | Defines |
|------|---------|
| `complexity.py` | `ComplexityTier`, `TIER_BUDGET`, `budget_for_tier` |
| `intent.py` | `TaskIntent` |
| `dispatch.py` | `TaskDispatch`, `TaskComplete`, `TaskFailed` |
| `topics.py` | 9 task topic constants |
| `envelope_bridge.py` | `dispatch_to_envelope`, `complete_to_envelope`, `failed_to_envelope` |
| `classifier.py` | `IntentClassification`, `classify_intents`, `build_dispatches` |
| `dependency_queue.py` | `TaskDependencyQueue` |
| `tools.py` | `dispatch_task`, `DISPATCH_TASK_SCHEMA` |
| `receiver.py` | `TaskReceiver` |
| `bundled_executor.py` | `IntentResult`, `BundledExecutionPlan` |
| `parallel_safety.py` | `PARALLEL_SAFE_GROUPS`, `ALWAYS_SEQUENTIAL`, `is_parallel_safe`, `classify_tool_batch` |

**`__init__.py` exports:** All of the above.

---

### `tools/` (5 files)

| File | Defines |
|------|---------|
| `schemas_front.py` | `FRONT_TOOL_SCHEMAS`, 9 individual front schema constants |
| `schemas_back.py` | `BACK_TOOL_SCHEMAS`, `BACK_TIER_ALLOWLISTS`, 5 back schema constants |
| `result_protocol.py` | `ToolResult`, `tool_result_to_message` |
| `implementations.py` | `ToolContext`, `TOOL_REGISTRY`, `execute_tool`, 15 tool handler functions |
| `dispatcher.py` | `ToolDispatcher`, `create_front_dispatcher`, `create_back_dispatcher`, `DispatchRecord` |
| `parallelism.py` | `can_parallelize`, `partition_calls` |

**`__init__.py` exports:** All of the above.

---

### Root-level files

| File | Defines | Imports from k1_poc |
|------|---------|---------------------|
| `main.py` | `boot()` | `bus.setup` |
| `demo_config.py` | `DEMO_FAMILY_PROFILE`, `DEMO_SESSION_CONFIG` | None |

---

## 2. Per-File Cross-Module Imports

### actors/back.py

```
FROM bus:       bus.builders (build_task_complete, build_task_failed, etc.)
FROM llm:       llm.ports (IConciergeModelPort), llm.types (ModelMessage), llm.validator
FROM prompt:    prompt.back_prompt (build_back_prompt)
FROM react:     react.loop (react_loop, ReactResult), react.history (build_chat_history_for_back)
FROM tools:     tools.dispatcher (ToolDispatcher), tools.schemas_back (BACK_TIER_ALLOWLISTS, BACK_TOOL_SCHEMAS)
FROM k1:        k1.bus.envelope, k1.bus.ports.bus
```

### actors/front.py

```
FROM bus:       bus.builders (build_turn_started, build_turn_completed, etc.)
FROM llm:       llm.ports (IConciergeModelPort), llm.types (ModelMessage), llm.validator
FROM prompt:    prompt.affect (compute_affect_band), prompt.builder (DynamicPromptBuilder), prompt.mode (PromptMode, determine_mode)
FROM react:     react.loop (react_loop, ReactResult)
FROM task:      task.complexity (ComplexityTier, budget_for_tier)
FROM tools:     tools.dispatcher (ToolDispatcher)
FROM k1:        k1.bus.envelope, k1.bus.ports.bus
```

### bus/builders.py

```
FROM bus:       bus.topics (all topic constants)
FROM k1:        k1.bus.envelope (Envelope, PayloadFormat, Priority)
```

### bus/setup.py

```
FROM k1:        k1.bus.adapters.session_adapter, k1.bus.factory, k1.bus.impl.local_bus, k1.bus.impl.local_mailbox, k1.bus.ports.mailbox
```

### bus/topics.py

```
No k1_poc cross-deps (pure constants)
```

### delta/aggregator.py

```
FROM delta:     delta.session_delta (SessionDelta) [internal]
```

### delta/applicator.py

```
FROM delta:     delta.aggregator (DeltaBatch), delta.session_delta (SessionDelta) [internal]
```

### delta/emitters.py

```
FROM delta:     delta.session_delta, delta.topics [internal]
```

### delta/overflow.py, delta/snapshot_reader.py, delta/writer_registry.py, delta/topics.py, delta/session_delta.py

```
No cross-folder deps (self-contained)
```

### demo/coordinator.py

```
FROM demo:      demo.output_channel [internal]
Lazy imports:
  FROM demo:    demo.preloaded_memories, demo.smith_family, demo.iot_stubs
  FROM prompt:  prompt.builder
  FROM kernel:  kernel.bootstrap (KernelConfig, start_kernel, stop_kernel)
  FROM actors:  actors.back (back_handler), actors.front (front_handler)
  FROM tools:   tools.schemas_front
  FROM fsm:     fsm.states
```

### demo/coordinator_old.py

```
FROM demo:      demo.output_channel [internal]
(Plus many more lazy imports -- deprecated)
```

### demo/interactive.py

```
FROM bus:       bus.builders (build_user_input)
FROM demo:      demo.display, demo.smith_family [internal]
```

### demo/iot_stubs.py

```
FROM bus:       bus.builders (build_proactive_fill)
FROM k1:        k1.bus.ports.bus (IBus)
```

### demo/output_channel.py

```
FROM bus:       bus.topics (topic constants)
FROM demo:      demo.display [internal]
FROM k1:        k1.bus.envelope, k1.bus.ports.bus
```

### demo/runner.py

```
FROM demo:      demo.coordinator, demo.interactive [internal]
```

### demo/_e2e_smoke.py

```
FROM demo:      demo.coordinator [lazy]
FROM bus:       bus.builders [lazy]
```

### demo/display.py, demo/smith_family.py, demo/preloaded_memories.py

```
No cross-folder deps (pure data/utilities)
```

### experience/layer.py

```
FROM experience: all 6 component files [internal only]
```

### experience/*.py (6 component files)

```
No cross-folder deps (self-contained dataclasses)
```

### fabric/capability_registry.py

```
No cross-folder deps (self-contained, imports demo_capabilities internally)
```

### fabric/demo_capabilities.py

```
No cross-folder deps
```

### fsm/controller.py

```
FROM bus:           bus.builders, bus.topics
FROM fsm:           fsm.control_extension, fsm.errors, fsm.front_lock, fsm.interrupt_handler, fsm.phase1, fsm.states, fsm.task_bridge, fsm.transition_table, fsm.turn_state [internal]
FROM orchestrator:  orchestrator.routing (route_task_sync)
FROM protocols:     protocols.cancel_handler, protocols.suspension_manager, protocols.weave_batcher
FROM task:          task.complexity, task.dispatch, task.intent
FROM k1:            k1.bus.envelope, k1.bus.ports.bus, k1.bus.ports.mailbox
```

### fsm/control_extension.py

```
FROM fsm:       fsm.states [internal]
```

### fsm/history_writer.py

```
FROM fsm:       fsm.controller (TypedHistoryEntry) [internal]
```

### fsm/task_bridge.py

```
FROM sessionstate: sessionstate.sections.task_artifacts, sessionstate.sections.task_state
```

### fsm/transition_table.py

```
FROM bus:       bus.topics
FROM fsm:       fsm.states [internal]
```

### fsm/front_lock.py, fsm/turn_state.py

```
FROM k1:        k1.bus.envelope
```

### fsm/errors.py, fsm/interrupt_handler.py, fsm/phase1.py, fsm/states.py

```
No cross-folder deps
```

### kernel/bootstrap.py

```
FROM actors:        actors.back (back_handler, subscribe_back_events), actors.front (front_handler, subscribe_front_events)
FROM bus:           bus.builders (build_affect_update, build_proactive_fill, build_task_failed, build_task_resume, build_task_suspended)
FROM experience:    experience.layer (ExperienceLayer)
FROM fsm:           fsm.controller (ConciergeController)
FROM main:          main (boot)
FROM tools:         tools.dispatcher, tools.implementations (ToolContext), tools.schemas_front (FRONT_TOOL_SCHEMAS)
Lazy imports:
  FROM delta:       delta.aggregator, delta.applicator, delta.topics, delta.session_delta
  FROM fabric:      fabric.capability_registry
  FROM llm:         llm.test_adapter, llm.gemini_adapter
  FROM orchestrator: orchestrator.stub, orchestrator.types
  FROM protocols:   protocols.hitl_coordinator
  FROM sessionstate: sessionstate.factory
  FROM k1:          k1.bus.envelope
```

### kernel/runner.py

```
FROM kernel:    kernel.bootstrap (relative import) [internal]
```

### llm/ports.py, llm/test_adapter.py, llm/gemini_adapter.py, llm/validator.py

```
FROM llm:       llm.types [internal]
llm/gemini_adapter.py also: llm.model_selection
```

### llm/types.py, llm/model_selection.py

```
No cross-folder deps
```

### orchestrator/types.py

```
FROM task:      task.complexity (ComplexityTier)
```

### orchestrator/ports.py

```
FROM orchestrator: orchestrator.types [internal]
```

### orchestrator/routing.py

```
FROM orchestrator:  orchestrator.types [internal]
FROM task:          task.complexity, task.dispatch
```

### orchestrator/stub.py

```
FROM orchestrator:  orchestrator.ports, orchestrator.types [internal]
```

### orchestrator/degradation.py

```
FROM orchestrator:  orchestrator.routing, orchestrator.types [internal]
FROM task:          task.complexity, task.dispatch
```

### orchestrator/interfaces.py

```
FROM orchestrator:  orchestrator.types [internal]
```

### prompt/builder.py

```
FROM llm:       llm.types (ModelMessage, ToolSchema)
FROM prompt:    prompt.affect, prompt.clarify_depth, prompt.domain_rules, prompt.mode, prompt.scenario_templates, prompt.sections [internal]
```

### prompt/back_prompt.py

```
No cross-folder deps (pure text construction)
```

### prompt/mode.py, prompt/affect.py, prompt/clarify_depth.py, prompt/domain_rules.py

```
No cross-folder deps
```

### prompt/sections.py, prompt/scenario_templates.py

```
FROM prompt:    prompt.mode (PromptMode) [internal]
```

### protocols/cancel_events.py

```
FROM task:      task.topics (TASK_FAILED)
```

### protocols/cancel_handler.py

```
FROM protocols: protocols.cancellation [internal]
```

### protocols/hitl.py

```
FROM protocols: protocols.suspension [internal]
```

### protocols/hitl_coordinator.py

```
FROM protocols: protocols.hitl, protocols.suspension, protocols.suspension_manager [internal]
```

### protocols/hitl_flow.py

```
FROM protocols: protocols.hitl [internal]
```

### protocols/hitl_persistence.py

```
FROM protocols: protocols.hitl [internal]
```

### protocols/hitl_pipeline.py

```
FROM protocols: protocols.hitl, protocols.hitl_flow [internal]
```

### protocols/hitl_wiring.py

```
FROM prompt:    prompt.builder (SS_READ_CONFIGS, SSReadConfig), prompt.mode, prompt.sections
```

### protocols/weave_state.py

```
FROM fsm:       fsm.states (ConciergeState)
```

### protocols/cancellation.py, protocols/suspension.py, protocols/suspension_events.py, protocols/suspension_manager.py, protocols/weave_batcher.py

```
No cross-folder deps (or internal only)
```

### react/loop.py

```
FROM llm:       llm.ports (IConciergeModelPort), llm.types, llm.validator
FROM tools:     tools.dispatcher (ToolDispatcher), tools.result_protocol (ToolResult)
```

### react/history.py

```
FROM llm:       llm.types (ModelMessage)
```

### sessionstate/ (all files)

```
All use RELATIVE imports only (from . / from ..)
No imports FROM other k1_poc folders.
Sections import from generated flatbuffers subpackage.
```

### task/complexity.py, task/intent.py, task/topics.py

```
No cross-folder deps
```

### task/dispatch.py

```
FROM task:      task.complexity, task.intent [internal]
```

### task/classifier.py

```
FROM task:      task.complexity, task.dispatch, task.intent [internal]
```

### task/dependency_queue.py

```
FROM task:      task.dispatch [internal]
```

### task/envelope_bridge.py

```
FROM task:      task.dispatch, task.topics [internal]
```

### task/receiver.py

```
FROM task:      task.dependency_queue, task.dispatch [internal]
```

### task/tools.py

```
FROM task:      task.classifier, task.complexity, task.dispatch, task.intent [internal]
```

### task/bundled_executor.py

```
FROM task:      task.intent [internal]
```

### task/parallel_safety.py

```
No cross-folder deps
```

### tools/schemas_front.py

```
FROM llm:       llm.types (ToolSchema)
```

### tools/schemas_back.py

```
FROM llm:       llm.types (ToolSchema)
FROM tools:     tools.schemas_front (RECALL_MEMORY_SCHEMA) [internal]
```

### tools/result_protocol.py

```
FROM llm:       llm.types (ToolResultMessage)
```

### tools/implementations.py

```
FROM task:      task.complexity, task.dispatch, task.intent
FROM tools:     tools.result_protocol [internal]
```

### tools/dispatcher.py

```
FROM llm:       llm.types (ToolCallResult, ToolSchema)
FROM tools:     tools.implementations, tools.result_protocol [internal]
```

### tools/parallelism.py

```
No cross-folder deps
```

---

## 3. Bootstrap Dependency Chain

Starting from `kernel/bootstrap.py` → `start_kernel()`:

```
kernel/bootstrap.py
├── main.py                          ← boot() creates bus infra
│   └── bus/setup.py
│       └── k1.bus.* (factory, local_bus, local_mailbox, session_adapter)
├── bus/builders.py                  ← affect/proactive/HITL envelope emitters
│   └── bus/topics.py
│
├── actors/front.py                  ← front_handler
│   ├── bus/builders.py              ← build_turn_started, etc.
│   │   └── bus/topics.py
│   ├── llm/ports.py → llm/types.py
│   ├── llm/validator.py → llm/types.py
│   ├── prompt/affect.py
│   ├── prompt/builder.py
│   │   ├── llm/types.py
│   │   ├── prompt/affect.py
│   │   ├── prompt/clarify_depth.py
│   │   ├── prompt/domain_rules.py
│   │   ├── prompt/mode.py
│   │   ├── prompt/scenario_templates.py → prompt/mode.py
│   │   └── prompt/sections.py → prompt/mode.py
│   ├── prompt/mode.py
│   ├── react/loop.py
│   │   ├── llm/ports.py, llm/types.py, llm/validator.py
│   │   ├── tools/dispatcher.py
│   │   │   ├── llm/types.py
│   │   │   ├── tools/implementations.py
│   │   │   │   ├── task/complexity.py, task/dispatch.py, task/intent.py
│   │   │   │   └── tools/result_protocol.py → llm/types.py
│   │   │   └── tools/result_protocol.py
│   │   └── tools/result_protocol.py
│   └── task/complexity.py
│
├── actors/back.py                   ← back_handler
│   ├── bus/builders.py
│   ├── llm/ports.py, llm/types.py, llm/validator.py
│   ├── prompt/back_prompt.py
│   ├── react/loop.py (shared)
│   ├── react/history.py → llm/types.py
│   └── tools/dispatcher.py, tools/schemas_back.py → llm/types.py + tools/schemas_front.py
│
├── experience/layer.py              ← ExperienceLayer
│   └── experience/*.py (6 component files, self-contained)
│
├── fsm/controller.py                ← ConciergeController
│   ├── bus/builders.py, bus/topics.py
│   ├── fsm/* (internal: states, errors, front_lock, etc.)
│   ├── orchestrator/routing.py
│   │   └── orchestrator/types.py → task/complexity.py
│   ├── protocols/cancel_handler.py → protocols/cancellation.py
│   ├── protocols/suspension_manager.py → protocols/suspension.py
│   ├── protocols/weave_batcher.py
│   └── task/complexity.py, task/dispatch.py, task/intent.py
│
├── tools/dispatcher.py              ← create_front_dispatcher, create_back_dispatcher
├── tools/implementations.py         ← ToolContext
├── tools/schemas_front.py           ← FRONT_TOOL_SCHEMAS
│
├── [LAZY] delta/aggregator.py       ← DeltaAggregator
├── [LAZY] delta/applicator.py       ← DeltaApplicator
├── [LAZY] protocols/hitl_coordinator.py ← HILCoordinator
├── [LAZY] orchestrator/stub.py      ← OrchestratorStub
├── [LAZY] fabric/capability_registry.py ← create_demo_registry
├── [LAZY] sessionstate/factory.py   ← SessionStateFactory
├── [LAZY] llm/test_adapter.py or llm/gemini_adapter.py
└── [LAZY] k1.bus.envelope (for delta notifications)
```

**Demo coordinator chain** (`demo/coordinator.py` → `initialize_system()`):

```
demo/coordinator.py
├── kernel/bootstrap.py              ← start_kernel() [PHASE 2]
│   └── (entire bootstrap chain above)
├── demo/smith_family.py             ← family profile data [PHASE 1]
├── demo/preloaded_memories.py       ← seed memories [PHASE 1]
├── prompt/builder.py                ← DynamicPromptBuilder [PHASE 1]
├── demo/iot_stubs.py                ← IoT stubs + storyline caps [PHASE 3-4]
│   └── bus/builders.py
├── demo/output_channel.py           ← OutputChannel [PHASE 4]
│   ├── bus/topics.py
│   └── demo/display.py
├── actors/front.py, actors/back.py  ← mailbox consumer [PHASE 4]
├── tools/schemas_front.py           ← consumer needs FRONT_TOOL_SCHEMAS
└── fsm/states.py                    ← health check FSM state
```

---

## 4. Dependency Matrix (folder → folder)

| Source ↓ / Target → | actors | bus | delta | demo | experience | fabric | fsm | kernel | llm | orch | prompt | protocols | react | session | task | tools | k1.* |
|---------------------|:------:|:---:|:-----:|:----:|:----------:|:------:|:---:|:------:|:---:|:----:|:------:|:---------:|:-----:|:-------:|:----:|:-----:|:----:|
| **actors**          |   -    |  X  |       |      |            |        |     |        |  X  |      |   X    |           |   X   |         |  X   |   X   |  X   |
| **bus**             |        |  -  |       |      |            |        |     |        |     |      |        |           |       |         |      |       |  X   |
| **delta**           |        |     |   -   |      |            |        |     |        |     |      |        |           |       |         |      |       |      |
| **demo**            |   X*   |  X  |       |  -   |            |        |  X* |   X*   |     |      |   X*   |           |       |         |      |  X*   |  X   |
| **experience**      |        |     |       |      |     -      |        |     |        |     |      |        |           |       |         |      |       |      |
| **fabric**          |        |     |       |      |            |   -    |     |        |     |      |        |           |       |         |      |       |      |
| **fsm**             |        |  X  |       |      |            |        |  -  |        |     |  X   |        |     X     |       |    X    |  X   |       |  X   |
| **kernel**          |   X    |     |  X*   |      |     X      |   X*   |  X  |   -    | X*  |  X*  |        |    X*     |       |   X*    |      |   X   |  X*  |
| **llm**             |        |     |       |      |            |        |     |        |  -  |      |        |           |       |         |      |       |      |
| **orchestrator**    |        |     |       |      |            |        |     |        |     |  -   |        |           |       |         |  X   |       |      |
| **prompt**          |        |     |       |      |            |        |     |        |  X  |      |   -    |           |       |         |      |       |      |
| **protocols**       |        |     |       |      |            |        |  X  |        |     |      |   X    |     -     |       |         |  X   |       |      |
| **react**           |        |     |       |      |            |        |     |        |  X  |      |        |           |   -   |         |      |   X   |      |
| **sessionstate**    |        |     |       |      |            |        |     |        |     |      |        |           |       |    -    |      |       |      |
| **task**            |        |     |       |      |            |        |     |        |     |      |        |           |       |         |  -   |       |      |
| **tools**           |        |     |       |      |            |        |     |        |  X  |      |        |           |       |         |  X   |   -   |      |

`X` = direct import at module level, `X*` = lazy/conditional import, `-` = self

### Dependency counts (imports FROM other k1_poc folders)

| Folder | Depends on N folders | Depended on by N folders |
|--------|:--------------------:|:------------------------:|
| **llm** | 0 | 5 (actors, prompt, react, tools, kernel) |
| **task** | 0 | 5 (actors, fsm, orchestrator, protocols, tools) |
| **bus** | 0 (only k1.*) | 5 (actors, demo, fsm, kernel via main.py) |
| **sessionstate** | 0 | 2 (fsm, kernel) |
| **experience** | 0 | 1 (kernel) |
| **fabric** | 0 | 1 (kernel) |
| **delta** | 0 | 1 (kernel) |
| **prompt** | 1 (llm) | 3 (actors, demo, protocols) |
| **react** | 2 (llm, tools) | 1 (actors) |
| **tools** | 2 (llm, task) | 3 (actors, kernel, react) |
| **protocols** | 3 (fsm, prompt, task) | 2 (fsm, kernel) |
| **orchestrator** | 1 (task) | 2 (fsm, kernel) |
| **fsm** | 5 (bus, orchestrator, protocols, sessionstate, task) | 3 (kernel, protocols, demo) |
| **actors** | 6 (bus, llm, prompt, react, task, tools) | 2 (kernel, demo) |
| **kernel** | 9 (actors, delta, experience, fabric, fsm, llm, orchestrator, protocols, sessionstate, tools, main) | 1 (demo) |
| **demo** | 6 (actors, bus, fsm, kernel, prompt, tools) | 0 (top of tree) |

---

## 5. External k1.* Dependencies

All external imports come from the production `k1/` package:

| k1 module | Used by |
|-----------|---------|
| `k1.bus.envelope` (Envelope, PayloadFormat, Priority) | actors/back, actors/front, bus/builders, demo/output_channel, fsm/controller, fsm/front_lock, fsm/turn_state, kernel/bootstrap (lazy) |
| `k1.bus.ports.bus` (IBus) | actors/back, actors/front, demo/iot_stubs, demo/output_channel, fsm/controller |
| `k1.bus.ports.mailbox` (IMailboxRouter, MailboxConfig) | bus/setup, fsm/controller |
| `k1.bus.factory` (BusFactory) | bus/setup, main.py (lazy) |
| `k1.bus.impl.local_bus` (LocalBus) | bus/setup |
| `k1.bus.impl.local_mailbox` (LocalMailbox, LocalMailboxRouter) | bus/setup |
| `k1.bus.adapters.session_adapter` (SessionBusAdapter) | bus/setup |

**All external deps are from `k1.bus.*` only.** No dependencies on k1.fabric, k1.kernel, k1.memory_writer, etc.

---

## 6. Missing or Broken Import Chains

### Confirmed Issues

1. **`fsm/task_bridge.py` → `sessionstate/sections/task_*`** — This is the ONLY file in `fsm/` that imports directly from `sessionstate`. All other sessionstate access goes through the kernel bootstrap adapters. This is a tight coupling that may cause issues if sessionstate sections API changes.

2. **`protocols/weave_state.py` → `fsm/states.py`** — `protocols` imports from `fsm`, while `fsm` imports from `protocols` (cancel_handler, suspension_manager, weave_batcher). This is a **bidirectional dependency** between `fsm` and `protocols`. Not circular at the file level (different files import different things), but it means neither package can exist without the other.

3. **`protocols/hitl_wiring.py` → `prompt/builder.py` + `prompt/mode.py` + `prompt/sections.py`** — Protocols package depends on prompt package. This couples HITL wiring configuration to the prompt assembly system.

4. **`demo/coordinator_old.py`** — Deprecated file still present. Has the same import pattern as the new coordinator but with inline composition instead of kernel delegation.

### Verified NOT Broken

- All lazy imports in `kernel/bootstrap.py` resolve correctly (verified by start_kernel execution path).
- All `__init__.py` re-exports match actual module contents.
- `fsm/__init__.py` no longer re-exports `delta/*` or `protocols/weave_batcher`; package boundary is now explicit.
- No circular imports at the file level (bidirectional at folder level between fsm ↔ protocols is safe since different files are involved).
- `sessionstate` is fully self-contained using relative imports — no risk of circular deps with rest of system.
- `experience` and `fabric` are leaf packages with zero k1_poc dependencies.
- `main.py` uses only `bus.setup` — clean boot entry point.

### Architectural Notes

- **Leaf packages (0 deps):** `llm`, `task`, `bus` (only k1.*), `sessionstate`, `experience`, `fabric`, `delta`
- **Mid-tier (1-3 deps):** `prompt`, `react`, `tools`, `orchestrator`, `protocols`
- **Hub packages (5+ deps):** `fsm`, `actors`, `kernel`, `demo`
- **Import direction:** Generally follows `demo → kernel → actors → {react, prompt, tools} → {llm, task}` with `fsm` as the central coordination hub connecting `bus`, `orchestrator`, `protocols`, `sessionstate`, and `task`.
