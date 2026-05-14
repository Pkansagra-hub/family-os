# K1 Concierge — WIRING

This document traces the complete construction graph for `ConciergeRuntime` and all
internal components assembled by `ConciergeFactory.create_with_ports()`. It also traces
the runtime call graph — what calls what during a live turn.

---

## 1. Factory construction (`ConciergeFactory.create_with_ports`)

Input port bundle (from kernel P4):

```python
ConciergeFactory.create_with_ports(
    bus=session_bus,                              # per-session IBus
    router=session_router,                        # per-session IMailboxRouter
    front_mailbox=front_mailbox,                  # router.register(ACTOR_FRONT)
    back_mailbox=back_mailbox,                    # router.register(ACTOR_BACK)
    ports=PortBundle(
        delta=DeltaPortAdapter(delta_bus),        # IDeltaPort  → IBus
        input_=BusInputAdapter(session_bus),      # IInputPort  → k1.session.user.input.v1 subscriber
        output=BusOutputAdapter(back_mailbox),    # IOutputPort → ACTOR_BACK mailbox
        state=SSMStateAdapter(ssm),               # IStatePort  → SessionStateManager
        llm=model_hub,                            # ILLMPort    → shared ModelHub
        classification=phase1_pipeline,           # IClassificationPort → UltraBERT|Stub
        dispatch=FabricDispatchAdapter(           # IDispatchPort → Fabric + Orchestrator
            fabric=session_fabric,
            orchestrator=self._orchestrator,
            bus=session_bus,
            workflow_engine=...,
        ),
        memory=RecallMemoryAdapter(               # IMemoryPort → bridge recall
            recall_fn=build_recall_fn(bridge_client)
        ),
        writer=ss_writer,                         # SS mutation writer (not a concierge port)
    ),
    config=ConciergeConfig.from_kernel_config(config),
    hil_port=self._hil_service,                   # HILService | None
)
```

---

## 2. Internal components assembled during construction

`ConciergeFactory` assembles the following:

### 2.1 FSM Controller (`ConciergeController`)

```python
controller = ConciergeController(bus=session_bus, router=session_router)
```

The controller creates these sub-components in its `__init__`:

| Component | Type | Role |
|---|---|---|
| `_state` | `ConciergeState` | Current cognitive state (starts `LISTENING`) |
| `_turn_number` | `int` | Monotonic turn counter |
| `_turn_state` | `FSMTurnState` | Ephemeral per-turn data (pending/deferred results) |
| `_front_lock` | `FrontLock` | Single-writer gate for Front LLM |
| `_cancel_handler` | `CancellationHandler` | Per-task cancel token management |
| `_suspension_manager` | `SuspensionManager` | HITL suspension lifecycle |
| `_control_ext` | `ConciergeControlExtension` | FSM-specific SS overlay (fsm_state, active_task_ids, complexity_tier) |
| `_task_bridge` | `TaskBridge` | Task lifecycle mirrored into SS task_state section |
| `_phase1_pipeline` | `StubPhase1Pipeline` | Initially a stub; replaced via setter |
| `_turn_lock` | `TurnLock` | Phase 1 sequencing gate (one classification at a time) |
| `_interrupt_classifier` | `InterruptClassifier` | Legacy keyword-based interrupt detection |
| `_arbiter` | `ConversationArbiter` | Context-aware M5 interrupt arbiter |
| `_proactive_wake` | `ProactiveWakeHandler` | Proactive wake classification |
| `_history` | `list[TypedHistoryEntry]` | In-memory typed history (also persisted to SS) |
| `_active_task_ids` | `set[str]` | Currently running task IDs |
| `_idempotency` | `IdempotencyLedger` | LRU dedup for envelope re-delivery |

After construction, factory wires in optional dependencies via setters:

