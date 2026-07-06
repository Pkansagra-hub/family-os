# CONCIERGE (K1) — Complete Component Inventory for Strengthening Pass

> Generated: 2026-06-25
> Source: `k1/concierge/concierge_unified.mmd` + `k1/concierge/concierge_wiring_matrix.mmd` + directory scan
> Branch: `feature/prompt-architecture-refactor`

---

## 1. PORTS (8 Hexagonal Boundary Contracts)

| # | Port | Direction | File |
|---|------|-----------|------|
| 1 | `IInputPort` | Inbound | `ports.py` |
| 2 | `IOutputPort` | Outbound | `ports.py` |
| 3 | `IClassificationPort` | Outbound | `ports.py` |
| 4 | `ILLMPort` | Outbound | `ports.py` / `llm/ports.py` |
| 5 | `IStatePort` | Both | `ports.py` |
| 6 | `IDispatchPort` | Outbound | `ports.py` |
| 7 | `IDeltaPort` | Both | `ports.py` |
| 8 | `IMemoryPort` | Outbound | `ports.py` |

---

## 2. ADAPTERS (Production + Test — ~20 files)

### Production Adapters

| Adapter | File |
|---------|------|
| `BusInputAdapter` | `adapters/bus_input.py` |
| `BusOutputAdapter` | `adapters/bus_output.py` |
| `FabricDispatchAdapter` | `adapters/fabric_dispatch.py` |
| `RecallMemoryAdapter` | `adapters/recall_memory.py` |
| `SSMStateAdapter` | `adapters/ssm_state.py` |
| `SnapshotStateReadAdapter` | `adapters/snapshot_state_read.py` |
| `ModelHubPOCBridge` (LLM) | `adapters/hub_llm.py` |
| `LocalDeltaBus` | `adapters/local_delta.py` |
| `NullBridgeWrite` | `adapters/null_bridge_write.py` |
| `NullDeltaBus` | `adapters/null_delta_bus.py` |
| `NullEventSubscription` | `adapters/null_event_subscription.py` |
| `NullStateReader` | `adapters/null_state_reader.py` |

### Test Adapters (9)

| Adapter | File |
|---------|------|
| `TestInputAdapter` | `adapters/test_input.py` |
| `TestOutputAdapter` | `adapters/test_output.py` |
| `TestStateAdapter` | `adapters/test_state.py` |
| `TestMemoryAdapter` | `adapters/test_memory.py` |
| `TestDispatchAdapter` | `adapters/test_dispatch.py` |
| `TestLLMAdapter` | `adapters/test_llm.py` |
| `TestDeltaAdapter` | `adapters/test_delta.py` |

---

## 3. FSM — State Machine Controller (16 files)

| Component | File |
|-----------|------|
| `ConciergeController` (main FSM) | `fsm/controller.py` |
| `ConciergeState` (11 states enum) | `fsm/states.py` |
| `FSMTurnState` (pending_results, cancelled_tasks) | `fsm/turn_state.py` |
| `FrontLock` (concurrency gate) | `fsm/front_lock.py` |
| `ConversationArbiter` (cancel/modify/defer) | `fsm/arbiter.py` |
| `TaskBridge` (SS task_state SOT bridge) | `fsm/task_bridge.py` |
| `transition_table.py` (legal transitions) | `fsm/transition_table.py` |
| `IdempotencyLedger` | `fsm/idempotency.py` |
| `control_extension.py` (mirror FSM → SS.control) | `fsm/control_extension.py` |
| `history_writer.py` | `fsm/history_writer.py` |
| `interrupt_handler.py` | `fsm/interrupt_handler.py` |
| `response_final_table.py` | `fsm/response_final_table.py` |
| `dead_letter.py` | `fsm/dead_letter.py` |
| `dead_letter_consumer.py` | `fsm/dead_letter_consumer.py` |
| `errors.py` | `fsm/errors.py` |

### FSM States (11)

| State | Description |
|-------|-------------|
| `LISTENING` | Idle, awaiting user input |
| `DISPATCHING` | Phase 1 + Front LLM: classify, cognitive, dispatch |
| `COMPANIONING` | Front idle, Back working; can accept new input |
| `PROGRESSING` | Stream deltas as updates |
| `DELIVERING` | Final results + next steps |
| `CLARIFYING_USER` | Front detected ambiguity; progressive disclosure |
| `CLARIFYING_WORKER` | Back suspended, needs user input; HITL relay/resolve |
| `CANCELLING` | Cancel in-flight task; cooperative tokens |
| `INTERRUPT_HANDLING` | New user input during COMPANIONING |
| `PROACTIVE_WAKE` | task.complete while LISTENING; idle delivery |
| `WEAVING` | Drain pending_results queue; WeaveBatcher flush |

### Guard Model (5 Actions)

| Guard | Description |
|-------|-------------|
| `TRANSITION` | Validate + change state |
| `PASSTHROUGH` | Forward, no state change |
| `OBSERVE` | Log only, no routing |
| `QUEUE` | Hold in FrontLock or pending_results |
| `DEAD_LETTER` | Reject as invalid |

---

## 4. ACTORS — Front + Back + Infrastructure (9 files)

### Front Actor (`actors/front.py`)

| Function | Purpose |
|----------|---------|
| `front_handler` | Main ReAct entry: mode resolve → prompt build → ReAct → bus emit |
| `_extract_scenario_data` | PRESENT / WEAVE / HIL / ERROR / CANCEL / CLARIFY / STANDARD |
| `_build_resolution` | HIL resolution building |
| `_build_resolution_frame` | HIL resolution frame |
| `emit_task_cancel` | Emit cancel event |
| `emit_task_resume` | Emit resume event |
| `_emit_streaming_response` | Stream response to output |
| `subscribe_front_events` | Subscribe to 5 bus topics |
| `_parse_routing_metadata` | Parse routing metadata from envelope |
| `_get_affect_dict` | Extract affect from SS |
| `_get_clarification_state` | Extract clarification state |
| `_get_task_state_dict` | Extract task state |
| `_extract_family_context` | Extract family context |
| `_get_history_active` | Get active history |
| `_extract_current_user_text` | Extract current user text |
| `_build_event_turn_text` | Build event turn text |
| `_write_runtime_prompt_dump` | Write runtime prompt dump |
| Leak guards | Reasoning / system block / Back frame cleanup |

**Front Subscribes To (5 topics):**
`k1.session.user.input.v1`, `k1.orchestration.task.complete.v1`, `k1.orchestration.task.failed.v1`, `k1.orchestration.findings.ready.v1`, `k1.orchestration.task.suspended.v1`

**Front Emits (6 topics):**
`k1.response.ack.v1`, `k1.orchestration.task.dispatch.v1`, `k1.orchestration.task.cancel.v1`, `k1.orchestration.task.resume.v1`, `k1.orchestration.clarification.response.v1`, `k1.response.final.v1`

### Back Actor (`actors/back.py`)

