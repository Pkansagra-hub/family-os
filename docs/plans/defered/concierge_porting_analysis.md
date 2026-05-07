# Concierge POC → Production Porting Analysis

**Scope**: `poc/k1_poc/fsm/`, `poc/k1_poc/kernel/`, `poc/k1_poc/delta/`
**Generated**: Exhaustive code read of all 31 files (~5,500+ lines)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Folder 1: FSM (`poc/k1_poc/fsm/`)](#2-folder-1-fsm)
   - [File Inventory](#21-file-inventory)
   - [Classes, Enums, Protocols](#22-classes-enums-protocols)
   - [Functions & Constants](#23-functions--constants)
   - [FSM States & Transitions](#24-fsm-states--transitions)
   - [Bus Topics & Subscriptions](#25-bus-topics--subscriptions)
   - [Cross-Dependencies](#26-cross-dependencies)
   - [Design Patterns](#27-design-patterns)
   - [POC Shortcuts & Hardcoded Values](#28-poc-shortcuts--hardcoded-values)
   - [Thread Safety & Concurrency](#29-thread-safety--concurrency)
   - [Error Handling](#210-error-handling)
   - [Controller Decomposition Plan](#211-controller-decomposition-plan)
   - [Porting Target & Complexity](#212-porting-target--complexity)
3. [Folder 2: Kernel (`poc/k1_poc/kernel/`)](#3-folder-2-kernel)
   - [File Inventory](#31-file-inventory)
   - [Classes & Functions](#32-classes--functions)
   - [Bootstrap Wiring Order](#33-bootstrap-wiring-order)
   - [Cross-Dependencies](#34-cross-dependencies)
   - [POC Shortcuts](#35-poc-shortcuts)
   - [Porting Target & Complexity](#36-porting-target--complexity)
4. [Folder 3: Delta (`poc/k1_poc/delta/`)](#4-folder-3-delta)
   - [File Inventory](#41-file-inventory)
   - [Classes & Functions](#42-classes--functions)
   - [Cross-Dependencies](#43-cross-dependencies)
   - [Design Patterns](#44-design-patterns)
   - [POC Shortcuts](#45-poc-shortcuts)
   - [Porting Target & Complexity](#46-porting-target--complexity)
5. [Global Cross-Dependency Map](#5-global-cross-dependency-map)
6. [Production Gaps Summary](#6-production-gaps-summary)
7. [Recommended Porting Order](#7-recommended-porting-order)

---

## 1. Executive Summary

The Concierge POC implements a **full FSM-based conversation controller** with:
- 11 FSM states, ~30 subscribed bus topics, a 198-cell guard matrix
- Single-writer delta aggregation with 500ms batching
- Priority-based front-lock serialization
- Phase 1 deterministic classification (UltraBERT) before LLM dispatch
- Adaptive weave delivery (M8) with 5 delivery modes
- HITL (Human-in-the-Loop) suspension/resume with crash recovery
- Conversation arbiter for interrupt classification (4 decisions)

**Controller is the critical bottleneck**: `controller.py` is ~4,080 lines and must be decomposed into 6-8 focused modules for production. The delta and kernel folders are cleaner and port more directly.

**Estimated total production effort**: High. The FSM folder alone requires significant refactoring; delta and kernel are medium effort each.

---

## 2. Folder 1: FSM (`poc/k1_poc/fsm/`)

### 2.1 File Inventory

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `__init__.py` | ~40 | Package re-exports |
| 2 | `states.py` | ~30 | ConciergeState enum (11 states) |
| 3 | `transition_table.py` | ~250 | Transition table, guard matrix, topic subscriptions |
| 4 | `errors.py` | ~25 | IllegalTransitionError, FrontLockOverflowError |
| 5 | `turn_state.py` | ~120 | FSMTurnState: pending/deferred result queues |
| 6 | `arbiter.py` | ~200 | ConversationArbiter: interrupt classification |
| 7 | `front_lock.py` | ~100 | FrontLock: priority queue serialization gate |
| 8 | `idempotency.py` | ~50 | IdempotencyLedger: LRU dedup cache |
| 9 | `phase1.py` | ~120 | Phase1Result, Phase1Pipeline protocol, StubPhase1Pipeline, TurnLock |
| 10 | `dead_letter.py` | ~50 | DeadLetterPayload dataclass + builder |
| 11 | `dead_letter_consumer.py` | ~80 | DeadLetterConsumer: stats tracking |
| 12 | `history_writer.py` | ~100 | HistoryWriter: typed history entry management |
| 13 | `task_bridge.py` | ~180 | TaskBridge: task lifecycle + SS binding |
| 14 | `interrupt_handler.py` | ~60 | InterruptClassifier (keyword), ProactiveWakeHandler |
| 15 | `ultrabert_adapter.py` | ~150 | UltraBERTAdapter protocol + K1 impl + LRU/TTL cache |
| 16 | `ultrabert_phase1.py` | ~200 | UltraBERTPhase1Pipeline: real Phase 1 mapping |
| 17 | `response_final_table.py` | ~150 | ResponseFinalAction enum, decide_response_final() pure function |
| 18 | `control_extension.py` | ~80 | ConciergeControlExtension: FSM ↔ SS overlay |
| 19 | `controller.py` | ~4,080 | ConciergeController: THE central FSM event router |

**Total**: ~5,865 lines across 19 files.

### 2.2 Classes, Enums, Protocols

#### Enums

| Enum | File | Values |
|------|------|--------|
| `ConciergeState` | states.py | LISTENING, DISPATCHING, COMPANIONING, PROGRESSING, DELIVERING, CLARIFYING_USER, CLARIFYING_WORKER, CANCELLING, INTERRUPT_HANDLING, PROACTIVE_WAKE, WEAVING |
| `GuardAction` | transition_table.py | TRANSITION, PASSTHROUGH, OBSERVE, QUEUE, DEAD_LETTER |
| `ArbiterDecision` | arbiter.py | CANCEL, MODIFY_INFLIGHT, PARALLEL_NEW, DEFER |
| `ResponseFinalAction` | response_final_table.py | TRANSITION_LISTENING, TRANSITION_WEAVING, TRANSITION_COMPANIONING, STAY, IGNORE, DEAD_LETTER |
| `WriterRole` (imported) | delta/writer_registry.py | FRONT_LLM, PHASE1, FSM, EXPERIENCE_LAYER, SESSION_INIT |

#### Dataclasses / Frozen Dataclasses

| Class | File | Key Fields |
|-------|------|------------|
| `FSMTurnState` | turn_state.py | pending_results (deque), deferred_results (list), max_depth=16, ttl_seconds=300 |
| `ArbiterResult` | arbiter.py | decision, confidence, target_task_id, modification_params, routing_metadata, phase1 |
| `InflightTask` | arbiter.py | task_id, action, domain, status, progress_pct, dispatch_turn, pending_hil, entities |
| `InflightContext` | arbiter.py | tasks, pending_results, cancelled_task_ids, fsm_state, current_turn, pool fields |
| `ArbiterConfig` | arbiter.py | domain_overlap_threshold, entity_overlap_threshold |
| `FrontLock` | front_lock.py | busy, event_queue (deque), max_queue_depth=8 |
| `Phase1Result` | phase1.py | 13 __slots__: intents, entities, salience_map, primary_emotion, emotion_confidence, valence, arousal, intent_classification, domain_context, safety_band, complexity_tier, temporal_expressions, relations, _degraded |
| `DeadLetterPayload` | dead_letter.py | original_topic, original_envelope_id, reason, fsm_state_at_rejection, turn_number, task_id, original_payload_summary, rejected_at_ns |
| `ResponseFinalDecision` | response_final_table.py | action, target_state, emit_turn_completed, drain_front_lock, schedule_weave, release_front_lock, entry_type (frozen) |
| `TypedHistoryEntry` | controller.py | __slots__: turn_number, entry_type, role, text, timestamp_ms, source, task_id, metadata |
| `RunningTaskHandle` | controller.py | task_id, inject_message (for inter-iteration MODIFY_INFLIGHT) |

#### Regular Classes

| Class | File | Key Methods |
|-------|------|-------------|
| `ConversationArbiter` | arbiter.py | classify(text, phase1, inflight) → ArbiterResult |
| `IdempotencyLedger` | idempotency.py | check_and_mark(envelope_id, turn_number), contains(), reset() |
| `StubPhase1Pipeline` | phase1.py | classify(text) → Phase1Result (keyword-based) |
| `TurnLock` | phase1.py | acquire(), release() (boolean flag, NOT asyncio.Lock) |
| `DeadLetterConsumer` | dead_letter_consumer.py | handle(envelope), snapshot() |
| `HistoryWriter` | history_writer.py | write_entry(), get_front_messages(), get_back_context() |
| `TaskBridge` | task_bridge.py | dispatch/activate/suspend/resume/complete/fail/cancel_task(), rebind() |
| `InterruptClassifier` | interrupt_handler.py | classify(text) → bool |
| `ProactiveWakeHandler` | interrupt_handler.py | should_wake(), record_wake() |
| `ConciergeControlExtension` | control_extension.py | set_fsm_state(), add/remove_active_task(), bind_control_section() |
| `ConciergeController` | controller.py | ~50+ methods (see §2.11 decomposition) |

#### Protocols

| Protocol | File | Method |
|----------|------|--------|
| `Phase1Pipeline` | phase1.py | classify(text) → Phase1Result |
| `UltraBERTAdapter` | ultrabert_adapter.py | analyze(text) → dict\|None, is_available() → bool, get_metrics() → dict |

#### Adapter Implementations

| Class | File | Notes |
|-------|------|-------|
| `K1UltraBERTAdapter` | ultrabert_adapter.py | Real impl, LRU/TTL cache, thread-safe singleton, SHA256 cache keys |
| `StubUltraBERTAdapter` | ultrabert_adapter.py | Returns None (test mode) |
| `UltraBERTPhase1Pipeline` | ultrabert_phase1.py | Maps 12-head output → Phase1Result, graceful degradation |

### 2.3 Functions & Constants

#### Module-Level Functions

| Function | File | Signature | Purpose |
|----------|------|-----------|---------|
| `is_legal()` | transition_table.py | (state, trigger) → bool | Check transition legality |
| `target_state()` | transition_table.py | (state, trigger) → ConciergeState | Get target state |
| `build_dead_letter_payload()` | dead_letter.py | (envelope, reason, state, turn, task_id) → DeadLetterPayload | Factory |
| `history_to_front_messages()` | history_writer.py | (history, window=20) → list[dict] | Last 20 entries for Front LLM |
| `history_to_back_context()` | history_writer.py | (history, window=5) → list[dict] | Last 5 filtered for Back LLM |
| `build_inflight_context()` | arbiter.py | (task_bridge, turn_state, ...) → InflightContext | Assemble arbiter input |
| `domain_overlap()` | arbiter.py | (d1, d2) → float | Domain similarity (hardcoded dict) |
| `entity_overlap()` | arbiter.py | (e1, e2) → float | Jaccard entity overlap |
| `decide_response_final()` | response_final_table.py | (state, has_pending, has_deferred, ...) → ResponseFinalDecision | Pure 13-branch truth table |
| `get_ultrabert_adapter()` | ultrabert_adapter.py | () → UltraBERTAdapter | Thread-safe singleton factory |
| `_parse_payload()` | controller.py | (envelope) → dict | JSON payload extraction |
| `_coerce_tier()` | controller.py | (raw) → str | Normalize complexity tier |
| `_task_dispatch_from_payload()` | controller.py | (payload, envelope) → Envelope | Build task dispatch envelope |
| `_build_canonical_event()` | controller.py | (task_id, result, ...) → dict | Normalize task result shape |
| `sort_results_for_delivery()` | controller.py (imported) | (results) → list | Sort results by urgency/timestamp |

#### Key Constants

| Constant | File | Value | Purpose |
|----------|------|-------|---------|
| `FRONT_HISTORY_WINDOW` | history_writer.py | 20 | Max history entries for Front |
| `BACK_HISTORY_WINDOW` | history_writer.py | 5 | Max history entries for Back |
| `PRUNE_COMPLETED_AFTER_TURNS` | task_bridge.py | 10 | Auto-prune completed tasks |
| `EVICT_ARTIFACTS_AFTER_TURNS` | task_bridge.py | 10 | Auto-evict old artifacts |
| `CANCEL_KEYWORDS` | interrupt_handler.py | 9 words (frozenset) | Keyword-based cancel detection |
| `_DEFAULT_DEFER_KEYWORDS` | arbiter.py | 14 keywords | Defer intent detection |
| `_DEFAULT_CANCEL_KEYWORDS` | arbiter.py | 9 keywords | Cancel intent detection |
| `_CANCEL_ALL_KEYWORDS` | arbiter.py | 6 phrases | "cancel all/everything" detection |
| `_RELATED_DOMAINS` | arbiter.py | dict | Hardcoded domain relationships |
| `ENTITY_MIN_CONFIDENCE` | ultrabert_adapter.py | 0.65 | NER confidence threshold |
| `SENTIMENT_TO_VALENCE` | ultrabert_adapter.py | dict | Sentiment → [-1,1] mapping |
| `HIGH_AROUSAL_EMOTIONS` | ultrabert_adapter.py | frozenset | Emotion → high arousal |
| `LOW_AROUSAL_EMOTIONS` | ultrabert_adapter.py | frozenset | Emotion → low arousal |

### 2.4 FSM States & Transitions

#### State Diagram (11 states)

```
LISTENING ──user.input──→ DISPATCHING
DISPATCHING ──phase1_complete──→ COMPANIONING
COMPANIONING ──tool.started──→ PROGRESSING
PROGRESSING ──tool.completed──→ COMPANIONING
COMPANIONING ──task.complete──→ DELIVERING (or WEAVING via M8)
DELIVERING ──response.final──→ LISTENING (or WEAVING)
WEAVING ──response.final──→ LISTENING
COMPANIONING ──task.suspended──→ CLARIFYING_WORKER
CLARIFYING_WORKER ──task.resume──→ COMPANIONING
LISTENING ──proactive events──→ PROACTIVE_WAKE ──routed──→ DELIVERING
Any ──interrupt in flight──→ INTERRUPT_HANDLING ──routed──→ varies
```

#### Transition Table (TRANSITION_TABLE)

The table maps `(state, trigger)` → `target_state`. Key synthetic triggers:

| Synthetic Trigger | Purpose |
|---|---|
| `TRIGGER_PHASE1_COMPLETE` | Phase 1 classification done → COMPANIONING |
| `TRIGGER_CLARIFICATION_DETECTED` | Sub-task needs user clarification |
| `TRIGGER_PENDING_RESULTS_NON_EMPTY` | Weave results available |
| `TRIGGER_INTERRUPT_ROUTED` | Interrupt classified, route to target |
| `TRIGGER_PROACTIVE_ROUTED` | Proactive wake routed |
| `TRIGGER_SAME_TURN_COMPLETE` | Same-turn completion (CLARIFYING_WORKER shortcut) |
| `TRIGGER_DEFERRED_HITL` | Deferred HITL surfaced post-LISTENING |

#### Guard Matrix (FULL_GUARD_TABLE)

198-cell matrix (11 states × ~30 topics). Each cell contains a `GuardAction`:
- **TRANSITION**: Legal state change, proceed
- **PASSTHROUGH**: Allow processing, no state change
- **OBSERVE**: Log/monitor only
- **QUEUE**: Enqueue via FrontLock for later
- **DEAD_LETTER**: Reject, send to dead-letter topic

The guard is checked before EVERY handler invocation via `_guard_dispatch()`.

### 2.5 Bus Topics & Subscriptions

**SUBSCRIBED_TOPICS** (frozenset, ~30 topics):

| Topic Constant | Topic String | Handler |
|---|---|---|
| `TOPIC_USER_INPUT` | k1.user.input.v1 | `_on_user_input` |
| `TOPIC_TASK_DISPATCH` | k1.orchestration.task.dispatch.v1 | `_on_task_dispatch` |
| `TOPIC_TASK_COMPLETE` | k1.orchestration.task.complete.v1 | `_on_task_complete` |
| `TOPIC_TASK_FAILED` | k1.orchestration.task.failed.v1 | `_on_task_failed` |
| `TOPIC_TASK_CANCEL` | k1.orchestration.task.cancel.v1 | `_on_task_cancel` |
| `TOPIC_TASK_SUSPENDED` | k1.orchestration.task.suspended.v1 | `_on_task_suspended` |
| `TOPIC_TASK_RESUME` | k1.orchestration.task.resume.v1 | `_on_task_resume` |
| `TOPIC_RESPONSE_FINAL` | k1.front.response.final.v1 | `_on_response_final` |
| `TOPIC_TOOL_STARTED` | k1.tool.started.v1 | `_on_tool_started` |
| `TOPIC_TOOL_COMPLETED` | k1.tool.completed.v1 | `_on_tool_completed` |
| `TOPIC_FINDINGS_READY` | k1.orchestration.findings.ready.v1 | `_on_findings_ready` |
| `TOPIC_CLARIFICATION_REQUEST` | k1.orchestration.clarification.request.v1 | `_on_clarification_request` |
| `TOPIC_CLARIFICATION_RESPONSE` | k1.orchestration.clarification.response.v1 | `_on_clarification_response` |
| `TOPIC_ARTIFACT_CREATED` | k1.session.artifact.created.v1 | `_on_artifact_created` |
| `TOPIC_AFFECT_UPDATE` | k1.affect.update.v1 | `_on_affect_update` |
| `TOPIC_PROACTIVE_FILL` | k1.proactive.fill.v1 | `_on_proactive_fill` |
| `TOPIC_DAG_COMPLETED` | k1.orchestration.dag.completed.v1 | `_on_dag_completed` |
| `TOPIC_WEAVE_BATCH` | k1.internal.weave.batch.v1 | `_on_weave_batch` |
| `TOPIC_UI_TYPING` | k1.ui.typing.v1 | `_on_ui_typing` |
| `TOPIC_DEAD_LETTER` | k1.internal.dead_letter.v1 | DeadLetterConsumer (separate) |

### 2.6 Cross-Dependencies

#### Imports FROM other POC packages

| Source Package | What is Imported | Used By |
|---|---|---|
| `poc.k1_poc.bus` | IBus, Envelope, Priority, PayloadFormat, IMailboxRouter, topic constants, builders | controller.py, transition_table.py, dead_letter.py |
| `poc.k1_poc.ledger` | LedgerWriter | turn_state.py, controller.py, task_bridge.py |
| `poc.k1_poc.events` | Weave events (WeaveCandidateArrived, WeaveEmitted, WeaveDecisionMade), ledger events | turn_state.py, controller.py |
| `poc.k1_poc.protocols` | WeavePolicy, WeaveSignal, WeaveDecision, WeaveDecisionResult, WeaveFallbackPolicy, UserActivityTracker, DigestPayload | controller.py |
| `poc.k1_poc.bus.builders` | build_weave_batch, build_weave_decided, build_state_updated | controller.py |
| `poc.k1_poc.orchestrator` | OrchestratorStub, PassthroughPlannerStub | controller.py |
| `poc.k1_poc.hitl` | HILCoordinator, HILSubTask, ResumeContext | controller.py |
| `poc.k1_poc.cancel` | CancellationHandler | controller.py |
| `poc.k1_poc.suspension` | SuspensionManager | controller.py |
| `k1.sessionstate` | SessionStateManager, ControlSection, TaskStateSection, TaskArtifactsSection, etc. | controller.py, task_bridge.py, control_extension.py |
| `familyos_ultrabert` | Client | ultrabert_adapter.py |

#### Imports FROM K0

None observed. The POC is self-contained within `poc/k1_poc/`.

### 2.7 Design Patterns

| Pattern | Where | Description |
|---|---|---|
| **Guard Matrix** | transition_table.py, controller._guard_dispatch() | Every event checked against 198-cell guard matrix before handler execution |
| **Single Writer Invariant** | delta/writer_registry.py | Back never writes SS; emits deltas instead |
| **FrontLock Priority Queue** | front_lock.py | 5 priority levels serialize access to Front LLM actor |
| **Turn-Based Conversation** | controller._finalize_turn() | Turn numbers monotonically increment; all state keyed by turn |
| **Idempotency via LRU** | idempotency.py | Envelope IDs deduplicated (max 500 entries) |
| **Phase 1 Before LLM** | phase1.py, controller._run_phase1() | UltraBERT deterministic classification (~22ms) runs before any LLM call |
| **Dead Letter** | dead_letter.py, dead_letter_consumer.py | Rejected events go to dead-letter topic with full provenance |
| **Pure Decision Table** | response_final_table.py | decide_response_final() is a pure function (no side effects) |
| **Weave Policy (Adaptive)** | controller._on_task_complete_adaptive() | WeavePolicy decides delivery mode (IMMEDIATE/BATCH/DEFER/DIGEST/SUPPRESS) |
| **Write-Before-Mutate** | task_bridge.py | Ledger event written before SS mutation |
| **Crash Recovery** | controller._recover_hitl_on_startup() | Scans persisted HILSubTask data to restore pending HITL on boot |
| **Inter-Iteration Injection** | RunningTaskHandle | MODIFY_INFLIGHT injects messages into running Back LLM iteration |
| **Auto-Activate** | task_bridge.py | complete_task/suspend_task auto-activate if still DISPATCHED |

### 2.8 POC Shortcuts & Hardcoded Values

| Shortcut | File | Description | Production Fix Required |
|---|---|---|---|
| **StubPhase1Pipeline** | phase1.py | Keyword-based intent/domain classification | Replace with real UltraBERT pipeline (already exists in ultrabert_phase1.py) |
| **InterruptClassifier** | interrupt_handler.py | 9-keyword cancel detection | Already superseded by ConversationArbiter; remove entirely |
| **_RELATED_DOMAINS dict** | arbiter.py | Hardcoded domain similarity (e.g., "cooking"→"nutrition") | Replace with embedding-based domain similarity |
| **Keyword defer/cancel** | arbiter.py | 14 defer keywords, 9 cancel keywords, 6 cancel-all phrases | Replace with LLM-based or classifier-based intent detection |
| **domain_overlap()** | arbiter.py | Returns 0.7 for related domains, 0.0 otherwise | Need continuous similarity scores |
| **_deliver_crisis_response()** | controller.py | Hardcoded crisis response text | Production needs configurable safety responses from policy layer |
| **HITL timeout** | controller._hitl_timeout_watcher() | asyncio.sleep-based timeout | Need persistent timer (survives restarts) |
| **_RELATED_DOMAINS hardcoded** | arbiter.py | Static dict of domain pairs | Should be config-driven or model-based |
| **TurnLock as bool flag** | phase1.py | Simple boolean, not asyncio.Lock | Fine for single-threaded async, but document the invariant |
| **SnapshotReader not atomic** | delta/snapshot_reader.py | read_multiple() not atomically consistent | Need MVCC or snapshot isolation for production |
| **ProactiveWakeHandler** | interrupt_handler.py | Simple counter; no rate limiting logic | Production needs configurable rate limits |
| **PassthroughPlannerStub** | controller._route_via_orchestrator() | HIGH complexity → medium (passthrough) | Real planner needed |
| **OrchestratorStub** | controller._route_via_orchestrator() | Stub orchestrator for routing | Real orchestrator needed (already in k1/orchestrator/) |

### 2.9 Thread Safety & Concurrency

| Component | Safety Model | Notes |
|---|---|---|
| **ConciergeController** | Single-threaded async (event loop) | All handlers are sync, called from async consumer; no internal locking |
| **FrontLock** | Single-threaded access assumed | No lock; relies on single event loop |
| **IdempotencyLedger** | OrderedDict (not thread-safe) | Fine for single-threaded async |
| **TurnLock** | Boolean flag (not asyncio.Lock) | Intentional: sync guard within async context |
| **K1UltraBERTAdapter cache** | threading.Lock | Thread-safe; adapter may be called from thread pool |
| **DeltaAggregator** | asyncio (single loop) | Timer uses asyncio.Task |
| **SnapshotReader** | dict.copy() for lock-free reads | POC limitation: no atomic multi-section reads |
| **FSMTurnState** | No locking | Single-threaded assumption |
| **WeavePolicy.decide()** | Called synchronously | No internal state mutation concern |

**Production concern**: The entire FSM is designed for single-threaded async execution. Any move to multi-threaded or multi-process requires adding locks to FrontLock, FSMTurnState, IdempotencyLedger, and the controller itself.

### 2.10 Error Handling

| Pattern | Where | Behavior |
|---|---|---|
| **Guard rejection → Dead Letter** | _guard_dispatch() | Invalid state → dead-letter with reason |
| **Idempotency rejection** | check_and_mark() | Duplicate envelope_id → skip silently |
| **FrontLock overflow** | _enqueue() | Rejects lowest-priority event; FrontLockOverflowError |
| **IllegalTransitionError** | _transition() | Raised but caught in handlers → dead-letter |
| **WeavePolicy exception** | _on_task_complete_adaptive() | Falls back to WeaveFallbackPolicy |
| **UltraBERT unavailable** | UltraBERTPhase1Pipeline | Graceful degradation to StubPhase1Pipeline |
| **HITL timeout** | _hitl_timeout_watcher() | Auto-cancel task after timeout |
| **Task complete with no task** | _on_task_complete() | Logs warning, proceeds with "unknown" task_id |
| **Crash recovery** | _recover_hitl_on_startup() | Scans HILSubTask data; re-surfaces pending HILs |
| **BUG-4a/b/c fixes** | _flush_weave_now, etc. | Re-enqueue results when FrontLock rejects delivery |
| **BUG-2 fix** | _mark_results_deferred() | Force-deliver results exceeding max_consecutive_defers |
| **BUG-3 fix** | _suppress_result() | Only suppress targeted task's result, not all |
| **BUG-5 fix** | _schedule_weave_flush_adaptive() | Don't transition to DELIVERING prematurely |
| **BUG-6 fix** | teardown() | Cancel digest flush task (was missing) |
| **BUG-7 fix** | _reset_all_components() | Removed duplicate state reset block |

### 2.11 Controller Decomposition Plan

The ~4,080-line `controller.py` should be split into these focused modules:

| Module | Methods to Extract | Est. Lines |
|---|---|---|
| **fsm_core.py** | `_transition()`, `_guard_dispatch()`, `_topic_guard()`, `_publish_dead_letter()`, `_finalize_turn()`, state management, subscription wiring | ~300 |
| **user_input_handler.py** | `_on_user_input()`, `_run_phase1()`, `_run_phase1_with_arbiter()`, `_write_phase1_to_ss()`, `_check_deferred_results_on_input()` | ~400 |
| **interrupt_router.py** | `_handle_interrupt()`, `_handle_arbiter_cancel()`, `_handle_arbiter_modify()`, `_handle_arbiter_defer()`, `_handle_arbiter_parallel_new()`, `_enrich_envelope_with_arbiter()` | ~350 |
| **task_lifecycle.py** | `_on_task_dispatch()`, `_route_via_orchestrator()`, `_on_dag_completed()`, `_on_task_complete()`, `_on_task_complete_adaptive()`, `_on_task_complete_legacy()`, `_on_task_failed()`, `_on_task_cancel()` | ~600 |
| **hitl_handler.py** | `_on_task_suspended()`, `_on_task_resume()`, `_recover_hitl_on_startup()`, `_hitl_timeout_watcher()`, `_surface_deferred_hitl()` | ~400 |
| **weave_delivery.py** | `_on_response_final()`, `_execute_response_final_decision()`, `_build_weave_envelope()`, `_schedule_weave_flush()`, `_flush_weave_after_delay()`, `_flush_weave_now()`, all adaptive methods (`_deliver_weave_immediate`, `_schedule_weave_flush_adaptive`, `_mark_results_deferred`, `_schedule_digest_flush`, `_flush_digest_now`, `_suppress_result`, `_emit_weave_decided`) | ~700 |
| **delivery.py** | `_deliver_to_front()`, `_deliver_to_back()`, `_deliver_crisis_response()`, `_drain_front_lock_queue()` | ~200 |
| **observability_handlers.py** | `_on_tool_started()`, `_on_tool_completed()`, `_on_findings_ready()`, `_on_clarification_request/response()`, `_on_artifact_created()`, `_on_affect_update()`, `_on_proactive_fill()`, `_on_ui_typing()`, `_on_weave_batch()` | ~300 |
| **history_integration.py** | `_write_history()`, `_emit_ledger_event()`, `_emit_intent_arbitrated_ledger()`, `_emit_turn_mutation_summary()`, `_emit_turn_completed()` | ~250 |
| **helpers.py** | `_parse_payload()`, `_coerce_tier()`, `_task_dispatch_from_payload()`, `_build_canonical_event()`, TypedHistoryEntry, RunningTaskHandle | ~200 |

**Decomposition strategy**: Use a **mediator pattern** where `ConciergeController` becomes a thin coordinator that delegates to handler modules, passing shared state via a `ControllerContext` dataclass. Each handler module is independently testable.

### 2.12 Porting Target & Complexity

**Porting Target**: `k1/concierge/` (new production module)

**K0/K1 Integration Points**:
- Bus: IBus → K0 event bus adapter (via bridge)
- Session State: Direct K1 SessionStateManager
- Ledger: K0 ledger integration via bridge
- Orchestrator: K1 orchestrator (replace stubs)
- HITL: K1 HITL coordinator

**Contract Dependencies**:
- `k0/contracts/modules/concierge.yaml` (must be created)
- `k0/contracts/pipelines/` — P02 (user input), P06 (task dispatch), P10 (weave delivery)
- Bus envelope schema
- Session state section schemas
- Phase1Result schema

**Key Invariants to Preserve**:
1. Guard matrix must be checked before EVERY handler invocation
2. Single-writer invariant (Back never writes SS directly)
3. Phase 1 must complete before Front LLM starts (TurnLock)
4. FrontLock serializes access to Front LLM
5. Dead-letter for every rejected event (full provenance)
6. Turn numbers monotonically increment
7. Write-before-mutate for ledger events
8. Idempotency dedup for envelope IDs

**Complexity Estimate**: HIGH
- Controller decomposition is the critical path
- 11-state FSM with 198-cell guard matrix must be ported exactly
- Adaptive weave delivery (M8) has 5 modes with complex interaction
- HITL crash recovery requires careful testing
- UltraBERT adapter is production-ready but needs GPU deployment story

---

## 3. Folder 2: Kernel (`poc/k1_poc/kernel/`)

### 3.1 File Inventory

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `__init__.py` | ~10 | Re-exports KernelConfig, KernelRuntime, start_kernel, stop_kernel |
| 2 | `runner.py` | ~80 | CLI entry point (argparse), async _run() with signal handling |
| 3 | `bootstrap.py` | ~1,000 | KernelConfig, KernelRuntime, start_kernel(), stop_kernel(), wiring |

**Total**: ~1,090 lines across 3 files.

### 3.2 Classes & Functions

#### Dataclasses

| Class | File | Key Fields |
|-------|------|------------|
| `KernelConfig` | bootstrap.py | ordered_bus, capture_bus, test_mode, tool_tier, session_mode, session_id, enable_experience/delta/hitl/orchestrator/ledger/dead_letter_consumer, seed_memories |
| `KernelRuntime` | bootstrap.py | bus, router, adapter, mailboxes, session_state, capability_registry, model, fsm, dispatchers, experience_layer, delta_aggregator/applicator, hitl_coordinator, orchestrator, consumer_task, ledger, dead_letter_consumer |

#### Functions

| Function | File | Purpose |
|----------|------|---------|
| `start_kernel(config)` | bootstrap.py | Full wiring: 20-step bootstrap sequence → KernelRuntime |
| `stop_kernel(runtime)` | bootstrap.py | Graceful shutdown: ledger flush → dead-letter → delta → FSM teardown → SS close |
| `_mailbox_consumer(runtime)` | bootstrap.py | Polling loop: dedup cache, front_handler + route_back_envelope |
| `_create_model(config)` | bootstrap.py | Gemini or TestModelAdapter based on env |
| `_create_session_state(config)` | bootstrap.py | Standalone or testing SessionStateManager |
| `_create_capability_registry()` | bootstrap.py | Tool registry with Back capability whitelist |
| `_tick_experience(runtime, context)` | bootstrap.py | ExperienceLayer tick → affect/tone/fill emissions |
| `_build_experience_context(runtime)` | bootstrap.py | Read SS sections for ExperienceLayer |
| `_build_recall_fn(ss)` | bootstrap.py | Memory recall with synonym expansion, stopword filtering |
| `_build_delta_applicator(runtime)` | bootstrap.py | Factory for DeltaApplicator with callbacks |

#### Internal Adapters (bootstrap.py)

| Adapter | Purpose |
|---------|---------|
| `_FabricGatewayAdapter` | Wraps bus.publish + router for OrchestratorStub |
| `_StateReadAdapter` | Read-only SS view for orchestrator |
| `_DeltaEmitAdapter` | Delta emission for orchestrator → DeltaAggregator |

### 3.3 Bootstrap Wiring Order

The `start_kernel()` function wires 20+ components in a strict dependency order:

```
 1. boot() → bus, router, adapter, mailboxes
 2. _create_model() → Gemini or Test adapter
 3. _create_session_state() → SessionStateManager
 4. _create_capability_registry()
 5. LedgerWriter + InMemoryLedgerStore (if enabled)
 6. ConciergeController(bus, router)
 7. Phase 1 pipeline (UltraBERT or Stub)
 8. Ledger → FSM
 9. History sink (SS → FSM)
10. FSM → SessionStateManager (triggers M4 rebind)
11. ToolContext (front + back) + dispatchers
12. ExperienceLayer (if enabled)
13. DeltaAggregator + DeltaApplicator (if enabled)
14. HILCoordinator (if enabled)
15. WeaveBatcher → FSM
16. WeavePolicy + UserActivityTracker → FSM
17. DeadLetterConsumer (if enabled)
18. OrchestratorStub + adapters
19. Front subscriptions
20. Mailbox consumer task
```

**Critical ordering constraints**:
- FSM must exist before Phase 1 wiring (step 6 before 7)
- SS must exist before FSM binding (step 3 before 10)
- Ledger must exist before FSM receives it (step 5 before 8)
- Delta must exist before orchestrator adapter (step 13 before 18)
- All components wired before consumer task starts (step 20 last)

### 3.4 Cross-Dependencies

| Source Package | What is Imported |
|---|---|
| `poc.k1_poc.bus` | boot(), IBus, IMailboxRouter, CaptureBus, Envelope, topics |
| `poc.k1_poc.fsm` | ConciergeController, UltraBERTPhase1Pipeline, StubPhase1Pipeline |
| `poc.k1_poc.delta` | DeltaAggregator, DeltaApplicator |
| `poc.k1_poc.hitl` | HILCoordinator |
| `poc.k1_poc.orchestrator` | OrchestratorStub |
| `poc.k1_poc.ledger` | LedgerWriter, InMemoryLedgerStore |
| `poc.k1_poc.protocols` | WeavePolicy, UserActivityTracker, WeaveBatcher |
| `poc.k1_poc.experience` | ExperienceLayer |
| `poc.k1_poc.tools` | ToolContext, ToolDispatcher |
| `k1.sessionstate` | SessionStateManager |
| `k1.model_hub` | Gemini adapter |
| `k1.agents` | FrontSubscriptions |

### 3.5 POC Shortcuts

| Shortcut | Description | Production Fix |
|---|---|---|
| **InMemoryLedgerStore** | In-memory only; lost on restart | Persistent store (SQLite/Postgres) |
| **_mailbox_consumer polling** | Fixed poll_interval sleep loop | Use asyncio.Queue or event-driven consumer |
| **Dedup cache in consumer** | Simple set(), unbounded growth potential | Use bounded LRU or IdempotencyLedger |
| **Gemini-only model** | _create_model() hardcoded to Gemini | Model registry with provider abstraction |
| **_build_recall_fn** | In-memory synonym expansion, stopword list | Real retrieval pipeline |
| **Signal handling** | SIGINT/SIGTERM → asyncio shutdown | Supervisor/process manager integration |
| **seed_memories config** | Direct memory seeding for testing | Replace with proper onboarding flow |

### 3.6 Porting Target & Complexity

**Porting Target**: `k1/kernel/` or `k1/concierge/kernel/`

**Key Decision**: Whether bootstrap lives in the concierge module or in the K1 kernel. Given the bootstrap wires concierge-specific components (FSM, FrontLock, WeavePolicy), it should live in `k1/concierge/bootstrap.py`.

**Contract Dependencies**:
- KernelConfig schema (new)
- Component lifecycle protocol (start/stop)
- Bus bootstrap contract
- Model adapter protocol

**Production Gaps**:
- No health checks or readiness probes
- No graceful degradation (component failure → partial startup not handled)
- No configuration validation (invalid combos not caught)
- No metrics emission during bootstrap

**Complexity Estimate**: MEDIUM
- Wiring order is well-defined and documented
- Main risk is the 20-step dependency chain; any production component change requires bootstrap update
- Shutdown sequence needs hardening (timeout per component)

---

## 4. Folder 3: Delta (`poc/k1_poc/delta/`)

### 4.1 File Inventory

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `__init__.py` | ~25 | Package re-exports |
| 2 | `topics.py` | ~15 | Delta bus topic constants |
| 3 | `session_delta.py` | ~80 | SessionDelta dataclass |
| 4 | `aggregator.py` | ~100 | DeltaAggregator: 500ms batch window |
| 5 | `applicator.py` | ~90 | DeltaApplicator: preflight + write + eviction |
| 6 | `emitters.py` | ~50 | emit_artifact(), emit_task_state_change() |
| 7 | `overflow.py` | ~120 | SectionOverflowHandler: per-section eviction |
| 8 | `snapshot_reader.py` | ~80 | SnapshotReader: lock-free reads |
| 9 | `writer_registry.py` | ~60 | WriterRole, SECTION_WRITERS, validate_writer() |

**Total**: ~620 lines across 9 files.

### 4.2 Classes & Functions

#### Dataclasses

| Class | File | Fields |
|-------|------|--------|
| `SessionDelta` | session_delta.py | section, key, operation, data, delta_id, source_task_id, parent_delta_id, timestamp_ns |
| `DeltaBatch` | aggregator.py | deltas, batch_id, collected_at_ns, dedup_count |
| `ApplyResult` | applicator.py | batch_id, applied, rejected, evicted, rejections |
| `SectionSnapshot` (frozen) | snapshot_reader.py | section, data, snapshot_ns, version |

#### Enums

| Enum | File | Values |
|------|------|--------|
| `WriterRole` | writer_registry.py | FRONT_LLM, PHASE1, FSM, EXPERIENCE_LAYER, SESSION_INIT |

#### Classes

| Class | File | Key Methods |
|-------|------|-------------|
| `DeltaAggregator` | aggregator.py | collect(delta), flush(), _dedup(), _causal_order() |
| `DeltaApplicator` | applicator.py | apply(batch), _apply_single(delta, result) |
| `SectionOverflowHandler` | overflow.py | check_and_evict(section, data) |
| `SnapshotReader` | snapshot_reader.py | register_section(), read(), write(), delete(), read_multiple() |

#### Functions

| Function | File | Purpose |
|----------|------|---------|
| `emit_artifact()` | emitters.py | Create SessionDelta for artifact |
| `emit_task_state_change()` | emitters.py | Create SessionDelta for task state |
| `validate_writer()` | writer_registry.py | Check if role is authorized for section |
| `enforce_writer()` | writer_registry.py | Raise SingleWriterViolation if unauthorized |

#### Constants

| Constant | File | Value |
|----------|------|-------|
| `VALID_DELTA_SECTIONS` | session_delta.py | {"task_state", "task_artifacts", "history_active", "control", "meta"} |
| `VALID_DELTA_OPERATIONS` | session_delta.py | {"set", "append", "update", "delete"} |
| `ARTIFACT_CREATED` | topics.py | "k1.session.artifact.created.v1" |
| `TASK_STATE_CHANGED` | topics.py | "k1.session.task.state.v1" |
| `STATE_UPDATED` | topics.py | "k1.session.state.updated.v1" |
| `ALL_DELTA_TOPICS` | topics.py | frozenset of above 3 |
| `SECTION_BUDGETS` | overflow.py | control=8KB, beliefs_active=8KB, scoreboard=6KB, history_active=8KB, etc. Total HOT=52KB |
| `TERMINAL_TASK_STATUSES` | overflow.py | {"COMPLETED", "FAILED", "CANCELLED"} |
| `HISTORY_WINDOW_SIZE` | overflow.py | 20 |
| `VALID_TASK_STATUSES` | emitters.py | {"DISPATCHED", "IN_PROGRESS", "SUSPENDED", "COMPLETED", "FAILED", "CANCELLED"} |
| `SECTION_WRITERS` | writer_registry.py | Dict mapping each section to authorized WriterRole list |

### 4.3 Cross-Dependencies

| Source Package | What is Imported |
|---|---|
| `k1.sessionstate` | Session state section types |
| `poc.k1_poc.bus` | IBus (for notify_fn in applicator) |

The delta folder is **the most self-contained** of the three folders. Minimal external dependencies.

### 4.4 Design Patterns

| Pattern | Component | Description |
|---|---|---|
| **Fixed-Window Batching** | DeltaAggregator | 500ms collection window, then flush |
| **Last-Write-Wins Dedup** | DeltaAggregator._dedup() | By section+key, keeps latest timestamp |
| **Topological Causal Order** | DeltaAggregator._causal_order() | parent_delta_id ordering |
| **Preflight Validation** | DeltaApplicator | preflight_fn checked before write |
| **Eviction with Retry** | DeltaApplicator._apply_single() | Evict on overflow, retry write |
| **Per-Section Budgets** | SectionOverflowHandler | 52KB total HOT budget across sections |
| **Lock-Free Reads** | SnapshotReader | dict.copy() per read; version counters |
| **Role-Based Write Auth** | WriterRegistry | Back LLM intentionally absent from WriterRole |

### 4.5 POC Shortcuts

| Shortcut | Description | Production Fix |
|---|---|---|
| **Fixed 500ms batch window** | Not adaptive to load | Adaptive window based on throughput |
| **read_multiple() not atomic** | Sections read sequentially with copy | MVCC or snapshot isolation |
| **In-memory only** | All data lost on restart | Persistent delta log (WAL pattern) |
| **SECTION_BUDGETS hardcoded** | Static dict | Config-driven budgets |
| **Simple eviction strategies** | Per-section: oldest, terminal, window | Need tuned eviction policies |
| **No delta compaction** | Deltas accumulate | Periodic compaction/merging |
| **No back-pressure from applicator** | Apply always proceeds | Flow control to aggregator |

### 4.6 Porting Target & Complexity

**Porting Target**: `k1/delta/` or `k0/delta/` (shared infrastructure)

**Key Decision**: Delta is session-state infrastructure used by the concierge. It could live in:
1. `k1/concierge/delta/` — if concierge-specific
2. `k1/delta/` — if shared across K1 modules
3. `k0/storage/delta/` — if shared with K0

Recommendation: `k1/delta/` since it's K1 session-state specific but not concierge-specific.

**Contract Dependencies**:
- SessionDelta schema (already well-defined)
- Section budget configuration schema
- WriterRole registry
- Delta topic constants

**Key Invariants**:
1. Single-writer invariant (SECTION_WRITERS)
2. Causal ordering (parent_delta_id)
3. Last-write-wins dedup semantics
4. Section budgets enforced at apply time
5. Back LLM NEVER in WriterRole

**Complexity Estimate**: MEDIUM-LOW
- Clean, well-factored code
- Main gaps are persistence and atomicity
- Well-defined interfaces (inject callbacks into DeltaApplicator)
- Most production-ready of the three folders

---

## 5. Global Cross-Dependency Map

```
                    ┌──────────────────────────────────────┐
                    │          poc/k1_poc/bus/              │
                    │  IBus, Envelope, IMailboxRouter,      │
                    │  topic constants, builders            │
                    └──────┬────────────┬──────────────────┘
                           │            │
              ┌────────────┘            └──────────────┐
              ▼                                        ▼
┌─────────────────────────┐              ┌─────────────────────────┐
│     poc/k1_poc/fsm/     │              │    poc/k1_poc/delta/    │
│                         │              │                         │
│  ConciergeController ◄──┼──────────────┤ DeltaAggregator         │
│  transition_table       │              │ DeltaApplicator         │
│  FrontLock              │              │ SessionDelta            │
│  Phase1Pipeline         │              │ WriterRegistry          │
│  ConversationArbiter    │              │ SnapshotReader          │
│  TaskBridge ────────────┼──────────────► emit_artifact()        │
│  WeavePolicy (imported) │              │ emit_task_state_change()│
└────────────┬────────────┘              └─────────────────────────┘
             │                                      ▲
             ▼                                      │
┌─────────────────────────┐                         │
│   poc/k1_poc/kernel/    │                         │
│                         │                         │
│  bootstrap.py ──────────┼─────────────────────────┘
│   start_kernel()        │      (wires DeltaAggregator
│   stop_kernel()         │       + DeltaApplicator)
│   _mailbox_consumer()   │
│                         │
│  KernelConfig ──────────┼──► enables/disables components
│  KernelRuntime ─────────┼──► holds all runtime refs
└─────────────────────────┘

External dependencies:
  ├── k1.sessionstate (SessionStateManager, sections)
  ├── k1.model_hub (Gemini adapter)
  ├── k1.agents (FrontSubscriptions)
  ├── poc.k1_poc.hitl (HILCoordinator)
  ├── poc.k1_poc.orchestrator (OrchestratorStub)
  ├── poc.k1_poc.ledger (LedgerWriter)
  ├── poc.k1_poc.protocols (WeavePolicy, UserActivityTracker)
  ├── poc.k1_poc.experience (ExperienceLayer)
  ├── poc.k1_poc.tools (ToolContext, ToolDispatcher)
  ├── poc.k1_poc.cancel (CancellationHandler)
  ├── poc.k1_poc.suspension (SuspensionManager)
  └── familyos_ultrabert (Client - GPU inference)
```

---

## 6. Production Gaps Summary

### Critical (Must Fix Before Production)

| Gap | Folder | Description |
|---|---|---|
| Controller monolith | FSM | 4,080 lines must be decomposed into 6-8 modules |
| Persistent ledger | Kernel | InMemoryLedgerStore lost on restart |
| Persistent delta log | Delta | In-memory only; no WAL/replay |
| Atomic multi-section reads | Delta | SnapshotReader.read_multiple() not atomic |
| Persistent HITL timers | FSM | asyncio.sleep timers lost on restart |
| Real orchestrator | FSM/Kernel | OrchestratorStub must be replaced |
| Real planner | FSM | PassthroughPlannerStub must be replaced |
| Configuration validation | Kernel | Invalid config combos not caught |
| Health checks | Kernel | No readiness/liveness probes |

### High (Should Fix)

| Gap | Folder | Description |
|---|---|---|
| Keyword-based arbiter | FSM | ConversationArbiter uses keyword matching; need classifier |
| Hardcoded domain similarity | FSM | _RELATED_DOMAINS dict → embedding-based |
| Hardcoded crisis response | FSM | _deliver_crisis_response() → policy layer |
| Fixed 500ms batch window | Delta | Should be adaptive |
| No delta compaction | Delta | Deltas accumulate forever |
| No back-pressure | Delta | Applicator has no flow control |
| Polling consumer | Kernel | Sleep loop → event-driven |
| Single model provider | Kernel | Gemini-only → model registry |

### Medium (Polish)

| Gap | Folder | Description |
|---|---|---|
| No metrics in bootstrap | Kernel | Component startup timing not emitted |
| Section budgets hardcoded | Delta | Should be config-driven |
| ProactiveWakeHandler basic | FSM | No rate limiting |
| TurnLock is boolean | FSM | Document single-threaded invariant |
| Consumer dedup unbounded | Kernel | Simple set, no eviction |

---

## 7. Recommended Porting Order

### Phase 1: Infrastructure (Delta + Bus contracts)

1. **Port `delta/`** → `k1/delta/`
   - Cleanest code, fewest dependencies
   - Add persistence (WAL), atomic reads, config-driven budgets
   - Produce: SessionDelta schema contract, WriterRole contract

2. **Define bus topic contracts**
   - Formalize all ~30 topic schemas
   - Register in K0 event topics registry

### Phase 2: FSM Core (decomposed)

3. **Port FSM state machine core**
   - states.py, transition_table.py, errors.py → `k1/concierge/fsm/`
   - Pure state machine, no side effects
   - Contract: guard matrix schema

4. **Port supporting FSM components**
   - front_lock.py, idempotency.py, turn_state.py, dead_letter.py/consumer → `k1/concierge/`
   - Independently testable
   - Contract: FrontLock priority levels, IdempotencyLedger capacity

5. **Port Phase 1 pipeline**
   - phase1.py, ultrabert_adapter.py, ultrabert_phase1.py → `k1/concierge/phase1/`
   - UltraBERT adapter is production-ready
   - Contract: Phase1Result schema

6. **Port arbiter + interrupt handling**
   - arbiter.py, interrupt_handler.py → `k1/concierge/arbiter/`
   - Replace keyword detection with classifier
   - Contract: ArbiterResult schema, InflightContext schema

7. **Decompose and port controller.py**
   - Split per §2.11 decomposition plan
   - Mediator pattern with ControllerContext
   - Each handler module independently testable
   - Contract: Handler → FSM core interaction protocol

### Phase 3: Bootstrap + Integration

8. **Port response_final_table.py, control_extension.py, task_bridge.py, history_writer.py**
   - These are controller support modules
   - Port alongside or immediately after controller decomposition

9. **Port kernel/bootstrap.py**
   - Adapt wiring to production component registry
   - Add health checks, config validation, metrics
   - Replace stubs with real components

10. **Integration testing**
    - End-to-end FSM state traversal tests
    - HITL suspend/resume/crash recovery
    - Weave delivery (all 5 modes)
    - Delta aggregation + application + overflow
    - Guard matrix completeness verification

---

*End of porting analysis.*