```python
controller.set_session_state(ssm)            # binds TaskBridge + ControlExtension to SS
controller.set_orchestrator(orchestrator)    # MEDIUM/HIGH task dispatch
controller.set_history_sink(history_sink)    # SS history_active persistence
controller.set_hitl_coordinator(hil_coord)  # HITL suspension + resolution
controller.set_weave_batcher(weave_batcher) # M8 weave queue
controller.set_ledger(ledger_writer)         # V3 event sourcing
controller.set_back_pool(back_pool)          # M7 capacity-aware arbiter
controller.set_weave_policy(weave_policy)    # M8 adaptive delivery policy
controller.set_activity_tracker(act_tracker) # M8 typing/idle signals
controller.set_opp_pipeline(opp_pipeline)    # OPP-1 through OPP-8 prompt primitives
```

### 2.2 Experience Layer

```python
ExperienceLayer()     # creates 6 sub-components at fixed cadences
```

| Sub-component | Cadence | Output type |
|---|---|---|
| `EmotionalProcessor` | every 25th turn (unless high confidence) | `EmotionalTrajectory` (valence, arousal, dominance, trend) |
| `AffectiveMirror` | chained after EmotionalProcessor | `ToneAdjustment` (warmth, formality, pace, mirror_intensity) |
| `NarrativeWeaver` | every 20th turn | `NarrativeContext` (stub) |
| `AnticipatoryResponder` | every 30th turn | `Anticipation` (stub) |
| `ProactiveAgent` | COMPANIONING state + wait > 5s | `FillMessage` (stub) |
| `RhythmController` | every turn | `TimingParams` + `ResponseStyle` |

### 2.3 Ledger

```python
ledger_store = InMemoryLedgerStore()
ledger_writer = LedgerWriter(store=ledger_store, session_id=session_id)
```

Append-only event-sourced ledger. Every canonical event (user input, task.dispatch,
task.complete, weave.emitted, hil events, dead letters) is written as a `LedgerEntry`.
Used for crash recovery and projection queries.

### 2.4 Back Pool (`BackPool`)

```python
BackPool(size=config.back_pool_size)
```

Manages concurrent Back worker coroutines. Each active task gets one worker slot.
Pool pressure (utilization > threshold) influences WeavePolicy's BATCH window
(Rule 8: wider batch window under pool pressure).

### 2.5 WeavePolicy + supporting components

```python
WeavePolicy(config=WeavePolicyConfig(...))
WeaveIntegrationRouter(policy=weave_policy)
WeaveFallbackHandler()
TypingPolicyReEvaluator(policy=weave_policy, debounce_ms=500)
WeaveMetricsCollector()
WeaveQueue(max_depth=16, batch_window_ms=500)
UserActivityTracker()
```

These form the M8 adaptive delivery subsystem — controls when pending task results
are flushed to the user. The 9-rule decision table maps `WeaveSignal` → `WeaveDecision`
(IMMEDIATE / BATCH / DEFER / DIGEST / SUPPRESS).

### 2.6 Episodic Compressor

```python
EpisodicCompressor(config=CompressionConfig(
    recent_window=10,
    episode_size=5,
    compression_strategy=CompressionStrategy.KEY_FACTS,
    preserve_hitl_turns=True,
    preserve_safety_turns=True,
    min_turns_to_compress=15,
))
```

Activates when conversation exceeds 15 turns. Compresses older turns into episodes
(~50% token reduction) while preserving HITL and safety-flagged turns verbatim.

### 2.7 Dynamic Identity Context

```python
DynamicIdentityContext(config=DynamicIdentityConfig(...))
```

Computes per-turn `IdentitySnapshot` (conversational role, domain expertise,
formality level, emotional attunement) injected into Front's system prompt via
`to_prompt_block()`. Role priority: crisis/low→SUPPORTER, HIGH→EXPERT,
inflight→EXECUTOR, >10 turns→PEER, else→GUIDE.

---

## 3. Runtime call graph — a single user turn (LISTENING → DELIVERING)