| Function | Purpose |
|----------|---------|
| `back_handler` | SS snapshot → Back prompt → ReAct → result emit |
| `back_resume_handler` | Resume context → fresh SS snapshot → continue ReAct |
| `back_cancel_handler` | CancellationToken / legacy fallback |
| `route_back_envelope` | dispatch / resume / cancel / clarification / dead-letter |
| `_read_ss_snapshot` | Selective SessionState read contract |
| `_budget_to_iterations` | Budget conversion |
| `_filter_back_tools` | Tool filtering by tier |
| `_maybe_rebind_back_dispatcher` | Dispatcher rebinding |
| `_serialize_messages` | Serialize for checkpoint |
| `_deserialize_messages` | Deserialize from checkpoint |
| `_build_react_checkpoint` | Build ReAct checkpoint |
| `_emit_back_result` | task.complete / task.suspended / task.failed |
| `_resolve_needs_human_in_process` | Unified HIL loop |
| Execution profile helpers | select / persist / metric record / prompt block |
| `emit_tool_started` | Emit tool started event |
| `emit_tool_completed` | Emit tool completed event |
| `emit_artifact_created` | Emit artifact created event |
| `_extract_cancel_token` | Extract cancel token |
| `_build_cancellation_check` | Build cancellation check |

**Back Subscribes To (4 topics):**
`k1.orchestration.task.dispatch.v1`, `k1.orchestration.task.cancel.v1`, `k1.orchestration.task.resume.v1`, `k1.orchestration.clarification.response.v1`

**Back Emits (8 topics):**
`k1.tool.started.v1`, `k1.tool.completed.v1`, `k1.orchestration.task.complete.v1`, `k1.orchestration.task.failed.v1`, `k1.orchestration.task.suspended.v1`, `k1.orchestration.findings.ready.v1`, `k1.session.booking.confirmed.v1`, `k1.session.artifact.created.v1`

### Supporting Actor Files

| File | Contents |
|------|----------|
| `actors/frames.py` | `BackResultFrame`, `HILResolutionFrame`, `WeavePresentationFrame`, frame helpers |
| `actors/front_hil_envelope.py` | HIL detect (`is_new_hil_envelope`, `is_legacy_bridge_envelope`), unwrap, response builders |
| `actors/back_pool.py` | `BackPool`, `WorkerSlot`, `BackPoolConfig`, `BackPoolExhausted`, `SessionLimitReached` |
| `actors/ready_queue.py` | `ReadyQueue` (dependency-ordered Back-bound envelopes), enqueue/dequeue/cycle detection |
| `actors/back_router.py` | `BackTopicRouter` (mailbox topic table), lease token |
| `actors/shared.py` | `parse_envelope_payload`, `safe_get_section`, `never_cancel` |

---

## 5. FRONT LLM TOOLS (10 total)

| # | Tool | Category | Function |
|---|------|----------|----------|
| 1 | `acknowledge_request()` | **Signal** (1) | ACK-first enforcement, iteration 1; ~100-150 tokens: restate intent + plan preview |
| 2 | `update_beliefs()` | **Cognitive** (6) | S-P-O triples + confidence |
| 3 | `update_scoreboard()` | Cognitive | QUD, referents, salience |
| 4 | `update_clarifications()` | Cognitive | Semantic gaps: field, question, severity |
| 5 | `update_narrative()` | Cognitive | Thread switch/resume/close |
| 6 | `refine_affect()` | Cognitive | Override Phase 1 emotion |
| 7 | `promote_belief()` | Cognitive | WARM-to-HOT promotion |
| 8 | `recall_memory()` | **Read** (2) | K0 long-term memory |
| 9 | `summarize_context()` | Read | Token budget compression |
| 10 | `dispatch_task()` | **Control** (1) | FSM intercepts → task.dispatch.v1 |

---

## 6. BACK LLM TOOLS (7 total)

| # | Tool | Category |
|---|------|----------|
| 1 | `recall_memory()` | **Read** (2) — Task-specific history |
| 2 | `discover_capabilities()` | Read — Fabric Registry search |
| 3 | `bind_capability()` | Binding — Exact registry name or typed degrade |
| 4 | `invoke_capability()` | **Action** (4) — Strict exact Fabric capability |
| 5 | `batch_invoke_capabilities()` | Action — Batch Fabric calls |
| 6 | `spawn_via_fabric()` | Action — Dynamic specialist agents |
| 7 | `execute_workflow()` | Action — Multi-step DAG execution |
| -- | `submit_result()` | **Control** (1) — ONLY way to end a task (complete \| needs_human) |

---

## 7. TOOLS INFRASTRUCTURE (8 files)

| File | Contents |
|------|----------|
| `tools/dispatcher.py` | `ToolDispatcher` (allowlist → budget → schema → policy → execute → record) |
| `tools/schemas_front.py` | `FRONT_TOOL_SCHEMAS` |
| `tools/schemas_back.py` | `BACK_TOOL_SCHEMAS`, `BACK_TIER_ALLOWLISTS` |
| `tools/implementations.py` | Tool implementations (update_*, recall, dispatch_task, discover, invoke, submit_result) |
| `tools/result_protocol.py` | `ToolResult` protocol |
| `tools/recovery_contract.py` | Tool recovery payloads |
| `tools/parallelism.py` | `can_parallelize`, `partition_calls` |
| `tools/schemas_fabric.py` | Fabric tool schemas |

---

## 8. REACT LOOP SYSTEM (6 files)

| File | Contents |
|------|----------|
| `react/loop.py` | `react_loop(actor='front'\|'back')`, `ReactResult` |
| `react/history.py` | `build_chat_history`, `build_chat_history_for_back` |
| `react/checkpoint.py` | `ReActCheckpoint` (suspend/resume snapshot) |
| `react/control.py` | `BackControlEvent`, `ReactLoopEvent` |
| `react/capability_routing.py` | Capability execution routing |
| `react/back_execution_plan.py` | Back execution planning |

### ReAct Recovery Patterns (5)

| Pattern | Trigger → Action |
|---------|------------------|
| `DEGENERATE` | Empty output → nudge + strip tools |
| `MALFORMED` | Invalid JSON → nudge simplify |
| `PSEUDO-CODE` | Text mimics tool → nudge real call |
| `TEXT-AFTER-TOOLS` | Back text after invoke → nudge submit |
| `LAST ITERATION` | Max iterations reached → force submit_result with partials |

### ReactLoopScratchpad (4 children — ADR-0098, ephemeral)

| Child | Description |
|-------|-------------|
| `LoopBudget` | LOW: max_tools=6, timeout=2s, tokens=500 / MEDIUM: 10, 10s, 2K / HIGH: 15, 45s, 8K |
| `tool_executions` | List[ToolExecution]: ToolCall + ToolResult pair |
| `cognitive_writes` | List[CognitiveWrite]: Audit trail (section, op, key, old/new) |
| `iteration_snapshots` | List[IterationSnapshot]: Per-iter thought/action/observation |

---

## 9. PROMPT ARCHITECTURE (10 files)

| File | Contents |
|------|----------|
| `prompt/mode.py` | `PromptMode` enum, `determine_mode` |
| `prompt/builder.py` | `DynamicPromptBuilder`, `BuiltContext`, `SS_READ_CONFIGS` |
| `prompt/affect.py` | `compute_affect_band` |
| `prompt/scenario_templates.py` | Mode scenario rendering |
| `prompt/sections.py` | Composable prompt sections |
| `prompt/back_prompt.py` | `build_back_prompt`, executor prompt contract |
| `prompt/back_profiles.py` | `select_back_execution_profiles`, render profile block |
| `prompt/clarify_depth.py` | Clarification depth logic |
| `prompt/domain_rules.py` | Domain rule injection |

