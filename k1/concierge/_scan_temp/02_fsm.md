# 02 — FSM Subsystem Scan

> **Subsystem**: `k1.concierge.fsm`
> **File count**: 19 Python files
> **Scanned**: 2026-04-04 (full read of every file)

---

## Table of Contents

1. [Subsystem Overview](#1-subsystem-overview)
2. [File-by-File Analysis](#2-file-by-file-analysis)
3. [State Enum & Transition Table](#3-state-enum--transition-table)
4. [Full Guard Matrix](#4-full-guard-matrix)
5. [Cross-Component Import Map](#5-cross-component-import-map)
6. [Port / Adapter / Protocol Usage](#6-port--adapter--protocol-usage)
7. [Error Handling Patterns](#7-error-handling-patterns)
8. [Key Invariants](#8-key-invariants)

---

## 1. Subsystem Overview

The FSM subsystem is the **event router and state machine** for the Concierge POC. It is NOT a loop driver. It subscribes to bus topics, determines the system's cognitive state, routes events to the correct handler, manages concurrency between Front and Back LLMs, and controls history writes.

**Core responsibilities:**
- State transitions (11 `ConciergeState` values)
- Concurrency gating via `FrontLock` (single-writer for Front LLM)
- Ephemeral turn tracking via `FSMTurnState` (pending results, deferred results)
- History writes (sole writer to `history_active`)
- Phase 1 (UltraBERT) classification sequencing via `TurnLock`
- Interrupt / cancel / proactive wake routing
- Conversation Arbiter (deterministic intent classification vs inflight work)
- Dead-letter handling for invalid/rejected events
- Task lifecycle management via `TaskBridge`
- Response-final decision table (13 branches, pure function)
- Idempotency dedup via LRU ledger

**Design refs**: V2 Section 4 (FSM), V2 Section 5 (SS write protocols), V3 WB 3.B / 8.3 / 13.5 (Arbiter)

---

## 2. File-by-File Analysis

### 2.1 `__init__.py` (76 lines)

**Purpose**: Package re-exports. Single import surface for all FSM public symbols.

**Re-exports** (grouped):
- States: `ConciergeState`
- Controller: `ConciergeController`, `TypedHistoryEntry`
- Turn state: `FSMTurnState`
- Concurrency: `FrontLock`, `DEFAULT_MAX_QUEUE_DEPTH`, `PRIORITY_*`, `TOPIC_PRIORITY`
- Transition: `TRANSITION_TABLE`, `is_legal`, `target_state`, `TRIGGER_*`
- Phase 1: `Phase1Pipeline`, `Phase1Result`, `StubPhase1Pipeline`, `TurnLock`
- Arbiter: `InterruptClassifier`, `ProactiveWakeHandler`
- History: `HistoryWriter`, `history_to_back_context`, `history_to_front_messages`, window constants
- Dead letter: `DeadLetterPayload`, `build_dead_letter_payload`, `DeadLetterConsumer`
- Response final: `ResponseFinalAction`, `ResponseFinalDecision`, `decide_response_final`
- Task bridge: `TaskBridge`, `EVICT_ARTIFACTS_AFTER_TURNS`, `PRUNE_COMPLETED_AFTER_TURNS`
- Idempotency: `IdempotencyLedger`
- Control: `ConciergeControlExtension`
- Errors: `IllegalTransitionError`, `FrontLockOverflowError`

---

### 2.2 `states.py` (~50 lines)

**Purpose**: Defines the 11-value `ConciergeState` enum.

**Enum: `ConciergeState(Enum)`**

| Value | auto() | Entry Trigger | Active Actor |
|---|---|---|---|
| `LISTENING` | 1 | response.final OR session start | None (idle) |
| `DISPATCHING` | 2 | user.input + Phase 1 complete | Front LLM |
| `COMPANIONING` | 3 | ack emitted + task dispatched | Front (idle), Back working |
| `PROGRESSING` | 4 | tool.started received | Back LLM |
| `DELIVERING` | 5 | task.complete received | Front LLM |
| `CLARIFYING_USER` | 6 | uncertainty >= threshold | Front LLM |
| `CLARIFYING_WORKER` | 7 | task.suspended received | Front LLM |
| `CANCELLING` | 8 | task.cancel emitted by Front | Controller |
| `INTERRUPT_HANDLING` | 9 | user.input during COMPANIONING/PROG. | Front LLM |
| `PROACTIVE_WAKE` | 10 | task.complete while LISTENING | Controller |
| `WEAVING` | 11 | pending_results non-empty after final | Front LLM |

**Cross-component imports**: None (pure enum, stdlib only).

---

### 2.3 `transition_table.py` (~700 lines)

**Purpose**: Legal FSM transitions, synthetic trigger constants, full guard matrix (11 states × 30 topics = 330 cells), and `get_guard_action()` lookup.

**Classes / Enums:**

| Symbol | Type | Description |
|---|---|---|
| `GuardAction(str, Enum)` | Enum | 5 values: `TRANSITION`, `PASSTHROUGH`, `OBSERVE`, `QUEUE`, `DEAD_LETTER` |

**Constants:**

| Constant | Value | Description |
|---|---|---|
| `TRIGGER_PHASE1_COMPLETE` | `"phase1.complete"` | Synthetic — Phase 1 done |
| `TRIGGER_CLARIFICATION_DETECTED` | `"clarification.detected"` | Synthetic — Front detects ambiguity |
| `TRIGGER_PENDING_RESULTS_NON_EMPTY` | `"pending_results.non_empty"` | Synthetic — results queued |
| `TRIGGER_INTERRUPT_ROUTED` | `"interrupt.routed"` | Synthetic — interrupt classified |
| `TRIGGER_PROACTIVE_ROUTED` | `"proactive.routed"` | Synthetic — proactive wake classified |
| `TRIGGER_SAME_TURN_COMPLETE` | `"same_turn.task.complete"` | Synthetic — task completed same turn |
| `TRIGGER_DEFERRED_HITL` | `"deferred_hitl.surface"` | Synthetic — deferred HITL surfaces |

**Data structures:**

- `TRANSITION_TABLE: dict[ConciergeState, dict[str, ConciergeState | None]]` — Compact legal transitions (11 state rows, 2-6 triggers each).
- `FULL_GUARD_TABLE: dict[ConciergeState, dict[str, tuple[GuardAction, ConciergeState | None]]]` — Complete 11×30 guard matrix. Every subscribed topic has an explicit cell.
- `SUBSCRIBED_TOPICS: frozenset[str]` — 30 topics the controller subscribes to.

**Functions:**

| Function | Signature | Description |
|---|---|---|
| `is_legal()` | `(from_state, trigger) -> bool` | Check if transition is legal |
| `target_state()` | `(from_state, trigger) -> ConciergeState \| None` | Static target for a transition |
| `get_guard_action()` | `(state, topic) -> tuple[GuardAction, ConciergeState \| None]` | Full guard matrix lookup; returns `DEAD_LETTER` for unknown topics |

**State transitions (from TRANSITION_TABLE):**

```
LISTENING:
  user.input          -> DISPATCHING
  task.complete       -> PROACTIVE_WAKE
  deferred_hitl       -> CLARIFYING_WORKER

DISPATCHING:
  task.dispatch       -> COMPANIONING
  response.final      -> LISTENING
  task.cancel         -> CANCELLING
  clarification.detected -> CLARIFYING_USER
  pending_results.non_empty -> WEAVING

COMPANIONING:
  task.complete       -> DELIVERING
  task.failed         -> DELIVERING
  task.suspended      -> CLARIFYING_WORKER
  user.input          -> INTERRUPT_HANDLING
  tool.started        -> PROGRESSING
  task.cancel         -> CANCELLING
  task.dispatch       -> COMPANIONING (idempotent multi-dispatch)
  response.final      -> LISTENING
  same_turn.task.complete -> LISTENING

PROGRESSING:
  tool.completed      -> COMPANIONING
  task.complete       -> DELIVERING
  task.failed         -> DELIVERING
  task.suspended      -> CLARIFYING_WORKER
  user.input          -> INTERRUPT_HANDLING
  task.cancel         -> CANCELLING

DELIVERING:
  response.final      -> LISTENING
  pending_results.non_empty -> WEAVING

CLARIFYING_USER:
  user.input          -> DISPATCHING

CLARIFYING_WORKER:
  user.input          -> CLARIFYING_WORKER (same-turn HITL)
  task.resume         -> COMPANIONING
  response.final      -> None (decided by response_final_table)

CANCELLING:
  task.failed         -> DELIVERING

INTERRUPT_HANDLING:
  interrupt.routed    -> DISPATCHING

PROACTIVE_WAKE:
  proactive.routed    -> DELIVERING

WEAVING:
  response.final      -> LISTENING
  pending_results.non_empty -> WEAVING (re-weave)
```

**Cross-component imports**: `k1.concierge.bus.topics` (30 topic constants), `k1.concierge.fsm.states`.

---

### 2.4 `controller.py` (~1500+ lines)

**Purpose**: The central FSM event router. Subscribes to all bus topics, performs state transitions, manages concurrency, dispatches to Front/Back, and coordinates all sub-components.

**Classes:**

#### `TypedHistoryEntry`
- **Slots**: `turn_number`, `entry_type`, `role`, `text`, `timestamp_ms`, `source`, `task_id`, `metadata`
- **Methods**: `__init__()`, `to_dict() -> dict`
- **Entry types**: `"user"`, `"final"`, `"weave"`, `"clarification"`, `"hitl_request"`, `"hitl_response"`, `"error"`, `"proactive"`, `"modify"`, `"cancel_confirmed"`, `"task_dispatch"`, `"task_complete"`, `"task_suspended"`, `"task_resumed"`, `"assistant_response"`, `"proactive_fallback"`

#### `RunningTaskHandle`
- **Slots**: `task_id`, `messages`, `dispatch_payload`, `started_at`
- Used for M5 E5.5.4 inter-iteration message injection into Back's ReAct loop

#### `ConciergeController`
- **Constructor args**: `bus: IBus`, `router: IMailboxRouter`
- **Internal sub-components** (all created in `__init__`):

| Field | Type | Role |
|---|---|---|
| `_state` | `ConciergeState` | Current FSM state (starts LISTENING) |
| `_turn_number` | `int` | Turn counter (incremented on user.input) |
| `_turn_state` | `FSMTurnState` | Ephemeral pending/deferred results |
| `_front_lock` | `FrontLock` | Concurrency gate for Front LLM |
| `_cancel_handler` | `CancellationHandler` | Cancel token management |
| `_suspension_manager` | `SuspensionManager` | HITL suspension tracking |
| `_control_ext` | `ConciergeControlExtension` | FSM state overlay for SS |
| `_task_bridge` | `TaskBridge` | Task lifecycle in SS |
| `_phase1_pipeline` | `StubPhase1Pipeline` | Phase 1 classification |
| `_turn_lock` | `TurnLock` | Sequencing gate for Phase 1 |
| `_interrupt_classifier` | `InterruptClassifier` | Legacy keyword interrupt |
| `_arbiter` | `ConversationArbiter` | Context-aware arbiter (M5) |
| `_proactive_wake` | `ProactiveWakeHandler` | Proactive wake logic |
| `_history` | `list[TypedHistoryEntry]` | In-memory history |
| `_active_task_ids` | `set[str]` | Currently active tasks |
| `_idempotency` | `IdempotencyLedger` | Envelope dedup |

- **Optional wired dependencies** (set via setters):

| Setter | Field | Purpose |
|---|---|---|
| `set_orchestrator()` | `_orchestrator` | MEDIUM/HIGH task dispatch |
| `set_history_sink()` | `_history_sink` | SS history_active persistence |
| `set_hitl_coordinator()` | `_hil_coordinator` | HITL orchestration |
| `set_session_state()` | `_ss` | SS reads + M4 binding (rebinds TaskBridge, ControlExtension) |
| `set_weave_batcher()` | `_weave_batcher` | Weave queue management |
| `set_ledger()` | `_ledger` | V3 event sourcing |
| `set_back_pool()` | `_back_pool` | M7 capacity-aware arbiter |
| `set_weave_policy()` | `_weave_policy` | M8 adaptive weave |
| `set_activity_tracker()` | `_activity_tracker` | M8 typing/idle signals |
| `set_opp_pipeline()` | `_opp_pipeline` | OPP-1 through OPP-8 primitives |

**Key methods:**

| Method | Signature | Description |
|---|---|---|
| `_subscribe_all()` | `-> None` | Wires 20 topic subscriptions to handler methods |
| `_transition()` | `(to_state, trigger, envelope) -> None` | Validated state change + observability emit |
| `_topic_guard()` | `(envelope, expected_topic) -> bool` | Defence against causal-cascade re-entry |
| `_guard_dispatch()` | `(envelope) -> GuardAction` | Full guard matrix lookup |
| `_publish_dead_letter()` | `(envelope, reason) -> None` | Dead-letter publish with ledger write |
| `_finalize_turn()` | `(envelope) -> None` | emit turn.completed + drain FrontLock |
| `_write_history()` | `(entry_type, role, ...) -> TypedHistoryEntry` | Sole writer to history with ledger emit |
| `_on_user_input()` | `(envelope) -> None` | Turn entry point. Routes by state: LISTENING→DISPATCHING, COMPANIONING→INTERRUPT, CLARIFYING_WORKER→HITL response |
| `_handle_interrupt()` | `(envelope, text, device_id) -> None` | M5 arbiter-based interrupt handler |
| `_handle_arbiter_cancel()` | `(envelope, text, arbiter_result) -> None` | CANCEL decision: set tokens, transition CANCELLING, publish events |
| `_handle_arbiter_modify()` | `(envelope, text, arbiter_result) -> None` | MODIFY_INFLIGHT: inject PARAMETER_UPDATE into Back's messages list |
| `_handle_arbiter_defer()` | `(envelope, text, arbiter_result) -> None` | DEFER: acknowledge and continue |
| `_handle_arbiter_parallel_new()` | `(envelope, text, arbiter_result) -> None` | PARALLEL_NEW: increment turn, Phase 1, dispatch |
| `_run_phase1_with_arbiter()` | `(envelope, text, device_id) -> None` | Phase 1 + Arbiter on normal turn start |
| `register_running_task_messages()` | `(task_id, messages) -> None` | Back registers mutable messages list for modify injection |

**Helper functions (module-level):**

| Function | Signature | Description |
|---|---|---|
| `_parse_payload()` | `(envelope) -> dict` | JSON parse envelope payload bytes |
| `_coerce_tier()` | `(raw_tier) -> ComplexityTier` | String → ComplexityTier with LOW fallback |
| `_task_dispatch_from_payload()` | `(payload) -> TaskDispatch` | Build canonical TaskDispatch from bus payload |
| `_build_canonical_event()` | `(entry_type, text, meta, metadata) -> Event \| None` | Map history entry_type to canonical event class |

**Cross-component imports** (HEAVY):
- `k1.bus.envelope`: `Envelope`, `PayloadFormat`, `Priority`
- `k1.bus.ports.bus`: `IBus`
- `k1.bus.ports.mailbox`: `IMailboxRouter`
- `k1.concierge.bus.builders`: 13 builder functions (build_dead_letter, build_final_response, build_hitl_requested/resolved, build_intent_arbitrated, build_state_updated, build_task_cancel/complete/dispatch/failed, build_turn_completed/started)
- `k1.concierge.bus.setup`: `ACTOR_BACK`, `ACTOR_FRONT`
- `k1.concierge.bus.topics`: 20 topic constants
- `k1.concierge.config`: `get_config`
- `k1.concierge.orchestrator.routing`: `route_task_sync`
- `k1.concierge.protocols.cancel_handler`: `CancellationHandler`
- `k1.concierge.protocols.cancellation`: `CancellationToken`
- `k1.concierge.protocols.hitl_persistence`: `HILSubTask`, `scan_for_recovery`
- `k1.concierge.protocols.hitl_wiring`: `build_resume_context`
- `k1.concierge.protocols.suspension_manager`: `SuspensionManager`
- `k1.concierge.protocols.weave_batcher`: `WEAVE_BATCH_WINDOW_MS`
- `k1.concierge.protocols.weave_policy`: `UserActivityTracker`, `WeaveDecision`, `WeaveDecisionResult`, `WeaveFallbackHandler`, `WeavePolicy`, `WeaveSignal`, `sort_results_for_delivery`
- `k1.sessionstate.sections.control`: `IntentClassification`, `PrivacyBand`
- `k1.concierge.task.complexity`: `ComplexityTier`
- `k1.concierge.task.dispatch`: `TaskDispatch`
- `k1.concierge.task.intent`: `TaskIntent`
- Lazy imports: `k1.concierge.events.conversation`, `k1.concierge.events.hitl`, `k1.concierge.events.task`, `k1.concierge.events.weave`, `k1.concierge.events.base`, `k1.concierge.bus.deserialize`, `k1.concierge.llm.types`

---

### 2.5 `arbiter.py` (~750 lines)

**Purpose**: Context-aware Conversation Arbiter (M5 E5.1). Replaces keyword-based InterruptClassifier with deterministic intent classification against inflight work. No LLM call.

**Enums:**

#### `ArbiterDecision(str, Enum)`
| Value | Description |
|---|---|
| `CANCEL` | Cancel targeted or all inflight tasks |
| `MODIFY_INFLIGHT` | Modify parameters of a running task |
| `PARALLEL_NEW` | Dispatch as new parallel task |
| `DEFER` | Defer — user is just acknowledging |

**Dataclasses:**

#### `ArbiterResult`
| Field | Type |
|---|---|
| `decision` | `ArbiterDecision` |
| `confidence` | `float` |
| `target_task_id` | `str \| None` |
| `modification_params` | `dict \| None` |
| `routing_metadata` | `dict` |
| `phase1` | `Phase1Result` |

Methods: `to_dict()`, `from_dict(cls, data)`

#### `InflightTask`
| Field | Type |
|---|---|
| `task_id` | `str` |
| `action` | `str` |
| `domain` | `str` |
| `status` | `str` |
| `progress_pct` | `float` |
| `dispatch_turn` | `int` |
| `pending_hil` | `bool` |
| `entities` | `list[str]` |

#### `InflightContext`
| Field | Type |
|---|---|
| `tasks` | `list[InflightTask]` |
| `pending_results` | `int` |
| `cancelled_task_ids` | `set[str]` |
| `fsm_state` | `str` |
| `current_turn` | `int` |
| `active_device_id` | `str \| None` |
| `pool_active_workers` | `int` |
| `pool_size` | `int` |
| `pool_available` | `int` |
| `lease_deadlines` | `dict[str, int]` |

**Classes:**

#### `ConversationArbiter`
- **Constructor**: `(config: ArbiterConfig | None = None)`
- **Key method**: `classify(text, phase1, inflight) -> ArbiterResult`

**Decision table (priority order):**

| # | Condition | Decision | Confidence |
|---|---|---|---|
| 1 | RED safety band | CANCEL (all) | 1.0 |
| 2 | Cancel intent + inflight | CANCEL (targeted or all) | 0.85-0.9 |
| 3 | Cancel intent + no inflight | PARALLEL_NEW | 0.7 |
| 4 | Domain+entity overlap ≥ thresholds + inflight | MODIFY_INFLIGHT | min(d_overlap, e_overlap) |
| 5 | Defer pattern + inflight | DEFER | 0.8 |
| 6 | Inflight present | PARALLEL_NEW | 0.75 |
| 7 | No inflight | PARALLEL_NEW | 0.9 |

**Internal helpers:**
- `_detect_cancel_intent(lower, phase1) -> bool`
- `_detect_cancel_all(lower) -> bool`
- `_detect_defer_intent(lower) -> bool`
- `_select_cancel_target(lower, phase1, inflight) -> str | None`
- `_select_modify_target(phase1, inflight) -> str | None`
- `_extract_modification_params(text, phase1) -> dict`

**Module-level functions:**
- `build_inflight_context(ss, suspension_manager, cancel_handler, turn_state, current_turn, device_id, back_pool) -> InflightContext` — Builds snapshot from M4-bound SS sections, SuspensionManager, CancellationHandler, BackPool.
- `domain_overlap(phase1, inflight) -> float` — Fuzzy domain matching with recency decay (OPP-2).
- `entity_overlap(phase1, inflight) -> float` — Jaccard coefficient on entity text with recency decay.
- `_apply_recency_decay(raw_score, dispatch_turn, current_turn, decay_per_turn) -> float` — OPP-2 generalized decay.
- `is_short_input(text, threshold) -> bool` — Short-input penalty guard.

**Keyword sets**: `_DEFAULT_DEFER_KEYWORDS` (14), `_DEFAULT_CANCEL_KEYWORDS` (9), `_CANCEL_ALL_KEYWORDS` (6), `_RELATED_DOMAINS` (8 domain families).

**Cross-component imports**: `k1.concierge.config` (`ArbiterConfig`, `get_config`), `k1.concierge.fsm.phase1` (`Phase1Result`).

---

### 2.6 `control_extension.py` (~230 lines)

**Purpose**: POC wrapper over SS `ControlSection` adding 3 FSM-specific fields: `fsm_state`, `active_task_ids`, `complexity_tier`. Does NOT modify the shared ControlSection schema.

**Class: `ConciergeControlExtension`**

| Method | Signature | Description |
|---|---|---|
| `__init__()` | `-> None` | Initial state: LISTENING, empty tasks, LOW tier |
| `bind_control_section()` | `(section) -> None` | M4 E4.1.2: bind to real SS ControlSection |
| `is_bound` | `@property -> bool` | Whether bound to SS |
| `set_fsm_state()` | `(state: ConciergeState) -> None` | Update + sync to SS |
| `add_active_task()` | `(task_id: str) -> None` | Register dispatched task |
| `remove_active_task()` | `(task_id: str) -> None` | Remove completed/failed task |
| `has_active_task()` | `(task_id: str) -> bool` | Check if task active |
| `set_complexity_tier()` | `(tier: str) -> None` | Update with validation |
| `snapshot()` | `-> dict` | Observability snapshot |
| `reset()` | `-> None` | Reset all state |

**Invariant**: Single-writer (FSM). No concurrent writes. Every mutation calls `_sync_to_section()` to push overlay to bound SS ControlSection.

**Cross-component imports**: `k1.concierge.fsm.states` (`ConciergeState`).

---

### 2.7 `front_lock.py` (~210 lines)

**Purpose**: Concurrency gate for the Front LLM actor. Serializes events targeting Front. Maintains a bounded priority queue with backpressure.

**Constants:**

| Constant | Value |
|---|---|
| `PRIORITY_URGENT` | 1 |
| `PRIORITY_INTERACTIVE` | 2 |
| `PRIORITY_RESULT` | 3 |
| `PRIORITY_ERROR` | 4 |
| `PRIORITY_INFO` | 5 |
| `DEFAULT_MAX_QUEUE_DEPTH` | 8 |

**`TOPIC_PRIORITY` mapping:**

| Topic | Priority |
|---|---|
| `user.input` | URGENT (1) |
| `task.suspended` | INTERACTIVE (2) |
| `task.complete` | RESULT (3) |
| `task.failed` | ERROR (4) |
| `findings.ready` | INFO (5) |
| `weave.batch` | RESULT (3) |

**Class: `FrontLock` (dataclass)**

| Field | Type | Default |
|---|---|---|
| `busy` | `bool` | `False` |
| `event_queue` | `deque[tuple[int, Envelope]]` | empty |
| `max_queue_depth` | `int` | from config |

| Method | Signature | Description |
|---|---|---|
| `try_deliver()` | `(envelope) -> bool` | True if delivered (Front free), False if queued |
| `release()` | `-> Envelope \| None` | Release lock, return next queued event or None |
| `drain_loop()` | `async (deliver_fn) -> None` | Drain entire queue in priority order |
| `queue_depth` | `@property -> int` | Current queue depth |
| `is_idle` | `@property -> bool` | Not busy and empty queue |
| `peek_priorities()` | `-> list[int]` | Priority values of queued events |
| `clear()` | `-> None` | Reset for testing |

**Backpressure**: When queue exceeds `max_queue_depth`, the lowest-priority event is ejected and logged.

**Cross-component imports**: `k1.bus.envelope` (`Envelope`), `k1.concierge.bus.topics` (6 topic constants), `k1.concierge.config` (`get_config`).

---

### 2.8 `turn_state.py` (~320 lines)

**Purpose**: Ephemeral turn tracking (NOT persisted in SessionState). Manages pending results queue and deferred results for weave delivery.

**Class: `FSMTurnState` (dataclass)**

| Field | Type | Default |
|---|---|---|
| `pending_results` | `deque[dict]` | empty |
| `_ledger` | `LedgerWriter \| None` | None |
| `deferred_results` | `list[dict]` | empty |
| `max_depth` | `int` | 16 |
| `ttl_seconds` | `int` | 300 (5 min) |

| Method | Signature | Description |
|---|---|---|
| `set_ledger()` | `(writer) -> None` | Attach ledger post-construction |
| `enqueue_result()` | `(task_id, result, envelope, urgency) -> dict \| None` | Queue result; returns evicted dict on overflow |
| `drain_results()` | `-> (valid, expired)` | Drain with TTL filtering |
| `has_pending_results` | `@property -> bool` | Queue non-empty |
| `depth` | `@property -> int` | Current queue depth |
| `mark_deferred()` | `(results, max_consecutive_defers) -> list[dict]` | M8 E8.3.2: move to deferred, force-deliver after 5 defers |
| `drain_deferred()` | `-> list[dict]` | Drain deferred for STANDARD injection |
| `has_deferred_results` | `@property -> bool` | |
| `reset()` | `-> None` | Clear all state |
| `rebuild_from_projection()` | `(projected) -> int` | M9 ledger rebuild |

**Overflow handling**: When `pending_results` reaches `max_depth` (16), oldest is evicted → dead-letter. TTL expiry (300s) filters out stale results on drain.

**Ledger integration**: `WeaveCandidateArrived` on enqueue, `WeaveEmitted` on drain (write-before-mutate pattern).

**Cross-component imports**: `k1.bus.envelope` (`Envelope`), `k1.concierge.ledger.writer` (`LedgerWriter` — TYPE_CHECKING only), lazy: `k1.concierge.events.weave`.

---

### 2.9 `phase1.py` (~340 lines)

**Purpose**: Phase 1 (UltraBERT) integration, `Phase1Result` data class, `Phase1Pipeline` protocol, `StubPhase1Pipeline`, and `TurnLock` sequencing.

**Class: `Phase1Result`**
- 13 slots: `intents`, `entities`, `salience_map`, `primary_emotion`, `emotion_confidence`, `valence`, `arousal`, `intent_classification`, `domain_context`, `safety_band`, `complexity_tier`, `temporal_expressions`, `relations`, `_degraded`
- Method: `to_metadata() -> dict` — Serializes for TypedHistoryEntry attachment

**Protocol: `Phase1Pipeline`**
- `classify(text: str) -> Phase1Result`

**Class: `StubPhase1Pipeline`**
- Keyword-based stub for POC. Recognizes: travel, health, weather, cancel, greeting domains.
- Properties: `call_count`, `last_text`, `last_result`

**Class: `TurnLock`**
- Simple boolean flag (not asyncio.Lock). Ensures Phase 1 completes before Front reads SS.
- Methods: `acquire(holder) -> bool`, `release() -> bool`
- Properties: `is_held`, `holder`, `acquire_count`

**Cross-component imports**: None (stdlib only).

---

### 2.10 `ultrabert_adapter.py` (~300 lines)

**Purpose**: K1-native UltraBERT adapter. Direct integration with `familyos_ultrabert` pip package. Zero dependency on k0/runtime/.

**Constants:**
- `SENTIMENT_TO_VALENCE: dict[str, float]` — Maps sentiment labels to valence values
- `HIGH_AROUSAL_EMOTIONS: frozenset[str]` — anger, excitement, fear, surprise
- `LOW_AROUSAL_EMOTIONS: frozenset[str]` — sadness, calm, boredom, contentment
- `ENTITY_MIN_CONFIDENCE: float = 0.65`

**Class: `_LRUTTLCache`**
- Thread-safe LRU cache with per-entry TTL.
- Constructor: `(max_size=64, ttl_s=30.0)`
- Methods: `get(key)`, `put(key, value)`, `clear()`
- Uses `threading.Lock` and `OrderedDict`.

**Protocol: `UltraBERTAdapter` (@runtime_checkable)**
- `analyze(text: str) -> dict[str, Any] | None`
- `is_available() -> bool`
- `get_metrics() -> dict[str, Any]`

**Class: `K1UltraBERTAdapter`**
- Thread-safe singleton (`_instance`, `_lock`, `get_instance()`, `reset_instance()`)
- Wraps `familyos_ultrabert.Client(backend="auto")`
- LRU cache keyed on `sha256(text)` (privacy: no raw text stored)
- Methods: `analyze(text)`, `is_available()`, `warmup()`, `get_metrics()`
- Metrics: `call_count`, `avg_latency_ms`, `cache_hits`, `cache_misses`, `fallback_count`

**Class: `StubUltraBERTAdapter`**
- Returns `None` for all `analyze()` calls. For tests without GPU.

**Cross-component imports**: None (stdlib + optional `familyos_ultrabert` lazy import).

---

### 2.11 `ultrabert_phase1.py` (~340 lines)

**Purpose**: Real UltraBERT-backed Phase 1 pipeline (M10 E10.1). Maps 12-head output to Phase1Result, computes multi-factor complexity tier, applies confidence thresholding, handles graceful degradation.

**Class: `UltraBERTPhase1Pipeline`**
- Constructor: `(adapter: UltraBERTAdapter, fallback: StubPhase1Pipeline | None, config: Phase1Config | None)`
- Properties: `call_count`, `degraded_count`, `last_embedding`
- Method: `classify(text: str) -> Phase1Result` — Calls adapter.analyze(), maps result, falls back to StubPhase1Pipeline on failure (tags `_degraded = True`)

**Internal mapping methods:**
- `_map_to_phase1_result(analysis) -> Phase1Result` — Maps all 12 heads
- `_filter_intents(analysis) -> list[str]` — Multi-label intent thresholding (E10.1.3)
- `_infer_arousal(primary_emotion, emotion_scores) -> float` — High/low arousal heuristic
- `_merge_entities(family_entities, general_entities) -> list[dict]` — De-duplicate by span, family takes priority
- `_compute_complexity(all_intents, active_domains, primary_intent, entities, safety_band) -> str` — Multi-factor scoring:
  - Factor 1: Multi-intent (>1 intent) → +1
  - Factor 2: Cross-domain (>1 domain) → +1
  - Factor 3: Temporal ambiguity → +1
  - Safety override: RED/CRISIS → force LOW
  - Thresholds from config: `low_max` (default 0), `medium_max` (default 2)

**Cross-component imports**: `k1.concierge.config.loader` (`Phase1Config`, `get_config`), `k1.concierge.fsm.phase1` (`Phase1Result`, `StubPhase1Pipeline`), `k1.concierge.fsm.ultrabert_adapter` (constants + protocol).

---

### 2.12 `history_writer.py` (~240 lines)

**Purpose**: Stateless writer for TypedHistoryEntry + converters for Front/Back LLM context windows.

**Constants:**
- `FRONT_HISTORY_WINDOW = 20`
- `BACK_HISTORY_WINDOW = 5`
- `USER_ENTRY_TYPES = frozenset({"user", "hitl_response"})`
- `ASSISTANT_ENTRY_TYPES = frozenset({"final", "weave", "clarification", "hitl_request", "error", "proactive"})`
- `BACK_RELEVANT_TYPES = frozenset({"user", "final", "hitl_response"})`

**Class: `HistoryWriter`**
- Constructor: `(history: list[TypedHistoryEntry])`
- Methods:
  - `write(turn_number, entry_type, role, text, source, task_id, timestamp_ms, metadata) -> TypedHistoryEntry`
  - `get_entries_by_turn(turn_number) -> list`
  - `get_entries_by_type(entry_type) -> list`
  - `last_n(n) -> list`
- Properties: `entries`, `count`

**Module-level functions:**

| Function | Signature | Description |
|---|---|---|
| `history_to_front_messages()` | `(entries, window=20) -> list[dict]` | Last 20 entries → `{role, content}` with type prefixes |
| `history_to_back_context()` | `(entries, window=5) -> list[dict]` | Filtered to user/final/hitl_response, content truncated to 500 chars |

**Entry prefix mapping for Front messages:**
- `hitl_request` → `[clarification question]`
- `hitl_response` → `[clarification answer]`
- `weave` → `[async result]`
- `error` → `[error]`
- `proactive` → `[proactive]`
- `clarification` → `[clarification]`

**Cross-component imports**: `k1.concierge.config` (`get_config`), `k1.concierge.fsm.controller` (`TypedHistoryEntry`).

---

### 2.13 `response_final_table.py` (~300 lines)

**Purpose**: Pure-function decision table for response.final handling. 13 state/condition branches, zero side effects. Externalizes the previously 217-line `_on_response_final` branching logic.

**Enums:**

#### `ResponseFinalAction(str, Enum)`
| Value | Description |
|---|---|
| `TRANSITION_LISTENING` | Turn done, go idle |
| `TRANSITION_WEAVING` | Pending results need weave flush |
| `TRANSITION_COMPANIONING` | Active tasks, wait |
| `STAY` | Stay in current state |
| `IGNORE` | Spurious final, ignore |
| `DEAD_LETTER` | Invalid in this state |

**Dataclass: `ResponseFinalDecision` (frozen, slots)**

| Field | Type |
|---|---|
| `action` | `ResponseFinalAction` |
| `target_state` | `ConciergeState \| None` |
| `emit_turn_completed` | `bool` |
| `drain_front_lock` | `bool` |
| `schedule_weave` | `bool` |
| `release_front_lock` | `bool` |
| `entry_type` | `str` |

**Function: `decide_response_final(fsm_state, has_pending_results, has_active_tasks, is_fallback, weave_flush_running) -> ResponseFinalDecision`**

**13-branch truth table:**

| # | State | Condition | Action | Target |
|---|---|---|---|---|
| 1 | DISPATCHING | pending_results | TRANSITION_WEAVING | WEAVING |
| 2 | DISPATCHING | active_tasks | TRANSITION_COMPANIONING | COMPANIONING |
| 3 | DISPATCHING | neither | TRANSITION_LISTENING | LISTENING |
| 4 | DELIVERING | pending_results | TRANSITION_WEAVING | WEAVING |
| 5 | WEAVING | pending + no flush | TRANSITION_WEAVING (re-weave) | WEAVING |
| 6 | WEAVING | pending + flush running | STAY | — |
| 7 | DELIVERING | no pending | TRANSITION_LISTENING | LISTENING |
| 8 | WEAVING | no pending | TRANSITION_LISTENING | LISTENING |
| 9 | COMPANIONING | active_tasks | STAY | — |
| 10 | COMPANIONING | no active | TRANSITION_LISTENING | LISTENING |
| 11 | CLARIFYING_WORKER | active_tasks | TRANSITION_COMPANIONING | COMPANIONING |
| 12 | CLARIFYING_WORKER | no active | TRANSITION_LISTENING | LISTENING |
| 13 | LISTENING | spurious | IGNORE | — |
| — | any other | — | DEAD_LETTER | — |

**Helper: `_resolve_entry_type(fsm_state, is_fallback) -> str`** — Returns `"weave"`, `"proactive_fallback"`, `"proactive"`, or `"final"`.

**Cross-component imports**: `k1.concierge.fsm.states` (`ConciergeState`).

---

### 2.14 `task_bridge.py` (~650 lines)

**Purpose**: FSM bridge to `TaskStateSection` and `TaskArtifactsSection` in SessionState. FSM is the single writer for both sections.

**Constants:**
- `PRUNE_COMPLETED_AFTER_TURNS = 10`
- `EVICT_ARTIFACTS_AFTER_TURNS = 10`

**Class: `TaskBridge`**
- Constructor: `(task_state, task_artifacts, ledger)`
- Counters: `total_dispatched`, `total_completed`, `total_failed`, `total_cancelled`

**Task lifecycle methods** (all write ledger BEFORE in-memory mutation — M9 E9.4.1):

| Method | Signature | Status transition |
|---|---|---|
| `dispatch_task()` | `(task_id, action) -> TaskStateEntry` | → DISPATCHED |
| `activate_task()` | `(task_id) -> TaskStateEntry \| None` | → ACTIVE |
| `suspend_task()` | `(task_id) -> TaskStateEntry \| None` | → SUSPENDED (auto-activates if DISPATCHED) |
| `resume_task()` | `(task_id) -> TaskStateEntry \| None` | → ACTIVE |
| `complete_task()` | `(task_id, result_data) -> TaskStateEntry \| None` | → COMPLETED (auto-activates if DISPATCHED) |
| `fail_task()` | `(task_id, reason) -> TaskStateEntry \| None` | → FAILED |
| `cancel_task()` | `(task_id, reason) -> TaskStateEntry \| None` | → CANCELLED |
| `mark_presented()` | `(task_id, turn_number) -> None` | Sets `presented_at_turn` |
| `set_progress()` | `(task_id, progress_pct) -> None` | 0-100 progress |
| `set_pending_hil_data()` | `(task_id, data) -> None` | M6 HITL crash recovery |

**Rebind (M4 E4.1.1):**
- `rebind(task_state, task_artifacts)` — Replaces local fallback sections with real SS sections. Copies pre-rebind tasks. Rejects if any task is ACTIVE (mid-flight guard).

**Artifact operations:**
- `add_artifact(task_id, content, artifact_type, metadata) -> TaskArtifactEntry`
- `get_artifacts_for_task(task_id) -> list`

**Read operations:**
- `get_active_tasks()`, `get_task(task_id)`, `get_suspended_tasks()`, `task_count_by_status()`

**Pruning:**
- `prune(current_turn) -> int` — Prune completed tasks > 10 turns old, evict old artifacts

**Ledger rebuild (M9 E9.4.1):**
- `rebuild_from_projection(projected) -> int` — Maps hitl_persistence statuses to SS statuses

**Cross-component imports**:
- `k1.sessionstate.sections.task_artifacts`: `ArtifactType`, `TaskArtifactEntry`, `TaskArtifactsSection`
- `k1.sessionstate.sections.task_state`: `TaskStateEntry`, `TaskStateSection`, `TaskStatus`
- `k1.concierge.ledger.writer`: `LedgerWriter` (TYPE_CHECKING)
- Lazy: `k1.concierge.events.task`, `k1.concierge.events.hitl`

---

### 2.15 `dead_letter.py` (~100 lines)

**Purpose**: Dead-letter payload schema and factory.

**Dataclass: `DeadLetterPayload`**

| Field | Type |
|---|---|
| `original_topic` | `str` |
| `original_envelope_id` | `int` |
| `reason` | `str` |
| `fsm_state_at_rejection` | `str` |
| `turn_number` | `int` |
| `task_id` | `str` |
| `original_payload_summary` | `str` |
| `rejected_at_ns` | `int` (monotonic_ns) |

Methods: `to_dict()`, `from_dict(cls, data)`

**Factory: `build_dead_letter_payload(original_topic, original_envelope_id, reason, fsm_state, turn_number, task_id, payload_summary) -> DeadLetterPayload`**
- Truncates `payload_summary` to 500 chars.

**Dead-letter reasons**: `invalid_transition`, `re_entrant_drop`, `cancel_incompatible`, `overflow`, `expired`, `weave_overflow`.

**Cross-component imports**: None (stdlib only).

---

### 2.16 `dead_letter_consumer.py` (~150 lines)

**Purpose**: Reconciliation consumer for dead-letter events. Subscribes to `TOPIC_DEAD_LETTER`, records events for observability dashboards.

**Class: `DeadLetterConsumer`**
- Constructor: `(bus: IBus, max_events=1000)`
- Subscribes to `TOPIC_DEAD_LETTER` on construction
- Handler: `_on_dead_letter(envelope)` — Parses payload, records, counts by reason/state/topic
- Memory safety: Events capped at `max_events`

**Query API:**
- `total_dead_letters` → `int`
- `events` → `list[DeadLetterPayload]`
- `get_events_by_reason(reason)`, `get_events_by_state(state)`, `get_events_by_topic(topic)`
- `snapshot() -> dict` — Summary for dashboards

**Cross-component imports**: `k1.bus.envelope` (`Envelope`), `k1.bus.ports.bus` (`IBus`), `k1.concierge.bus.topics` (`TOPIC_DEAD_LETTER`).

---

### 2.17 `errors.py` (~35 lines)

**Purpose**: FSM-specific exceptions.

**Classes:**

| Class | Fields | Description |
|---|---|---|
| `IllegalTransitionError(Exception)` | `from_state`, `trigger` | Raised when FSM attempts illegal transition. Does NOT crash — event discarded or queued. |
| `FrontLockOverflowError(Exception)` | `rejected_topic`, `queue_depth` | Backpressure signal when FrontLock exceeds max_queue_depth. Does NOT propagate. |

**Cross-component imports**: None.

---

### 2.18 `interrupt_handler.py` (~200 lines)

**Purpose**: Interrupt, cancel, and proactive wake logic. Extracted from controller into testable standalone classes.

**Class: `InterruptClassifier`**
- Legacy keyword-based cancel detection (replaced by Arbiter for M5+, but retained for backward compat).
- `CANCEL_KEYWORDS` (9 keywords, class constant + config override)
- `classify(text) -> str` — Returns `"cancel"` or `"chat"`
- Properties: `classify_count`, `last_classification`

**Class: `ProactiveWakeHandler`**
- `should_wake(fsm_state_name) -> bool` — True if LISTENING
- `record_wake(task_id) -> None` — Record proactive wake event
- Properties: `wake_count`, `last_task_id`

**Interrupt flow documented:**
```
COMPANIONING (Front idle, Back working)
    │
user.input arrives (interrupt)
    │
INTERRUPT_HANDLING
  /           \
just chat    cancel!
  |            |
respond    CANCELLING → task.failed(cancelled) → DELIVERING
  |                                                  |
  +--------------------------------------------------+
                      │
               DELIVERING (if results pending) or LISTENING
```

**Cross-component imports**: `k1.concierge.config` (`get_config`).

---

### 2.19 `idempotency.py` (~60 lines)

**Purpose**: LRU-based idempotency ledger for FSM envelope dedup.

**Class: `IdempotencyLedger`**
- Slots: `_processed` (OrderedDict[int, int]), `_max_entries`
- Constructor: `(max_entries=500)`
- `check_and_mark(envelope_id, turn_number) -> bool` — True if NEW, False if duplicate. LRU eviction of oldest on overflow.
- `contains(envelope_id) -> bool`
- Properties: `size`, `max_entries`
- `reset() -> None`

**Cross-component imports**: None (stdlib only).

---

## 3. State Enum & Transition Table

### 3.1 States (11 total)

```
LISTENING → DISPATCHING → COMPANIONING → PROGRESSING
                ↑              ↕               |
                |         DELIVERING ←---------+
                |              ↕
                +----- WEAVING
                |
                +--- CLARIFYING_USER
                |
                +--- CLARIFYING_WORKER
                |
                +--- CANCELLING
                |
                +--- INTERRUPT_HANDLING
                |
                +--- PROACTIVE_WAKE
```

### 3.2 All Legal Transitions

| From | Trigger | To |
|---|---|---|
| LISTENING | user.input | DISPATCHING |
| LISTENING | task.complete | PROACTIVE_WAKE |
| LISTENING | deferred_hitl.surface | CLARIFYING_WORKER |
| DISPATCHING | task.dispatch | COMPANIONING |
| DISPATCHING | response.final | LISTENING |
| DISPATCHING | task.cancel | CANCELLING |
| DISPATCHING | clarification.detected | CLARIFYING_USER |
| DISPATCHING | pending_results.non_empty | WEAVING |
| COMPANIONING | task.complete | DELIVERING |
| COMPANIONING | task.failed | DELIVERING |
| COMPANIONING | task.suspended | CLARIFYING_WORKER |
| COMPANIONING | user.input | INTERRUPT_HANDLING |
| COMPANIONING | tool.started | PROGRESSING |
| COMPANIONING | task.cancel | CANCELLING |
| COMPANIONING | task.dispatch | COMPANIONING |
| COMPANIONING | response.final | LISTENING |
| COMPANIONING | same_turn.task.complete | LISTENING |
| PROGRESSING | tool.completed | COMPANIONING |
| PROGRESSING | task.complete | DELIVERING |
| PROGRESSING | task.failed | DELIVERING |
| PROGRESSING | task.suspended | CLARIFYING_WORKER |
| PROGRESSING | user.input | INTERRUPT_HANDLING |
| PROGRESSING | task.cancel | CANCELLING |
| DELIVERING | response.final | LISTENING |
| DELIVERING | pending_results.non_empty | WEAVING |
| CLARIFYING_USER | user.input | DISPATCHING |
| CLARIFYING_WORKER | user.input | CLARIFYING_WORKER |
| CLARIFYING_WORKER | task.resume | COMPANIONING |
| CLARIFYING_WORKER | response.final | (dynamic) |
| CANCELLING | task.failed | DELIVERING |
| INTERRUPT_HANDLING | interrupt.routed | DISPATCHING |
| PROACTIVE_WAKE | proactive.routed | DELIVERING |
| WEAVING | response.final | LISTENING |
| WEAVING | pending_results.non_empty | WEAVING |

---

## 4. Full Guard Matrix

The `FULL_GUARD_TABLE` covers **11 states × 30 topics = 330 cells**. Each cell is one of:

- **T (TRANSITION)** — Validated state change
- **P (PASSTHROUGH)** — Forward to handler without state change
- **O (OBSERVE)** — Log/history only
- **Q (QUEUE)** — Queue in FrontLock or pending_results
- **D (DEAD_LETTER)** — Reject event

Guard actions by category (summary):

| Action | Used in states/topics | Purpose |
|---|---|---|
| T | ~33 cells | State machine transitions |
| P | ~77 cells | findings.ready, clarification, dag.completed, weave.batch passthrough |
| O | ~165 cells | Observability: artifact.created, affect.update, HITL lifecycle, BackPool, UI typing, weave metrics |
| Q | ~22 cells | pending_results queue (task.complete in DELIVERING/WEAVING/etc.), FrontLock queue (user.input in DELIVERING) |
| D | ~33 cells | Rejected: tool events in wrong state, re-entrant user.input, etc. |

---

## 5. Cross-Component Import Map

| Import source | Used by files | Usage |
|---|---|---|
| **k1.bus.envelope** | controller, front_lock, turn_state, dead_letter_consumer | `Envelope`, `PayloadFormat`, `Priority` |
| **k1.bus.ports.bus** | controller, dead_letter_consumer | `IBus` protocol |
| **k1.bus.ports.mailbox** | controller | `IMailboxRouter` protocol |
| **k1.concierge.bus.builders** | controller | 13+ builder functions |
| **k1.concierge.bus.setup** | controller | `ACTOR_BACK`, `ACTOR_FRONT` |
| **k1.concierge.bus.topics** | controller, front_lock, transition_table, dead_letter_consumer | 30 topic constants |
| **k1.concierge.config** | controller, arbiter, front_lock, history_writer, interrupt_handler, ultrabert_phase1 | `get_config`, `ArbiterConfig`, `Phase1Config` |
| **k1.concierge.orchestrator.routing** | controller | `route_task_sync` |
| **k1.concierge.protocols.cancel_handler** | controller | `CancellationHandler` |
| **k1.concierge.protocols.cancellation** | controller | `CancellationToken` |
| **k1.concierge.protocols.hitl_persistence** | controller | `HILSubTask`, `scan_for_recovery` |
| **k1.concierge.protocols.hitl_wiring** | controller | `build_resume_context` |
| **k1.concierge.protocols.suspension_manager** | controller | `SuspensionManager` |
| **k1.concierge.protocols.weave_batcher** | controller | `WEAVE_BATCH_WINDOW_MS` |
| **k1.concierge.protocols.weave_policy** | controller | `WeavePolicy`, `WeaveSignal`, `WeaveDecision`, `UserActivityTracker`, etc. |
| **k1.sessionstate.sections.control** | controller | `IntentClassification`, `PrivacyBand` |
| **k1.sessionstate.sections.task_state** | task_bridge | `TaskStateEntry`, `TaskStateSection`, `TaskStatus` |
| **k1.sessionstate.sections.task_artifacts** | task_bridge | `ArtifactType`, `TaskArtifactEntry`, `TaskArtifactsSection` |
| **k1.concierge.task.complexity** | controller | `ComplexityTier` |
| **k1.concierge.task.dispatch** | controller | `TaskDispatch` |
| **k1.concierge.task.intent** | controller | `TaskIntent` |
| **k1.concierge.ledger.writer** | task_bridge, turn_state | `LedgerWriter` (TYPE_CHECKING) |
| **k1.concierge.events.*** | controller, task_bridge, turn_state (lazy) | Canonical event classes |
| **k1.concierge.llm.types** | controller (lazy) | `ModelMessage` |
| **k1.concierge.bus.deserialize** | controller (lazy) | `deserialize_envelope` |
| **familyos_ultrabert** | ultrabert_adapter (lazy) | `Client` (GPU model) |

---

## 6. Port / Adapter / Protocol Usage

| Protocol / Port | Defined in | Consumed by | Description |
|---|---|---|---|
| `IBus` | `k1.bus.ports.bus` | `ConciergeController`, `DeadLetterConsumer` | Pub/sub event bus |
| `IMailboxRouter` | `k1.bus.ports.mailbox` | `ConciergeController` | Point-to-point actor delivery |
| `Phase1Pipeline` (Protocol) | `phase1.py` | `ConciergeController` | Classification interface |
| `UltraBERTAdapter` (Protocol, @runtime_checkable) | `ultrabert_adapter.py` | `UltraBERTPhase1Pipeline` | UltraBERT analysis abstraction |
| `CancellationHandler` | `protocols.cancel_handler` | `ConciergeController` | Cancel token management |
| `CancellationToken` | `protocols.cancellation` | `ConciergeController` | Per-task cancel token |
| `SuspensionManager` | `protocols.suspension_manager` | `ConciergeController`, `build_inflight_context` | HITL suspension tracking |
| `WeavePolicy` | `protocols.weave_policy` | `ConciergeController` | Adaptive weave decisions |
| `UserActivityTracker` | `protocols.weave_policy` | `ConciergeController` | Typing/idle signals |
| `LedgerWriter` | `concierge.ledger.writer` | `TaskBridge`, `FSMTurnState`, `ConciergeController` | Event sourcing |

**Adapter pattern**: `K1UltraBERTAdapter` wraps `familyos_ultrabert.Client` behind the `UltraBERTAdapter` protocol. `StubUltraBERTAdapter` provides test double. `StubPhase1Pipeline` provides test double for `Phase1Pipeline`.

---

## 7. Error Handling Patterns

### 7.1 Exception Types
- `IllegalTransitionError` — Raised on illegal FSM transitions. Caught by handlers, logged, event discarded or dead-lettered. **Never propagates to crash the system.**
- `FrontLockOverflowError` — Backpressure signal. Lowest-priority event ejected. **Never propagates.**

### 7.2 Guard Matrix (Closed-World)
Every (state, topic) pair has an explicit cell in `FULL_GUARD_TABLE`. Unknown topics default to `DEAD_LETTER`. Events in invalid states are dead-lettered, not silently dropped.

### 7.3 Dead-Letter Pipeline
1. FSM guard rejects event → `_publish_dead_letter(envelope, reason)`
2. Dead-letter envelope published to `TOPIC_DEAD_LETTER`
3. `DeadLetterConsumer` subscribes, records, counts by reason/state/topic
4. Configurable via `fsm.dead_letter_enabled` flag
5. Ledger write BEFORE bus publish (M2 E2.5.2)

### 7.4 Idempotency / Dedup
- `IdempotencyLedger` (LRU, 500 entries) prevents duplicate processing of same `envelope_id`
- Topic guard (`_topic_guard`) prevents causal-cascade re-entry

### 7.5 Overflow / TTL
- `FSMTurnState.pending_results`: max_depth=16, evicts oldest on overflow → dead-letter
- `FSMTurnState.drain_results()`: TTL=300s, filters expired → dead-letter
- `FrontLock.event_queue`: max_depth=8, ejects lowest-priority on overflow
- `DeadLetterConsumer._events`: capped at 1000

### 7.6 Graceful Degradation
- `UltraBERTPhase1Pipeline`: Falls back to `StubPhase1Pipeline` if adapter unavailable. Tags result `_degraded = True`.
- `K1UltraBERTAdapter`: Returns `None` on import failure or runtime exception → fallback path.
- `build_inflight_context()`: All SS reads wrapped in try/except, returns partial data on failure.

### 7.7 Ledger Write-Before-Mutate
- `TaskBridge` lifecycle methods: Ledger write BEFORE in-memory mutation (M9 E9.4.1)
- `FSMTurnState.enqueue_result()`: `WeaveCandidateArrived` emitted before queue append
- `ConciergeController._write_history()`: Ledger event emitted BEFORE in-memory append

---

## 8. Key Invariants

| # | Invariant | Enforced by |
|---|---|---|
| 1 | **FSM is sole writer to history_active** | `_write_history()` is only write path; HistoryWriter wraps it |
| 2 | **FSM is sole writer to task_state and task_artifacts** | All writes go through `TaskBridge` |
| 3 | **Phase 1 completes BEFORE Front LLM starts** | `TurnLock.acquire()` → Phase 1 → `TurnLock.release()` → Front |
| 4 | **Front LLM is single-actor** (no concurrent calls) | `FrontLock` serializes all events targeting Front |
| 5 | **Every (state, topic) pair has explicit guard action** | `FULL_GUARD_TABLE` covers all 330 cells |
| 6 | **Transitions are validated against TRANSITION_TABLE** | `_transition()` calls `is_legal()` before state change |
| 7 | **Cancellation wins over late completion** | `CancellationHandler` tracks cancelled set; completed results for cancelled tasks are discarded |
| 8 | **Idempotency: same envelope_id processed at most once** | `IdempotencyLedger.check_and_mark()` (LRU, 500 entries) |
| 9 | **Dead-letters are observable, not silent drops** | `_publish_dead_letter()` + `DeadLetterConsumer` |
| 10 | **Ledger write before in-memory mutation** | All TaskBridge lifecycle + FSMTurnState + _write_history |
| 11 | **ConciergeControlExtension syncs to SS on every mutation** | `_sync_to_section()` called in every setter |
| 12 | **TaskBridge rejects mid-flight rebind** | `rebind()` raises RuntimeError if any task is ACTIVE |
| 13 | **Arbiter is deterministic** — same inputs = same output | Pure function, no LLM call, no randomness |
| 14 | **Overflow results in dead-letter, never silent discard** | FrontLock backpressure, FSMTurnState overflow, TTL expiry → dead-letter |
| 15 | **Safety RED always forces CANCEL ALL** | Arbiter priority 1: safety override |
| 16 | **Deferred results force-deliver after 5 consecutive defers** | `mark_deferred()` tracks `defer_count`, forces after `max_consecutive_defers` |

---

*End of FSM subsystem scan.*