```
[User message arrives on session_bus / ACTOR_FRONT mailbox]
        │
        ▼
FSM Controller._on_user_input(envelope)
  │
  ├─ IdempotencyLedger.check(envelope_id)   → duplicate? → dead-letter
  ├─ _transition(DISPATCHING, "user.input")
  ├─ LedgerWriter.append(UserInputReceived event)
  ├─ TurnLock.acquire()
  ├─ Phase1Pipeline.classify(text)           → Phase1Result
  │     (UltraBERT ~2ms or StubPhase1Pipeline)
  ├─ ConversationArbiter.classify(text, phase1, inflight_context)
  │     → ArbiterResult (CANCEL / MODIFY_INFLIGHT / PARALLEL_NEW / DEFER)
  │
  ├─ [if LISTENING state] → direct Front dispatch
  ├─ [if COMPANIONING] → _handle_interrupt()
  │     ├─ CANCEL  → CancellationHandler.set_token(task_id) → emit task.cancel.v1
  │     ├─ MODIFY  → inject PARAMETER_UPDATE into Back's messages list
  │     ├─ DEFER   → acknowledge + continue
  │     └─ PARALLEL_NEW → increment turn, re-classify, dispatch new task
  │
  ▼
Front Actor (front_handler)
  │
  ├─ FSM state resolved (explicit or from ss.control.flow_state)
  ├─ PromptMode determined (STANDARD / INTERRUPT / WEAVE / HITL_RELAY / etc.)
  ├─ Affect band computed (compute_affect_band from affective_now section)
  ├─ Domain extracted from Phase1Result
  ├─ Family context extracted (persona section)
  ├─ Chat history built (build_chat_history, mode-specific window size)
  ├─ OPP pipeline enrichments applied:
  │     OPP-6: EpisodicCompressor (if turn_count >= 15)
  │     OPP-7: DynamicIdentityContext.compute() → IdentitySnapshot
  ├─ DynamicPromptBuilder.build() → system prompt + messages
  ├─ ILLMPort.stream_execute(HubRequest)     [streaming]
  │     ├─ ReAct loop (front tools: recall_memory, dispatch_task, request_clarification)
  │     └─ Streaming chunks → _emit_streaming_response() → response.stream.v1 on bus
  │
  ├─ Emit ordering (invariant):
  │     1. emit task.cancel.v1 (if cancel dispatches)
  │     2. emit task.dispatch.v1(s) (for each TaskDispatch)
  │     3. emit response.final.v1
  │
  ▼
  [if task.dispatch.v1 emitted]
  │
  ▼
  FSM Controller._on_task_dispatch() → _transition(COMPANIONING)
  │
  ▼
  Back Actor (back_handler) — dispatched to BackPool worker
  │
  ├─ SS snapshot read ONCE at start (beliefs, scoreboard, task_state, task_artifacts,
  │   control, history, persona) — snapshot is immutable for ReAct loop duration
  ├─ back_prompt built (system prompt with task context + SS snapshot)
  ├─ Tools filtered by tier (LOW=3, MEDIUM/HIGH=6)
  ├─ CancellationToken wired (polls cancel_token.is_cancelled() each iteration)
  ├─ ILLMPort.execute(HubRequest)            [non-streaming, structured JSON]
  │     ├─ ReAct loop (max_iterations from ComplexityTier budget: LOW=6, MED=10, HIGH=14)
  │     ├─ IDispatchPort.dispatch_direct() or .dispatch_envelope() per tool call
  │     └─ Emits tool.started.v1 / tool.completed.v1 per iteration
  ├─ Emits task.complete.v1 / task.failed.v1 / task.suspended.v1
  │
  ▼
  FSM Controller._on_task_complete() → _transition(DELIVERING)
  │
  ▼
  WeavePolicy.decide(WeaveSignal)            [M8 adaptive delivery]
  │   9 rules → IMMEDIATE / BATCH / DEFER / DIGEST / SUPPRESS
  │   Fallback: WeaveFallbackHandler (500ms BATCH)
  │
  ├─ IMMEDIATE → flush_now → front_handler (DELIVERING/WEAVING mode)
  └─ BATCH     → schedule_flush(window_ms) → timer → front_handler
                    Front reads pending results from WeaveQueue
                    Emits response.final.v1
                    FSM → _transition(LISTENING)
```