### Prompt Modes (10)

| Mode | Tools | ~Tokens | Use Case |
|------|-------|---------|----------|
| `STANDARD` | 10 | ~5500 | Normal turn |
| `CLARIFY_ASK` | 3 | ~2200 | Asking user for clarification |
| `CLARIFY_RESOLVE` | 7 | ~3800 | Resolving clarification |
| `HITL_RELAY` | 0 | ~1200 | Relaying HITL to user |
| `HITL_RESOLVE` | 2 | ~2000 | Resolving HITL |
| `PRESENT` | 2 | ~3000 | Presenting results |
| `WEAVE` | 2 | ~3200 | Weaving async results |
| `CANCEL` | 3 | ~2000 | Cancellation flow |
| `INTERRUPT` | 10 | ~5500 | Interrupt handling |
| `ERROR` | 1 | ~1800 | Error response |

### Prompt Components (10 composable sections)

| Section | ~Tokens |
|---------|---------|
| `IDENTITY` | ~150 |
| `REACT_RHYTHM` | ~200 |
| `STATE_INTERP` | ~200 |
| `COGNITIVE_DISCIPLINE` | ~150 |
| `DISPATCH_RULES` | ~350 |
| `EMOTIONAL_CALIB` | ~100 |
| `SAFETY_HITL` | ~300 |
| `WEAVE_PROTOCOL` | ~100 |
| `ANTI_PATTERNS` | ~150 |
| `MODE_EXAMPLES` | ~200/mode |

### Affect Bands (5)

| Band | max_tokens | vocab | tools |
|------|-----------|-------|-------|
| `CRISIS` | 512 | simple | 2 |
| `LOW` | 1024 | simple | 3 |
| `NEUTRAL` | no cap | standard | all |
| `POSITIVE` | 2048 | rich | all |
| `ELEVATED` | 1536 | standard | all |

### Domain Rules (8)

| Domain | Rule |
|--------|------|
| `health` | AMBER, never diagnose |
| `finance` | AMBER, exact amounts |
| `elder_care` | Simple lang, max 3 |
| `children` | Route via parent |
| `emergency` | RED, safety first |
| `legal` | RED, never advise |
| `travel` | GREEN→AMBER bookings |
| `productivity` | GREEN |

---

## 10. PROTOCOLS (18 files)

| File | Contents |
|------|----------|
| `protocols/cancellation.py` | `CancellationToken`, `CancelReason` |
| `protocols/cancel_handler.py` | `CancellationHandler` (register/cancel/late-complete dedupe) |
| `protocols/cancel_events.py` | Cancel event types |
| `protocols/task_lease.py` | `TaskLease`, `LeaseStatus`, renewal/token |
| `protocols/suspension.py` | Suspension limits, `SuspensionResolutionNotFound` |
| `protocols/suspension_events.py` | Suspension event types |
| `protocols/hitl_flow.py` | Parse approval/selection resolution |
| `protocols/hitl_wiring.py` | `ResumeContext`, relay/resolve config |
| `protocols/hitl.py` | Core HITL types |
| `protocols/hitl_persistence.py` | HITL persistence |
| `protocols/hitl_pipeline.py` | HITL pipeline |
| `protocols/weave_policy.py` | Weave delivery decisions |
| `protocols/weave_batcher.py` | Weave batching (500ms window) |
| `protocols/weave_state.py` | Weave state tracking |
| `protocols/delivery_strategy.py` | `DeliveryStrategyEngine` (13-rule decision table D1-D13) |
| `protocols/opp_pipeline.py` | OPP Pipeline (8 primitives, 9 hooks) |
| `protocols/trust_accumulator.py` | OPP-4 Trust Accumulator |

### HITL Variants (3)

| Variant | Timeout |
|---------|---------|
| Clarification | 60s |
| Approval | 120s |
| Selection | 90s |

### OPP Primitives (8)

| # | Name | Description |
|---|------|-------------|
| OPP-1 | Paced Delivery | Stagger/group/prioritize output |
| OPP-2 | Recency Bias Decay | Decay scores by age (0.15/turn) |
| OPP-3 | Affect Hard Caps | Cap response by affect band |
| OPP-4 | Trust Accumulator | Auto-approve at trust ≥ 0.85 |
| OPP-5 | Proactive Scheduler | Idle detection → proactive fill |
| OPP-6 | Episodic Compression | Compress old turns to episodes |
| OPP-7 | Dynamic Identity | Role adaptation (EXPERT/PEER/GUIDE/SUPPORTER/EXECUTOR) |
| OPP-8 | Natural Flow Delivery | 13-rule decision table (D1-D13) |

---

## 11. SESSION STATE (10 sections — HOT 52KB + WARM 48KB)

### Cognitive Sections (Front LLM Writes)

| Section | Size | Description |
|---------|------|-------------|
| `beliefs_active` | 8KB | S-P-O triples + confidence; evict to WARM after 20 turns |
| `scoreboard` | 6KB | QUD stack, referents, salience; rewritten per turn |
| `affective_now` | 4KB | Emotion, valence, arousal, trend; priority: later write wins |
| `clarifications` | 4KB | Semantic gaps: field, question, severity; clear after 5 turns |
| `narrative_active` | 4KB | Thread state, switches, summaries; summarize after 50 turns |

### System Sections (FSM / Phase1 Writes)

| Section | Size | Description |
|---------|------|-------------|
| `control` | 8KB | FlowState, TurnLock, IntentClass, DomainCtx, SafetyCtx, active_tasks, lock_version, turn_sequence_number |
| `history_active` | 8KB | TypedHistoryEntry[] (9 types); sliding window: 20 entries |
| `meta` | 2KB | Turn count, latency, telemetry |

### Task Sections (FSM via DeltaAggregator)

| Section | Size | Description |
|---------|------|-------------|
| `task_state` | 4KB | TaskStateEntry per task; Status: DISPATCHED/IN_PROGRESS/SUSPENDED/COMPLETED/FAILED/CANCELLED |
| `task_artifacts` | 4KB | Durable outputs: confirmations, appointments, documents; evict to WARM after 10 turns |

### Static

| Section | Description |
|---------|-------------|
| `persona` | Immutable: Tone, personality, family, prefs |

### WARM Tier (48KB)

| Section |
|---------|
| `beliefs_warm` |
| `history_warm` |
| `artifacts_warm` |
| `narrative_warm` |

### MutationGuard (3-Tier Validation)

1. Section capacity
2. HOT/WARM budget
3. Overall limit
4. Emergency: >95% → ALL writes rejected

---

## 12. DELTA SYSTEM (8 files)

| File | Contents |
|------|----------|
| `delta/session_delta.py` | `SessionDelta` (sections/operations/dedup key) |
| `delta/topics.py` | Delta topic constants (`ARTIFACT_CREATED`, `TASK_STATE_CHANGED`, `STATE_UPDATED`) |
| `delta/aggregator.py` | `DeltaAggregator` (500ms batch, LWW merge by section+key, ordered by parent_id) |
| `delta/applicator.py` | `DeltaApplicator` (preflight → write → evict → notify) |
| `delta/emitters.py` | `emit_artifact`, `emit_task_state_change` |
| `delta/overflow.py` | `SectionOverflowHandler` (section budgets / eviction) |
| `delta/snapshot_reader.py` | `SnapshotReader`, `SectionSnapshot` |
| `delta/writer_registry.py` | `WriterRole`, `SECTION_WRITERS`, `SingleWriterViolation` |

---

## 13. BUS (4 files + topic taxonomy)

| File | Contents |
|------|----------|
| `bus/topics.py` | Topic constants (front/back/task/HIL/weave/pool) |
| `bus/builders.py` | Envelope builders (task/response/HIL/tool/metric/dead-letter) |
| `bus/setup.py` | Router registration (`ACTOR_FRONT=front_half`, `ACTOR_BACK=back_half`) |
| `bus/deserialize.py` | Payload decode helpers |

### Bus Topics (20+)

#### Session Events

| Topic | Priority |
|-------|----------|
| `k1.session.user.input.v1` | URGENT |
| `k1.session.booking.confirmed.v1` | REALTIME |
| `k1.session.artifact.created.v1` | INTERACTIVE |

#### Response Events

| Topic | Priority |
|-------|----------|
| `k1.response.ack.v1` | URGENT |
| `k1.response.final.v1` | URGENT |
| `k1.response.clarification.v1` | URGENT |

#### Orchestration Events

| Topic | Priority |
|-------|----------|
| `k1.orchestration.task.dispatch.v1` | STRICT |
| `k1.orchestration.task.complete.v1` | STRICT |
| `k1.orchestration.task.failed.v1` | STRICT |
| `k1.orchestration.task.cancel.v1` | URGENT |
| `k1.orchestration.task.suspended.v1` | STRICT |
| `k1.orchestration.task.resume.v1` | STRICT |
| `k1.orchestration.findings.ready.v1` | STRICT |
| `k1.orchestration.task.accepted.v1` | STRICT |
| `k1.orchestration.delta.v1` | STRICT |
| `k1.orchestration.dag.completed.v1` | STRICT |

#### Tool Events

| Topic | Priority |
|-------|----------|
| `k1.tool.started.v1` | STRICT |
| `k1.tool.completed.v1` | STRICT |

#### Clarification Events

| Topic | Priority |
|-------|----------|
| `k1.orchestration.clarification.request.v1` | STRICT |
| `k1.orchestration.clarification.response.v1` | STRICT |

#### Internal / Relaxed Topics

| Topic | Priority |
|-------|----------|
| `k1.affect.update.v1` | RELAXED |
| `k1.proactive.fill.v1` | RELAXED |
| `k1.internal.weave.batch.v1` | INTERNAL |
| `k1.hil.request.v1` | STRICT |
| `k1.hil.response.v1` | STRICT |
| `turn.complete.v1` | BACKGROUND |

### Bus Infrastructure

| Component | Description |
|-----------|-------------|
| `LocalBus` | `BusFactory.create_local_ordered()` |
| `TimingChain` | Causal ordering via parent_id; STRICT: buffer until parent delivered; RELAXED: deliver immediately; gap_timeout: 5s |
| `MailboxRouter` | Actor-to-actor routing; WFQ priority scheduling |

---

## 14. EVENTS (9 files)

| File | Contents |
|------|----------|
| `events/base.py` | `CanonicalEventMeta`, required metadata, validation |
| `events/conversation.py` | `UserInputReceived`, `IntentArbitrated`, `DeadLettered`, `ResponseDelivered`, `TaskRouted` |
| `events/task.py` | `TaskCreated`, `TaskLeased`, `TaskProgressed`, `TaskCompleted`, `TaskFailed`, `TaskCancelled` |
| `events/hitl.py` | `HILRequested`, `HILResolved`, `TaskSuspended`, `TaskResumed`, HITL lifecycle events |
| `events/weave.py` | `WeaveCandidateArrived`, `WeaveDecisionMade`, `WeaveEmitted`, `WeaveMetricsEvent` |
| `events/mutation.py` | `TurnMutationSummary` (ledger-only mutation stats) |
| `events/pool.py` | `BackPoolWorker*`, `TaskLease*`, `TaskDeferred`, `DependencyFailed` |
| `events/registry.py` | `EVENT_TYPE_REGISTRY`, resolve/deserialize |
| `events/validator.py` | `validate_event`, `validate_event_chain` |

---

## 15. EXPERIENCE LAYER (7 files, 6 components)

| Component | File | Status | Trigger |
|-----------|------|--------|---------|
| `ExperienceLayer` | `experience/layer.py` | REAL | Orchestrates all processors |
| `EmotionalProcessor` | `experience/emotional_processor.py` | REAL | Every 25th turn, 5ms |
| `AffectiveMirror` | `experience/affective_mirror.py` | REAL | After EP, 2ms |
| `NarrativeWeaver` | `experience/narrative_weaver.py` | STUB | Every 20th turn, 10ms |
| `AnticipatoryResponder` | `experience/anticipatory_responder.py` | STUB | Every 30th turn, 15ms |
| `ProactiveAgent` | `experience/proactive_agent.py` | STUB | OPP-5, idle detection 5000ms, cooldown 15000ms, max 10/session |
| `RhythmController` | `experience/rhythm_controller.py` | REAL | Every output, 1ms |

---

## 16. ACKING CORE — Phase 1 Pipeline

### UltraBERT v4 (22ms, 12 Heads, Single Forward Pass)

| Head | Output |
|------|--------|
| Intent Head V2 (MULTI-LABEL) | 8 classes: log_memory, set_reminder...; primary + all[] + scores{} |
| Ingress Head V2 (MULTI-LABEL) | 12 domains: HEALTH, FINANCE...; domains[] above threshold |
| Safety Head | 4 bands: GREEN, AMBER, RED, CRISIS |
| Emotions Head | 44 classes: joy, sadness, anxiety... |
| Sentiment Head | 5 levels: very_negative to very_positive |
| NER Heads (3x GlobalPointer) | General: PER, ORG, LOC, MISC / Family: PERSON, KINSHIP, PET, HOME_LOC... / Temporal: DATE_ABS, DATE_REL, TIME, DURATION, FREQUENCY, AGE |
| Relations Head | 15 types: parent_of, child_of, spouse_of, sibling_of, pet_of... |

### Pipeline Sub-Stages

| Stage | Description |
|-------|-------------|
| Safety Gate | Crisis Detector + Safety Override; evaluates FIRST, before any routing |
| Complexity Router V2 | Multi-factor: intent_count, domain_count, safety_band, emotion → Tier |
| Hypothesis & Gap Detection | Hypothesis Generator, Contract & Signal Gap Detector, Signal Library |
| Time Resolution | Time Parser → Time Resolver → Timezone Context |
| Spatial/Temporal/Grounding | Runtime reference |
| Context Inference | SessionState fill + entity resolution |
| Tiny Sanity Arbiter | UltraBERT + cached checks (fast path) |
| Uncertainty Estimation | UltraBERT confidence scores → Entropy-Minimizing Question Planner (1-2 Qs max) |
| OPP-2 Recency Bias Decay | Arbiter.classify() with decay_per_turn=0.15; short input (<3 words) = 50% overlap penalty |
| Write Elision Gate | Per-section signal significance scoring; low-signal turns: ELIDE writes, carry forward |