---

## 4. HITL (Human-in-the-Loop) wiring

When Back calls `request_clarification` tool:

```
Back emits task.suspended.v1
  → FSM._on_task_suspended() → _transition(CLARIFYING_WORKER)
  → SuspensionManager.record(task_id, suspension_context)
  → HILCoordinator.route(suspension)
  → Front gets HITL_RELAY mode prompt
  → Front emits hil.requested.v1 to bus
  → User responds with clarification
  → FSM._on_user_input() in CLARIFYING_WORKER → HITL response path
  → Front gets HITL_RESOLVE mode prompt
  → Front emits task.resume.v1 with resolution
  → back_resume_handler() re-reads SS, hydrates resolution, continues ReAct loop
  → Back emits task.complete.v1 / task.failed.v1
```

---

## 5. Crash recovery wiring

On session restart (process crash), before `start()`:

```python
CrashRecoveryOrchestrator.recover(fsm=controller, ledger_store=ledger_store, session_id=session_id)
```

Recovery order (dependency-safe):


1. `project_task_states(entries)` → `TaskBridge.rebuild_from_projection(task_states)`
2. `project_cancel_state(entries)` → `CancellationHandler.rebuild_from_events(entries)`
3. `project_suspension_state(entries)` → `SuspensionManager.rebuild_from_events(entries)`
4. `project_hitl_state(entries)` → `HILCoordinator.rebuild_from_events(entries)`
5. `project_pending_results(entries)` → `FSMTurnState.rebuild_from_projection(pending)`
6. History rebuilt → `report.history_entries`
7. Derive active_task_ids
8. Derive FSM state from events: priority = CLARIFYING_WORKER > WEAVING > COMPANIONING > DISPATCHING > LISTENING

---

## 6. Runtime teardown ownership

`ConciergeRuntime.stop()` owns every subscription created during Concierge construction:

1. `ConciergeController.teardown()` unsubscribes controller FSM topic handles.
2. Runtime unsubscribes `subscribe_front_events(...)` front actor handles.
3. Runtime calls `BusInputAdapter.close()` to remove the input-port subscriber on `k1.session.user.input.v1`.

Kernel session teardown calls this before closing the per-session bus, so `destroy_session()` can leave no Concierge handler refs in `LocalBus._sub_patterns`.

---

## 7. Dependency graph (construction)

```
IBus (session bus)
  └─ BusInputAdapter     → IInputPort  → k1.session.user.input.v1 subscriber
  └─ BusOutputAdapter    → IOutputPort → Front response emitter
  └─ DeltaPortAdapter    → IDeltaPort  → FSM event bus
  └─ ConciergeController.subscribe_all() [20 topic subscriptions]

IMailboxRouter (session router)
  └─ front_mailbox (ACTOR_FRONT)
  └─ back_mailbox  (ACTOR_BACK)

SessionStateManager
  └─ SSMStateAdapter     → IStatePort → SS read surface (9 sections)

ModelHub (shared, Tier 1)
  └─ ILLMPort            → Front (streaming) + Back (non-streaming)

Phase1Pipeline (shared UltraBERT | StubPhase1Pipeline)
  └─ IClassificationPort → FSM Controller

FabricDispatchAdapter (session fabric + shared orchestrator)
  └─ IDispatchPort       → Back ReAct tool calls

BridgeClient (shared, may be None)
  └─ RecallMemoryAdapter → IMemoryPort → Front recall tool

HILService (shared, may be None)
  └─ passed to ConciergeFactory → HILCoordinator wiring

InMemoryLedgerStore
  └─ LedgerWriter
  └─ CrashRecoveryOrchestrator

ExperienceLayer (6 sub-components, internal)
EpisodicCompressor (internal)
DynamicIdentityContext (internal)
BackPool (internal)
WeavePolicy + WeaveQueue + WeaveIntegrationRouter (internal M8 subsystem)
```