### Write Elision (`acking/write_elision.py`)

| Component | Description |
|-----------|-------------|
| `WriteElisionGate` | Per-section signal significance scoring |
| `WriteElisionDecision` | Low-signal turns: ELIDE writes, carry forward |
| Safety band | ALWAYS written (CONC-05) |
| Intent/domains | If significant |
| Entities/temporal | If detected |
| Emotions/sentiment | If non-neutral |
| Backchannels | 1 write (safety), 5 elisions |

---

## 17. SECTION UPDATE (15 files — LLM classifier pipeline)

| File | Contents |
|------|----------|
| `section_update/apply.py` | Section update application |
| `section_update/classifier.py` | Section classifier |
| `section_update/events.py` | Section update events |
| `section_update/idempotency.py` | Idempotency tracking |
| `section_update/input_builder.py` | Input construction |
| `section_update/lifecycle.py` | Lifecycle management |
| `section_update/live_api.py` | Live API surface |
| `section_update/llm_classifier.py` | LLM-based classifier |
| `section_update/overlay.py` | Overlay management |
| `section_update/plan_compiler.py` | Plan compilation |
| `section_update/prompt.py` | Classification prompts |
| `section_update/types.py` | Type definitions |
| `section_update/vocabulary.py` | Vocabulary management |
| `section_update/worker.py` | Worker execution |

---

## 18. TASK MODEL (12 files)

| File | Contents |
|------|----------|
| `task/dispatch.py` | `TaskDispatch`, `TaskComplete`, `TaskFailed` (front → back payload contract) |
| `task/intent.py` | `TaskIntent` (capability/params/urgency) |
| `task/complexity.py` | `ComplexityTier`, `budget_for_tier` |
| `task/envelope_bridge.py` | dispatch_to_envelope / complete_to_envelope / failed_to_envelope |
| `task/receiver.py` | `TaskReceiver` (dispatch subscription, active task tracking) |
| `task/dependency_queue.py` | `TaskDependencyQueue` (depends_on / $ref hydration) |
| `task/bundled_executor.py` | Bundled execution |
| `task/classifier.py` | Task classification |
| `task/parallel_safety.py` | Parallel execution safety |
| `task/tools.py` | Task tool bindings |
| `task/topics.py` | Task topic constants |

### Complexity Tiers (4)

| Tier | Latency | Tool Calls | Tokens | Path |
|------|---------|------------|--------|------|
| `LOW` | <2s | 4 (max 6) | 500 | Front → dispatch → Back → invoke → submit |
| `MEDIUM` | 2-10s | 8 (max 10) | 2K | Front → dispatch → OrchestratorStub (1-2 Fabric calls) |
| `HIGH` | 10-45s | 12 (max 15) | 8K | Front → TaskEnvelope → Orchestrator → Planner 4-stage → DAG |
| `CRISIS` | 5s | 0 | hardcoded | Safety Protocol → hardcoded string, zero deps |

### Tier Degradation Cascade

```
HIGH (CB_PLANNER open) → MEDIUM (CB_ORCH open) → LOW (CB_FABRIC open) → canned response
```

---

## 19. ORCHESTRATOR (3 files)

| File | Contents |
|------|----------|
| `orchestrator/routing.py` | `route_task`, `route_task_sync` (LOW direct Back / MED-HIGH orchestrator envelope) |
| `orchestrator/types.py` | `Budget`, `TaskEnvelope`, `AggregatedResult`, `PlanRequest`, `PlanStep`, `CommittedPlan` |
| Orchestrator tier budgets + wiring gate | Inline: fabric budget, planner token budget; `OrchestratorNotWired` for HIGH without orchestrator |

---

## 20. LLM INTERNAL (6 files)

| File | Contents |
|------|----------|
| `llm/types.py` | `ModelMessage`, `ToolSchema`, `StreamChunk`, `ToolCallResult` |
| `llm/validator.py` | `LLMOutputValidator` (tool name/required params/type checks; retry 1x, lower temp) |
| `llm/model_hub_bridge.py` | Model hub adapter surface |
| `llm/model_hub_adapter.py` | Provider adapter |
| `llm/gemini_adapter.py` | Gemini provider adapter |
| `llm/model_selection.py` | Model selection table: (CHAT, front)→flash, (TOOL_CALL, *)→pro, (STRUCTURED,*)→flash, (REASON, back)→pro |
| `llm/ports.py` | `IConciergeModelPort` (wraps ILLMPort) |

---

## 21. CONFIG (5 files)

| File | Contents |
|------|----------|
| `config/loader.py` | `get_config`, typed config tree |
| `config/concierge.py` | `ConciergeConfig` (feature gates/session toggles) |
| `config/kernel.py` | Kernel config |
| `config/defaults.yaml` | Default configuration |

### Config Objects

| Config | Purpose |
|--------|---------|
| `FrontActorConfig` | Front actor settings |
| `BackActorConfig` | Back actor settings |
| `FsmConfig` | Pending result depth/TTL, idempotency, dead-letter |
| `ReactConfig` | Loop fallback, HIL limits |
| `ProtocolsConfig` | Protocol settings |
| `BackPoolConfig` | Pool size, session limit, lease TTL |

---

## 22. OBSERVABILITY (8 files)

| File | Contents |
|------|----------|
| `obs/metrics.py` | `MetricsCollector`, `MetricEnvelope`, `TurnTimer` |
| `obs/actor_metrics.py` | `FrontOutcome`, `BackOutcome`, `record_front_metrics`, `record_back_metrics` |
| `obs/fsm_metrics.py` | Transition count, dwell metrics |
| `obs/hitl_metrics.py` | HITL protocol decision metrics |
| `obs/weave_metrics.py` | Weave metrics |
| `obs/arbiter_metrics.py` | Arbiter metrics |
| `obs/react_metrics.py` | ReAct loop metrics |
| `obs/alerts.py` | Alert definitions |

---

## 23. LEDGER (4 files)

| File | Contents |
|------|----------|
| `ledger/store.py` | `LedgerEntry`, `ILedgerStore`, `InMemoryLedgerStore` |
| `ledger/writer.py` | `LedgerWriter` (append/append_sync/idempotency) |
| `ledger/projections.py` | `project_task_states`, cancel/history/hitl/pending_results |
| `ledger/recovery.py` | `CrashRecoveryOrchestrator` (recover → FSM rebuild hooks) |

---

## 24. COMPRESSION (2 files)

| File | Contents |
|------|----------|
| `compression/turn_shape.py` | `history_entries_to_opp_turns` (canonical history → OPP turn dict) |
| `compression/episodic_compressor.py` | `EpisodicCompressor`, `CompressedEpisode`, `CompressionConfig` |

---

## 25. REMAINING MODULES

| Module | File(s) | Status |
|--------|---------|--------|
| **Identity** | `identity/dynamic_identity.py` — `DynamicIdentityContext`, `IdentitySnapshot.to_prompt_block`, `ConversationalRole` (EXPERT/PEER/GUIDE/SUPPORTER/EXECUTOR), `DynamicIdentityConfig` | REAL |
| **Scheduler** | `scheduler/proactive_scheduler.py` — `ProactiveScheduler`, `ProactiveSchedulerConfig` (idle threshold/cooldown/suppressions/max per session) | REAL |
| **Services** | `services/recall_service.py` — `RecallService` (typed `RecallRequestV1` client, offline empty fallback) | REAL |
| **Fabric** | `fabric/ports.py` — `IFabricPort` (execute/execute_batch/discover/prompts) | REAL |
| **Kernel** | `kernel/bootstrap.py`, `kernel/runner.py` — re-exports k1.kernel bootstrap/runner | REAL |
| **Types** | `types/__init__.py` — pure re-export hub (Envelope/IBus/TaskEnvelope/AggregatedResult/Capability*/Hub*) | REAL |
| **Affective** | `affective/__init__.py` — planned MS-4; future affective_now tracking / Fabric affective routing | STUB |
| **Empathy** | `empathy/__init__.py` — planned MS-4; future emotional inference → affective_now / beliefs_active | STUB |
| **Rhythm** | `rhythm/__init__.py` — planned MS-4; live code in `experience/rhythm_controller.py` | STUB |

---

## 26. RUNTIME WIRING (3 files)

| File | Contents |
|------|----------|
| `factory.py` | `PortBundle`, `ConciergeFactory` (mailboxes/dispatchers/ports) |
| `session.py` | `ConciergeRuntime._mailbox_consumer` (front_handler + route_back_envelope) |
| `ports.py` | All 8 port protocol definitions |

---

## 27. STREAMING INFRASTRUCTURE (8 components, ~150 tests)

| Component | ~Tests | Purpose |
|-----------|--------|---------|
| `StreamConsumer` | 25 | Consume `AsyncIterator[HubChunk]`, backpressure, cancel |
| `ChunkRouter` | 20 | Route by chunk_type: text/tool_call_delta/thinking/error/done |
| `TextChunkAggregator` | 15 | Flush at word boundaries, ~5 tokens/SSE |
| `ToolCallStreamHandler` | 25 | Accumulate JSON fragments, parse on complete |
| `ThinkingTraceHandler` | 15 | Capture REASON capability traces |
| `StreamingSSEEmitter` | 20 | Wrap chunks → OutputEvent → OutputManager REALTIME |
| `StreamCancellationGuard` | 15 | Handle user interrupts mid-stream |
| `PartialResponseBuffer` | 15 | Buffer partial text for FSM state transitions |

---

## 28. INTERNAL SERVICES (9 codeable components, ~585 tests)

| Service | ~Tests | Purpose |
|---------|--------|---------|
| `FSMController` | 60 | `transition()`, `current_state()`, `on_interrupt()`, `tick_experience()` |
| `TurnProcessor` | 90 | `start_turn()`, `execute_phase1()`, `route_dispatch()`, `execute_phase2()`, `end_turn()` |
| `IntentProcessor` | 110 | SafetyGate → Hypothesis → TimeResolver → ContextInference → SanityArbiter → UncertaintyEstimator |
| `ComplexityRouter` | 45 | 5 factors: intent_count, domain_count, safety_band, emotion, combined |
| `ToolDispatcher` | 80 | `dispatch()`, `get_buffered_results()`; enforces allowlist by state/tier/safety |
| `OutputManager` | 55 | `enqueue()`, `deliver_next()`, `flush()`; 9 event types, 3 priority levels |
| `DeltaAggregator` | 50 | `start_window()`, `receive()`, `flush()`; 500ms, LWW merge |
| `ClarificationTracker` | 40 | `track_round()`, `max_reached()`, `escalate()`, `add_pending()`, `get_pending()` |
| `ContextAssembler` | 55 | `assemble()`, `track_usage()`; CONTEXT_PROFILES, TOKEN_ESTIMATOR |

---

## 29. CIRCUIT BREAKERS (7)

| CB | Owner | Threshold | Degradation |
|----|-------|-----------|-------------|
| `CB_SSE` | SSEOutputAdapter | 5s reconnect, 3/min | Polling mode |
| `CB_MODEL` | UltraBERT + ModelGateway | — | Heuristic fallback / canned response |
| `CB_SESSIONSTATE` | SessionKernelAdapter | 100ms, 10/min | Stale cached data |
| `CB_ORCHESTRATOR` | FabricOrchestratorAdapter | 60s, 2/min | Degrade to LOW tier |
| `CB_PLANNER` | FabricOrchestratorAdapter | 45s, 2/min | Skip planning |
| `CB_FABRIC` | FabricOrchestratorAdapter (Concierge owns) | 30s, 5/min | Mark unavailable |
| `CB_MCP` | FabricOrchestratorAdapter (Concierge owns) | 10s, 3/min | Mark tool unavailable |

---

## 30. LIFECYCLE PHASES (6)

| Phase | Steps |
|-------|-------|
| `init` | 1. Create 9 services (no I/O) / 2. Connect 8 ports / 3. Restore state (Edge-First: LOCAL COLD first) / 4. Load persona → PersonaEngine + Style / 5. Init 7 circuit breakers → all CLOSED / 6. Start subscriptions + DeltaAggregator timer / 7. FSM → LISTENING |
| `turn_start` | 1. Acquire Single Writer lock (lock_version++) / 2. Increment turn_sequence_number / 3. Read HOT snapshot (all sections) / 4. Reset: ToolDispatcher, ClarificationTracker, ContextAssembler / 5. Allocate tier budget envelope |
| `turn_end` | 1. Flush OutputManager / 2. Append history_active (MutationGuard) / 3. Update telemetry (tokens, cost, latency) / 4. Release Single Writer lock / 5. Checkpoint LOCAL COLD (SQLite <1ms) / 6. Checkpoint K0 (fire-and-forget via Bridge) / 7. Check experience triggers (% 20/25/30) / 8. Emit turn.complete.v1 via IDeltaPort |
| `turn_end_abbreviated` | 1. Cancel in-flight dispatches / 2. Flush OutputManager (partial) / 3. Record turn_status: INTERRUPTED / 4. Release lock, checkpoint LOCAL COLD / SKIP: history, telemetry, K0, experience |
| `shutdown` | 1. IInputPort.close() (reject new input) / 2. Wait active turn (30s) or force-close / 3. Flush DeltaAggregator + OutputManager / 4. Final checkpoint (LOCAL COLD + K0 5s wait) / 5. Stop background (timer, subscriptions, SSE) / 6. Disconnect ports (LIFO: Memory → Input) |
| `crash_recovery` | 1. Bootstrap (9 services + 8 ports) / 2. Detect: check turn_lock in SS_CONTROL / 3. Rollback: clear lock, lock_version++ / 4. Reconcile Local Outbox (Bridge drain) / 5. Restore from LOCAL COLD / 6. Resume: persona, CBs, subscriptions, LISTENING / Max loss: 1 turn |

---

## 31. INVARIANTS (21 rules, 6 categories)

### OWNERSHIP (INV-01..04)

| # | Rule |
|---|------|
| 01 | Only Concierge writes SS |
| 02 | Every cognitive write → MutationGuard.preflight() |
| 03 | Phase 1 completes before Phase 2 |
| 04 | Orchestrator/Planner/Agents NEVER write SS |

### SAFETY (INV-05..07)

| # | Rule |
|---|------|
| 05 | Safety Gate evaluates FIRST |
| 06 | CRISIS = immediate protocol, bypasses FSM |
| 07 | safety_band written BEFORE any routing |

### RATE LIMITS (INV-08..12)

| # | Rule |
|---|------|
| 08 | Tool calls/turn: 20 |
| 09 | Clarification rounds/intent: 3 |
| 10 | Output queue depth: 50 |
| 11 | Workflow depth: 3 |
| 12 | Concurrent active turns/session: 1 |

### TIMING (INV-13..14)

| # | Rule |
|---|------|
| 13 | FSM transition ≤ 1ms (no I/O) |
| 14 | Delta aggregation = 500ms fixed |

### STRUCTURAL (INV-15..17)

| # | Rule |
|---|------|
| 15 | All output through OUTPUT_CHANNEL |
| 16 | Internal services call ports, never external |
| 17 | Single FSM — no secondary FSMs |

### TOKEN BUDGET (INV-18..21)

| # | Rule |
|---|------|
| 18 | LLM context window: 128K tokens |
| 19 | Intent ack: 150 tokens |
| 20 | Preliminary ack: 200 tokens |
| 21 | Clarification: 300 tokens |

---

## 32. EXTERNAL TOUCHPOINTS

| Touchpoint | Description |
|------------|-------------|
| **Orchestrator** | Blind DAG executor (NO LLM, NO tools); Topological Walker; Step Retry (2 retries) |
| **Planner** | LLM-powered 4-stage: Sketch → Expand → Validate → Commit; 4 discovery tools (read-only); HIL: Requirement Clarification + Plan Approval |
| **Capability Fabric** | Dual role: Intelligent Retrieval (serves Planner) + Resolution/Execution; Agent Factory; 9-Step Pipeline; Capability Registry |
| **Model Hub** | Capability routing, Caching, Budgets, CBs; Plugin-based providers (manifest-driven); Output Validation: T1 FORMAT (<1ms) → T2 SAFETY (<5ms) → T3 BELIEF (<50ms) |
| **Bridge (K0)** | Cross-kernel transport + auth + retries; SSE Receiver for K0 event stream |
| **Output System** | OUTPUT_CHANNEL (Unified: SSE/WebSocket/REST); Output Queue: REALTIME > PROGRESS > BACKGROUND |
| **Memory Writer** | 0-3 factual memories/turn |
| **Learning Loop** | 5 feedback detectors: correction, validation, reformulation, abandonment, hedging |
| **Dynamic Agents** | Ephemeral, TTL-based, scoped snapshot; NEVER write SS, mutate via Delta Bus |
| **Safety Agent** | CRISIS protocol handler |

---

## 33. ERROR RECOVERY (3 Severity Levels)

| Severity | Behavior |
|----------|----------|
| **RECOVERABLE** | Retry/fallback in same phase; MutationGuard reject → skip write; Delta emit fail → log + skip; Memory timeout → skip memory |
| **DEGRADED** | Continue with partial results; LLM CB OPEN → canned response; SS read timeout → stale cache; Tier degradation → lower tier |
| **TERMINAL** | Error response to DELIVERING; 3 consecutive LLM failures; All degradation exhausted |

### Canned Responses (7 by call_type)

`ack`, `prelim_ack`, `clarify`, `LOW`, `MED`, `HIGH`, `CRISIS` (hardcoded constant, zero deps)

---

## 34. PERFORMANCE BASELINES

| Metric | Value |
|--------|-------|
| UltraBERT inference | 25ms P99 |
| Intent ack SSE | 50ms P99 |
| FSM transition | 1ms P99 |
| MutationGuard | 0.2ms |
| Phase 1 write | 0.02ms |
| Phase 2 write | 0.1ms |
| Output → SSE | 5ms |
| Orch dispatch | 2ms |
| **Total overhead/turn** | **~32ms** (excluding LLM) |
| Single LLM timeout | 30s |
| Planner stage timeout | 10s/stage |

---

## SUMMARY COUNTS

| Category | Count |
|----------|-------|
| Ports | 8 |
| Production Adapters | ~14 |
| Test Adapters | ~9 |
| FSM Files | 16 |
| Actor Files | 9 |
| Front Tools | 10 |
| Back Tools | 7 |
| Tool Infrastructure Files | 8 |
| ReAct System Files | 6 |
| Prompt Files | 10 |
| Prompt Modes | 10 |
| Prompt Components | 10 |
| Protocol Files | 18 |
| OPP Primitives | 8 |
| Delta System Files | 8 |
| Bus Files | 4 |
| Bus Topics | 20+ |
| Event Files | 9 |
| Experience Components | 6 (3 real, 3 stub) |
| Section Update Files | 15 |
| Task Model Files | 12 |
| Orchestrator Files | 3 |
| LLM Internal Files | 6 |
| Config Files | 5 |
| Observability Files | 8 |
| Ledger Files | 4 |
| Compression Files | 2 |
| Streaming Components | 8 |
| Internal Services | 9 |
| Circuit Breakers | 7 |
| Lifecycle Phases | 6 |
| Invariants | 21 |
| FSM States | 11 |
| Guard Actions | 5 |
| Session State Sections | 10 HOT + 4 WARM |
| Affect Bands | 5 |
| Domain Rules | 8 |
| HITL Variants | 3 |
| Complexity Tiers | 4 |
| **Total Source Files** | **~170+** |
| **Estimated Tests** | **~735** |

Good question. Here's my analysis of the visit order, driven by architecture dependency chains and blast radius.

---

## Strengthening Visit Order — Ranked by Criticality

### The Dependency Stack (bottom-up)

The architecture has a clear dependency pyramid. If layer N is broken, everything above it produces garbage regardless of correctness:

```
┌─────────────────────────────────┐
│   Experience / Obs / CBs        │  ← Refinement
├─────────────────────────────────┤
│   Protocols (HITL/Weave/Cancel) │  ← Coordination
├─────────────────────────────────┤
│   ReAct Loop + Tool Dispatcher  │  ← Core execution
├─────────────────────────────────┤
│   Prompt Architecture           │  ← What the LLM sees
├─────────────────────────────────┤
│   Bus + Delta System            │  ← Communication
├─────────────────────────────────┤
│   Session State + MutationGuard │  ← Shared memory
├─────────────────────────────────┤
│   FSM Controller                │  ← The brain
└─────────────────────────────────┘
```

---

### TIER 1 — FOUNDATION (visit FIRST)

**If these break, literally nothing works. No partial degradation possible.**

#### 1. FSM Controller + States + Transition Table

- Everything flows through the FSM. 11 states, 5 guard actions, 6 lifecycle phases, error severity classification (RECOVERABLE/DEGRADED/TERMINAL).
- **Why first:** A wrong state transition corrupts the entire turn. A missing transition = deadlock. The `SingleWriterInvariant` is enforced here. If the FSM lets two things write SS simultaneously, you get silent corruption that's near-impossible to debug.
- **Key files:** `fsm/controller.py`, `fsm/states.py`, `fsm/transition_table.py`, `fsm/front_lock.py`

#### 2. Session State + MutationGuard + Write Elision Gate

- Shared memory between two minds that don't know each other exist. 10 HOT sections + 4 WARM sections. The 3-tier MutationGuard (section capacity → tier budget → overall limit) is the ONLY thing preventing SS corruption from runaway writes.
- **Why second:** The Write Elision Gate decides what gets persisted vs. carried forward. If it over-elides, context is lost. If it under-elides, SS bloats. MutationGuard emergency mode (>95% capacity) must work — otherwise you get turn failures under load.
- **Key files:** Delta system writes to SS; `acking/write_elision.py`; MutationGuard is embedded in the state adapter

#### 3. Bus Infrastructure (LocalBus + TimingChain + MailboxRouter)

- Front and Back communicate exclusively through the bus. 20+ topics with STRICT/RELAXED/URGENT priorities. TimingChain enforces parent_id causal chains — if a `task.complete` arrives before `task.dispatch`, the system must buffer, not crash.
- **Why third:** If the bus drops messages or violates causal ordering, the two minds desync. The MailboxRouter's WFQ priority scheduling must not starve URGENT topics. The 5s gap_timeout on TimingChain must be tuned correctly.
- **Key files:** `bus/setup.py`, `bus/builders.py`, `bus/topics.py`; the bus core lives in k1_bus_core

---

### TIER 2 — CORE EXECUTION (visit SECOND)

**If these break, specific turns fail but the system can degrade.**

#### 4. ReAct Loop + Checkpoint + Recovery Patterns

- Both Front and Back use the same `react_loop()`. This is the actual LLM interaction loop. 5 recovery patterns (DEGENERATE, MALFORMED, PSEUDO-CODE, TEXT-AFTER-TOOLS, LAST ITERATION). The scratchpad tracks tool_executions, cognitive_writes, and iteration_snapshots.
- **Why fourth:** The loop budget (max_iterations per tier) and cancellation check (between iterations) are hard guards. If a recovery pattern fails to fire, the loop spins until timeout. Checkpoint serialization/deserialization must be perfect for HITL suspend/resume.
- **Key files:** `react/loop.py`, `react/checkpoint.py`, `react/control.py`, `react/history.py`

#### 5. Tool Dispatcher + Tool Implementations

- Front: 10 tools. Back: 7 tools. The dispatcher enforces allowlists by state/tier/safety. A tool executing in the wrong state = invariant violation. A tool failing silently = Back never calls `submit_result()` = task hangs forever.
- **Why fifth:** The allowlist is multi-dimensional (state × tier × safety_band). The `bind_capability()` tool is especially tricky — it must do exact registry name matching OR typed degrade, and failure must route to `submit_result(needs_human)`, not silent hang.
- **Key files:** `tools/dispatcher.py`, `tools/implementations.py`, `tools/schemas_front.py`, `tools/schemas_back.py`

#### 6. Prompt Architecture (DynamicPromptBuilder + Modes + Sections)

- 10 modes, 10 composable sections, 5 affect bands, 8 domain rules. This is what the LLM actually sees. The 128K context window with 80% safety margin means ~102K usable tokens — if the builder overshoots, truncation happens silently.
- **Why sixth:** A wrong mode selection (e.g., STANDARD when HITL_RELAY is needed) gives the LLM tools it shouldn't have. Domain rule injection (health=AMBER never diagnose, legal=RED never advise) is a safety boundary. If domain rules don't inject, the LLM gives dangerous advice.
- **Key files:** `prompt/builder.py`, `prompt/mode.py`, `prompt/domain_rules.py`, `prompt/affect.py`, `prompt/back_prompt.py`

---

### TIER 3 — COORDINATION (visit THIRD)

**If these break, complex multi-step scenarios fail but simple turns still work.**

#### 7. Protocols (HITL + Weave + Cancel + Suspend)

- HITL: 3 variants (Clarification 60s, Approval 120s, Selection 90s). Max 2 suspensions per task. OPP-4 Trust Accumulator auto-approves at trust ≥ 0.85. Weave: 500ms batch window, 13-rule delivery decision table (D1-D13). Cancel: cooperative token-based, dedup against late completion.
- **Why seventh:** These are the hardest coordination patterns. HITL suspend/resume must preserve ReAct history. Weave batching must flush ONCE with ALL results, not N separate Front invocations. Cancel must handle the race between `task.complete` and `task.cancel`.
- **Key files:** `protocols/hitl_flow.py`, `protocols/hitl_wiring.py`, `protocols/weave_batcher.py`, `protocols/weave_policy.py`, `protocols/cancel_handler.py`, `protocols/suspension.py`

#### 8. Delta System (Aggregator + Applicator)

- 500ms batch window, LWW merge by section+key, ordered by parent_id. The applicator does preflight → write → evict → notify. This is how Back's work (deltas) reaches SS without Back ever writing SS directly.
- **Why eighth:** If the aggregator merges wrong (e.g., newer delta overwritten by older due to parent_id misorder), task state is wrong. If overflow handler doesn't evict correctly, SS bloats silently.
- **Key files:** `delta/aggregator.py`, `delta/applicator.py`, `delta/overflow.py`, `delta/writer_registry.py`

#### 9. Back Pool + Ready Queue

- BackPool manages concurrent Back workers with leases. ReadyQueue does dependency-ordered envelope dispatching. Cycle detection, circular dependency handling, lease expiry.
- **Why ninth:** Pool exhaustion (`BackPoolExhausted`) and dependency failures must degrade gracefully. If a lease expires while Back is mid-ReAct, you get zombie tasks.
- **Key files:** `actors/back_pool.py`, `actors/ready_queue.py`, `protocols/task_lease.py`

---

### TIER 4 — REFINEMENT (visit LAST)

**These improve quality but the system functions without them.**

#### 10. ACKING Core — UltraBERT Pipeline

- Already well-baked (22ms, 12 heads). The heuristic fallback when CB_MODEL is open is the main thing to verify.
- **Key files:** `acking/write_elision.py`; UltraBERT is external

#### 11. Experience Layer (6 components, 3 real + 3 stub)

- The 3 stubs (NarrativeWeaver, AnticipatoryResponder, ProactiveAgent) need to be made real. The 3 real components (EmotionalProcessor, AffectiveMirror, RhythmController) need integration testing.
- **Key files:** `experience/layer.py`, `experience/*.py`

#### 12. Observability + Metrics + Circuit Breakers

- 8 obs files, 7 CBs. These are monitoring/defense, not core functionality. Important for production but not for correctness.
- **Key files:** `obs/*.py`

#### 13. Section Update Pipeline (15 files)

- LLM-based classifier for section updates. This is a secondary path; the primary path is Front cognitive tools writing SS directly.
- **Key files:** `section_update/*.py`

---

### Summary: The Strengthening Pass Order

| Pass | Tier | Components | Why |
|------|------|------------|-----|
| **1** | Foundation | FSM → Session State → Bus | If these are wrong, nothing else matters |
| **2** | Core Execution | ReAct Loop → Tool Dispatcher → Prompt Architecture | These are the actual turn mechanics |
| **3** | Coordination | Protocols (HITL/Weave/Cancel) → Delta System → Back Pool | Complex scenarios |
| **4** | Refinement | ACKING → Experience → Obs/CBs → Section Update | Quality and monitoring |

The principle: **fix the foundation before you fix what runs on it.** A bug in FSM state transitions will manifest as "mysterious" failures in every other component. A bug in the ReAct loop recovery patterns will look like a Prompt or Tool problem. Start at the bottom of the dependency pyramid.
