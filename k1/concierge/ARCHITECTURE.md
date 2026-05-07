# K1 Concierge — ARCHITECTURE.md

> **Component**: `k1.concierge` — L1 Conversational Agent (User-Facing)
> **Scan date**: 2026-04-05
> **Source files**: 181 .py files (~35,000 lines)
> **Test files**: 79 files (2,679 tests, 548 classes)
> **Diagrams**: `concierge_unified.mmd` (1,334 lines), `docs/concierge_poc_architecture.mmd` (1,086 lines)

---

## Table of Contents

1. [Component Overview](#1-component-overview)
2. [Hexagonal Ports](#2-hexagonal-ports)
3. [Adapter Matrix](#3-adapter-matrix)
4. [FSM — State Machine](#4-fsm--state-machine)
5. [Protocols Layer](#5-protocols-layer)
6. [Actor Model](#6-actor-model)
7. [Prompt & LLM Subsystem](#7-prompt--llm-subsystem)
8. [Tools & ReAct Loop](#8-tools--react-loop)
9. [Cross-Component Integration (Fabric, Bus, Orchestrator)](#9-cross-component-integration)
10. [Events, Delta & Observability](#10-events-delta--observability)
11. [Task, Scheduler & Kernel](#11-task-scheduler--kernel)
12. [Ledger, Experience, Identity & Compression](#12-ledger-experience-identity--compression)
13. [Cross-Component Wiring Analysis](#13-cross-component-wiring-analysis)
14. [Invariants](#14-invariants)
15. [Test Coverage](#15-test-coverage)
16. [Gaps & Risks](#16-gaps--risks)

---

## 1. Component Overview

Concierge is K1's **user-facing conversational agent** — the L1 layer that receives user input, classifies intent, orchestrates LLM calls (Front and Back actors), manages multi-turn task execution, handles Human-in-the-Loop (HITL) flows, and delivers results back to the user.

### Architecture Layers

| Layer | Subsystem | Responsibility |
|-------|-----------|----------------|
| **Transport** | `bus/`, `adapters/` | Bus topics, envelope builders, port adapters |
| **FSM** | `fsm/` | 11-state machine, guard matrix, concurrency |
| **Actors** | `actors/` | Front (user-facing) + Back (tool-executing) LLM actors |
| **Protocols** | `protocols/` | Cancellation, Suspension, HITL, Weave, Trust, OPP |
| **Prompt** | `prompt/` | 10-mode dynamic prompt builder, affect modulation |
| **LLM** | `llm/` | Model port, Gemini adapter, ModelHub bridge |
| **Tools** | `tools/` | ReAct tool loop, capability discovery, tool schemas |
| **Task** | `task/` | Intent classification, complexity scoring, dispatch |
| **Events** | `events/` | 30 canonical event types, validation |
| **Delta** | `delta/` | SessionState write pipeline (aggregator→applicator) |
| **Observability** | `obs/` | 37+ Prometheus metrics |
| **Ledger** | `ledger/` | Event sourcing, projections, crash recovery |
| **Experience** | `experience/` | Episodic memory layer |
| **Identity** | `identity/` | Dynamic persona engine |
| **Compression** | `compression/` | Episodic compression for long sessions |
| **Scheduler** | `scheduler/` | Proactive wake triggers |
| **Kernel** | `kernel/` | Bootstrap wiring, lifecycle runner |

### Key Design Decisions

- **Hexagonal architecture**: 8 ports with structural subtyping (`@runtime_checkable Protocol`)
- **Actor model**: Front actor (user-facing, single-threaded via FrontLock) + Back actor pool (3 workers, tool execution)
- **Closed-world FSM**: Every (state, topic) pair has an explicit guard action (330 cells)
- **Write-before-mutate**: All ledger writes happen before in-memory state changes
- **Cooperative cancellation**: Back checks cancel tokens at tool boundaries, never preemptive
- **No new types invented**: `k1.concierge.types/` is a pure re-export hub

---

## 2. Hexagonal Ports

8 ports defined in `ports.py` — 5 new Protocol definitions + 3 aliases of existing K1 protocols.

### Port Summary

| # | Port | Type | Source | Key Methods |
|---|------|------|--------|-------------|
| 1 | `IInputPort` | New Protocol | `ports.py` | `receive() → Envelope`, `has_buffered() → bool` |
| 2 | `IOutputPort` | New Protocol | `ports.py` | `send(Envelope) → None` |
| 3 | `IClassificationPort` | Alias → `Phase1Pipeline` | `fsm.phase1` | `classify(str) → Phase1Result` |
| 4 | `ILLMPort` | Alias → `IModelHubPort` | `k1.model_hub` | `execute(HubRequest) → HubResponse`, `stream_execute() → AsyncIterator[HubChunk]` |
| 5 | `IStatePort` | New Protocol | `ports.py` | `get_section(str) → Any`, `get_snapshot() → dict` |
| 6 | `IDispatchPort` | New Protocol | `ports.py` | `dispatch_direct(CapabilityRequest) → CapabilityResult`, `dispatch_envelope(TaskEnvelope) → AggregatedResult` |
| 7 | `IDeltaPort` | Alias → `IBus` | `k1.bus` | `publish()`, `subscribe()`, `unsubscribe()` |
| 8 | `IMemoryPort` | New Protocol | `ports.py` | `recall(str, list[str]\|None, int) → list[dict]` |

All 5 new protocols use `@runtime_checkable` decorator. No ABC inheritance — pure structural subtyping.

### Cross-Component Port Dependencies

| Port | Depends On |
|------|-----------|
| `ILLMPort` | `k1.model_hub.ports.hub_port.IModelHubPort`, `k1.model_hub.types.{HubRequest, HubResponse, HubChunk}` |
| `IDispatchPort` | `k1.fabric.types.{CapabilityRequest, CapabilityResult}`, `k1.concierge.orchestrator.types.{TaskEnvelope, AggregatedResult}` |
| `IDeltaPort` | `k1.bus.ports.bus.IBus`, `k1.bus.envelope.Envelope` |
| `IClassificationPort` | Internal only (`fsm.phase1.Phase1Pipeline`) |
| `IInputPort` | `k1.bus.envelope.Envelope` |
| `IOutputPort` | `k1.bus.envelope.Envelope` |
| `IStatePort` | None (duck-typed `Any`) |
| `IMemoryPort` | None (returns `list[dict]`) |

---

## 3. Adapter Matrix

### Production Adapters (8)

| Port | Adapter | Module | Wiring |
|------|---------|--------|--------|
| `IInputPort` | `BusInputAdapter` | `adapters/bus_input.py` | Subscribes to `TOPIC_USER_INPUT` on bus, buffers to `asyncio.Queue` |
| `IOutputPort` | `BusOutputAdapter` | `adapters/bus_output.py` | Publishes envelope to bus |
| `IClassificationPort` | `UltraBERTPhase1Pipeline` | Re-export from `fsm/ultrabert_phase1.py` | UltraBERT GPU model → Phase1Result |
| `ILLMPort` | `ModelHubPOCBridge` | Re-export from `llm/model_hub_bridge.py` | Bridge to `k1.model_hub` |
| `IStatePort` | `SSMStateAdapter` | `adapters/ssm_state.py` | Wraps SessionState instance |
| `IDispatchPort` | `FabricDispatchAdapter` | `adapters/fabric_dispatch.py` | LOW→Fabric, MED/HIGH→Orchestrator |
| `IDeltaPort` | `BusFactory.create_local()` | Re-export from `k1.bus.factory` | Local in-process bus |
| `IMemoryPort` | `RecallMemoryAdapter` | `adapters/recall_memory.py` | Wraps recall_fn closure |

### Test Adapters (8)

| Port | Adapter | Module |
|------|---------|--------|
| `IInputPort` | `TestInputAdapter` | `adapters/test_input.py` |
| `IOutputPort` | `TestOutputAdapter` | `adapters/test_output.py` |
| `IClassificationPort` | `StubPhase1Pipeline` | Re-export from `fsm/phase1.py` |
| `ILLMPort` | `TestModelHubBridge` | Re-export from `llm/test_model_hub_bridge.py` |
| `IStatePort` | `InMemoryStateAdapter` | `adapters/test_state.py` |
| `IDispatchPort` | `MockDispatchAdapter` | `adapters/test_dispatch.py` |
| `IDeltaPort` | `create_test_bus()` | `adapters/test_delta.py` |
| `IMemoryPort` | `MockMemoryAdapter` | `adapters/test_memory.py` |

### Null/Startup Adapters (5) — SIM-D-33/38/39

For shared components that start before per-session state is available:

| Satisfies | Adapter | Behavior |
|-----------|---------|----------|
| `IBridgeWritePort` (Orchestrator) | `NullBridgeWriteAdapter` | Silent drop |
| `IDeltaBusPort` (Fabric) | `NullDeltaBusAdapter` | Silent drop |
| `IEventSubscriptionPort` (Orchestrator) | `NullEventSubscriptionAdapter` | Returns null handle |
| `ISessionStateReader` (Fabric) | `NullSessionStateReaderAdapter` | Returns None/empty |
| `IStateReadPort` (Planner) | `SnapshotStateReadAdapter` | Filtered SessionSnapshot from bound data |

---

## 4. FSM — State Machine

**Location**: `k1/concierge/fsm/` (19 files, ~8,100 lines)

### 4.1 States (11 values)

```
ConciergeState(Enum):
  LISTENING            # Idle, waiting for user input
  DISPATCHING          # Phase 1 complete, Front routing
  COMPANIONING         # Front idle, Back working
  PROGRESSING          # Back using tools
  DELIVERING           # Task complete, Front presenting
  CLARIFYING_USER      # Ambiguity detected, asking user
  CLARIFYING_WORKER    # HITL — task suspended, user input needed
  CANCELLING           # Cancel in progress
  INTERRUPT_HANDLING   # Interrupt during Back execution
  PROACTIVE_WAKE       # Task completed while idle
  WEAVING              # Flushing pending async results
```

### 4.2 Transition Table (33 legal transitions)

```
LISTENING:
  user.input              → DISPATCHING
  task.complete           → PROACTIVE_WAKE
  deferred_hitl.surface   → CLARIFYING_WORKER

DISPATCHING:
  task.dispatch           → COMPANIONING
  response.final          → LISTENING
  task.cancel             → CANCELLING
  clarification.detected  → CLARIFYING_USER
  pending_results.non_empty → WEAVING

COMPANIONING:
  task.complete           → DELIVERING
  task.failed             → DELIVERING
  task.suspended          → CLARIFYING_WORKER
  user.input              → INTERRUPT_HANDLING
  tool.started            → PROGRESSING
  task.cancel             → CANCELLING
  task.dispatch           → COMPANIONING (multi-dispatch)
  response.final          → LISTENING
  same_turn.task.complete → LISTENING

PROGRESSING:
  tool.completed          → COMPANIONING
  task.complete           → DELIVERING
  task.failed             → DELIVERING
  task.suspended          → CLARIFYING_WORKER
  user.input              → INTERRUPT_HANDLING
  task.cancel             → CANCELLING

DELIVERING:
  response.final          → LISTENING
  pending_results.non_empty → WEAVING

CLARIFYING_USER:
  user.input              → DISPATCHING

CLARIFYING_WORKER:
  user.input              → CLARIFYING_WORKER (same-turn HITL)
  task.resume             → COMPANIONING
  response.final          → (dynamic via response_final_table)

CANCELLING:
  task.failed             → DELIVERING

INTERRUPT_HANDLING:
  interrupt.routed        → DISPATCHING

PROACTIVE_WAKE:
  proactive.routed        → DELIVERING

WEAVING:
  response.final          → LISTENING
  pending_results.non_empty → WEAVING (re-weave)
```

### 4.3 Guard Matrix (330 cells)

Every (state, topic) pair maps to one of 5 guard actions:

| Action | Meaning | Cells |
|--------|---------|-------|
| `TRANSITION` | Validated state change | ~33 |
| `PASSTHROUGH` | Forward without state change | ~77 |
| `OBSERVE` | Log/history only | ~165 |
| `QUEUE` | Queue in FrontLock or pending_results | ~22 |
| `DEAD_LETTER` | Reject event | ~33 |

Unknown topics default to `DEAD_LETTER`. This is a **closed-world** design — no event can silently fall through.

### 4.4 Key FSM Components

| Component | File | Purpose |
|-----------|------|---------|
| `ConciergeController` | `controller.py` (~1,500 lines) | Central event router, 20 topic subscriptions |
| `ConversationArbiter` | `arbiter.py` (~750 lines) | Deterministic interrupt classifier (7-rule table) |
| `FrontLock` | `front_lock.py` | Priority queue concurrency gate for Front actor |
| `FSMTurnState` | `turn_state.py` | Ephemeral pending/deferred results tracking |
| `TaskBridge` | `task_bridge.py` (~650 lines) | FSM↔SessionState task lifecycle bridge |
| `Phase1Pipeline` | `phase1.py` | Classification protocol + stub |
| `UltraBERTPhase1Pipeline` | `ultrabert_phase1.py` | Real UltraBERT-backed classification |
| `K1UltraBERTAdapter` | `ultrabert_adapter.py` | Thread-safe singleton GPU adapter |
| `HistoryWriter` | `history_writer.py` | History write + Front/Back context converters |
| `ResponseFinalDecision` | `response_final_table.py` | 13-branch pure-function decision table |
| `DeadLetterConsumer` | `dead_letter_consumer.py` | Dead-letter reconciliation |
| `IdempotencyLedger` | `idempotency.py` | LRU-based envelope dedup (500 entries) |
| `ConciergeControlExtension` | `control_extension.py` | FSM state overlay on SS ControlSection |

### 4.5 Conversation Arbiter (M5)

Context-aware interrupt classification. No LLM call — deterministic 7-rule priority table:

| # | Condition | Decision | Confidence |
|---|-----------|----------|-----------|
| 1 | RED safety band | CANCEL (all) | 1.0 |
| 2 | Cancel intent + inflight | CANCEL (targeted/all) | 0.85-0.9 |
| 3 | Cancel intent + no inflight | PARALLEL_NEW | 0.7 |
| 4 | Domain+entity overlap ≥ thresholds | MODIFY_INFLIGHT | min(overlaps) |
| 5 | Defer pattern + inflight | DEFER | 0.8 |
| 6 | Inflight present | PARALLEL_NEW | 0.75 |
| 7 | No inflight | PARALLEL_NEW | 0.9 |

Supports OPP-2 recency decay on overlap scores.

### 4.6 Response Final Decision Table (13 branches)

Pure function `decide_response_final()` — zero side effects:

| State | Condition | Action | Target |
|-------|-----------|--------|--------|
| DISPATCHING | pending_results | TRANSITION_WEAVING | WEAVING |
| DISPATCHING | active_tasks | TRANSITION_COMPANIONING | COMPANIONING |
| DISPATCHING | neither | TRANSITION_LISTENING | LISTENING |
| DELIVERING | pending_results | TRANSITION_WEAVING | WEAVING |
| WEAVING | pending + no flush | TRANSITION_WEAVING | WEAVING |
| WEAVING | pending + flush running | STAY | — |
| DELIVERING | no pending | TRANSITION_LISTENING | LISTENING |
| WEAVING | no pending | TRANSITION_LISTENING | LISTENING |
| COMPANIONING | active_tasks | STAY | — |
| COMPANIONING | no active | TRANSITION_LISTENING | LISTENING |
| CLARIFYING_WORKER | active_tasks | TRANSITION_COMPANIONING | COMPANIONING |
| CLARIFYING_WORKER | no active | TRANSITION_LISTENING | LISTENING |
| LISTENING | spurious | IGNORE | — |

---

## 5. Protocols Layer

**Location**: `k1/concierge/protocols/` (20 files, ~7,800 lines)

### 5.1 Cancellation

- **`CancellationToken`**: Cooperative cancel primitive. Back checks at tool boundaries via `token.check()` which raises `TaskCancelledError`. Idempotent cancel.
- **`CancelReason`**: `USER_REQUESTED | TIMEOUT | SUPERSEDED`
- **`CancellationHandler`**: FSM-side lifecycle — register, cancel (write-before-mutate), confirm, late-completion detection, ledger-based crash recovery.

### 5.2 Suspension

- **`SuspensionType`**: `CLARIFICATION (60s) | APPROVAL (120s) | SELECTION (90s)` — timeouts from config.
- **`SuspensionRequest`**: Carries ReAct history + tool state for resume.
- **`SuspensionManager`**: Enforces limits (max 2 per task, max 1 concurrent), timeout watchers via `asyncio.Task`, write-before-mutate to ledger.

### 5.3 HITL (Human-in-the-Loop) — 6 files

Complete closed-cycle HITL orchestration:

| Component | Purpose |
|-----------|---------|
| `HILRequest/HILResponse` | Request/response dataclasses with safety band |
| `HILCoordinator` | Central hub — 8-step closed cycle |
| `HILFlowType` | 3 shapes: Clarification, Approval, Selection |
| `ClarificationContext/ApprovalContext/SelectionContext` | Structured context builders |
| `HILSubTask` | Persistence model with 4-state lifecycle (PENDING→RESOLVED/TIMED_OUT/CANCELLED) |
| `ResumeContext` | Back resume context with remaining budget (min-2 floor) |
| `validate_hitl_wiring()` | 14+ cross-layer consistency checks |

**Safety Band Escalation**: GREEN + side_effects → AMBER. RED always blocks. Unknown → AMBER (err on caution).

### 5.4 Weave

Async result delivery pipeline:

| Component | Purpose |
|-----------|---------|
| `WeaveAction` (5 values) | `IMMEDIATE / QUEUE_WEAVE / QUEUE / CHAIN / DEAD_LETTER` |
| `STATE_ACTION_TABLE` | Maps FSM state → WeaveAction |
| `WeaveBatcher` | 500ms batching window with Front-busy queueing |
| `WeavePolicy` | 9-rule adaptive decision engine |
| `WeaveDecision` (5 values) | `IMMEDIATE / BATCH / DEFER / DIGEST / SUPPRESS` |
| `PacingStrategy` (4 values) | `NONE / STAGGER / GROUP_BY_DOMAIN / PRIORITY_CASCADE` |

**WeavePolicy 9-Rule Table** (priority order):

| Rule | Condition | Decision |
|------|-----------|----------|
| R1 | LISTENING + idle > 10s | IMMEDIATE |
| R2 | has_critical + gate=open | IMMEDIATE |
| R3 | user_typing | DEFER |
| R4 | gate=suppress_all_non_safety | SUPPRESS |
| R5 | gate=suppress_trivial + no critical | DEFER |
| R5.5 | hitl_pending + no critical | DEFER |
| R6 | pending≥3 + all low | DIGEST |
| R7 | pending≥1 + idle > 3s | BATCH |
| R8 | pool_util > 0.8 | BATCH |
| R9 | default | BATCH (500ms) |

### 5.5 Delivery Strategy (OPP-8)

Answers HOW to present results (complements WeavePolicy's WHEN):

| `DeliveryMode` | Meaning |
|----------------|---------|
| `DIRECT_PRESENT` | Result IS the focus |
| `CONVERSATIONAL_WEAVE` | Mid-conversation insertion |
| `CONTEXTUAL_INJECT` | Silently add to context |
| `BRIEF_NOTIFY` | One-liner notification |
| `DEFERRED_QUEUE` | Store for later |

13-rule delivery engine with `ResultClassification` (AWAITED/FOLLOW_UP/BACKGROUND/TIME_SENSITIVE/INFORMATIONAL) and `ConversationFlowSignal` from SessionState.

### 5.6 Trust Accumulator (OPP-4)

Per-session trust score (0.0–1.0, starts 0.5):

- Approve → +0.05, Reject → -0.10, Cancel → -0.07, Modify → -0.03
- Auto-approve threshold: 0.85 (only for "low" risk)
- Dynamic max rounds: trust≥0.9 → base-1, trust≤0.2 → base+1

### 5.7 Task Lease

Temporal ownership for Back workers:

- `LeaseStatus`: `ACTIVE → SUSPENDED (HITL, TTL paused) → ACTIVE (resume)` or `→ EXPIRED/RELEASED/CANCELLED`
- Default TTL: 300s, max 3 renewals
- Integrates with `CancellationToken`

### 5.8 OPP Pipeline

8-primitive integration hub with lifecycle hooks:

| Hook | OPP | Call Site |
|------|-----|-----------|
| `on_classify` | OPP-2 | Phase 1 classification |
| `on_pre_prompt_build` | OPP-6, OPP-7 | Front prompt build |
| `on_pre_llm_call` | OPP-3 | Front LLM call |
| `on_task_complete` | OPP-8 | task.complete received |
| `on_hitl_outcome` | OPP-4 | HITL resolution |
| `on_pre_invoke` | OPP-4 | Pre-invoke trust gate |
| `on_idle_tick` | OPP-5 | 1s idle timer |
| `on_weave_flush` | OPP-1 | Weave batch flush |
| `on_natural_pause` | OPP-8 | Topic shift detected |

All hooks are no-op passthrough if primitive not attached. All wrap in try/except with safe defaults.

---

## 6. Actor Model

**Location**: `k1/concierge/actors/` (6 files, ~4,860 lines)

Concierge uses a **Front/Back actor split** — Front handles user-facing conversation (single-threaded via FrontLock), Back handles tool-intensive task execution in a worker pool.

### 6.1 Shared Utilities (`shared.py`)

Three helper functions used by both actors:

| Function | Purpose |
|----------|---------|
| `get_session_state(ctx)` | Extracts SS from handler context |
| `get_complexity_tier(ss)` | Reads `control.get_complexity_tier()` → string tier |
| `build_tool_context(ss, ctx)` | Creates `ToolContext` with writer_port, fabric_port, recall_fn, hil_coordinator |

### 6.2 Front Actor (`front.py`, ~1,250 lines)

The Front actor is the **user-facing conversational handler**. Never cancellable. Personality-aware, affect-modulated, streams text.

#### 10-Step Execution Flow

| Step | Action |
|------|--------|
| 1 | Read current FSM state + SS snapshot |
| 2 | Determine `PromptMode` from (state, topic, SS signals) |
| 3 | Compute `AffectBand` from `ss.affective_now` |
| 4 | Build `BuiltContext` via `DynamicPromptBuilder.build()` |
| 5 | Create `ToolDispatcher` (front, tier-filtered tools) |
| 6 | Create `LLMOutputValidator` with Front tool schemas |
| 7 | Run `react_loop()` → `ReactResult` |
| 8 | Extract `dispatched_tasks` from ReactResult |
| 9 | Emit result events to bus (`response.final`, `task.dispatch`, etc.) |
| 10 | Return FrontResult with text, dispatched tasks, metrics |

**Emission Ordering Invariant**: Cancel events → Normal dispatch events → Final response. This ensures the FSM processes cancellations before new dispatches.

### 6.3 Back Actor (`back.py`, ~1,380 lines)

The Back actor is the **tool-executing worker**. Operates on a SessionState snapshot-at-start (immutable during execution), uses tier-based tool filtering, and supports cooperative cancellation.

#### 7-Step Execution Flow

| Step | Action |
|------|--------|
| 1 | Snapshot SS at start (immutable for duration) |
| 2 | Resolve complexity tier → tool allowlist |
| 3 | Build back prompt via `build_back_prompt()` (~1,800-word template) |
| 4 | Create `ToolDispatcher` (back, tier-filtered) |
| 5 | Run `react_loop()` with `cancellation_check` wired to `CancellationToken` |
| 6 | Extract `submit_result` data from ReactResult |
| 7 | Return BackResult with submission payload + metrics |

**Tier-Based Tool Filtering**:

| Tier | Max Tools | Allowed |
|------|-----------|---------|
| LOW | 3 | recall_memory, discover_capabilities, invoke_capability, submit_result |
| MEDIUM | 6 | ALL 7 Back tools |
| HIGH | 6 | ALL 7 Back tools |

**Cooperative Cancellation**: Per-task `CancellationToken` checked at tool boundaries — never preemptive. `token.check()` raises `TaskCancelledError`.

#### Back Resume Flow (10 steps)

When a suspended task resumes after HITL:

| Step | Action |
|------|--------|
| 1 | Restore ReAct history from `SuspensionRequest` |
| 2 | Calculate remaining budget: `original - tools_called` (floor 2) |
| 3-10 | Same as normal Back flow with restored state |

### 6.4 Back Pool (`back_pool.py`, ~810 lines)

Pool of **3 workers** for concurrent Back task execution.

| Parameter | Value |
|-----------|-------|
| Pool size | 3 workers |
| Per-session max | 2 concurrent tasks |
| Overflow queue | Unbounded (tasks queued until worker available) |
| Lease TTL | 300s default (from `TaskLease`) |

**Lease Expiry Reclamation** (3-tier):

1. **Cooperative**: Request cancel via `CancellationToken`
2. **Grace period**: Wait for current tool to complete
3. **Hard kill**: `asyncio.Task.cancel()` if grace exceeded

**TaskLease Integration**: Each worker acquires a `TaskLease` before execution. Lease is released on completion, suspended on HITL, or reclaimed on expiry.

### 6.5 Back Topic Router (`back_router.py`, ~230 lines)

Routes incoming bus envelopes to appropriate Back handlers across 4 topics:

| Topic | Handler | Worker Needed |
|-------|---------|---------------|
| `task.dispatch` | New task execution | Yes |
| `task.resume` | Resume suspended task | Yes |
| `task.cancel` | Cancel active task | **No** (synchronous) |
| `clarification.response` | HITL response delivery | **No** (routes to coordinator) |

**Late-envelope discard**: If an envelope arrives for a task that has already completed/cancelled, it is discarded with a warning log.

### 6.6 Ready Queue (`ready_queue.py`, ~440 lines)

Dependency-ordered FIFO queue for multi-intent task dispatch.

| Feature | Behavior |
|---------|----------|
| `enqueue(task)` | Add task, respecting `depends_on` |
| `dequeue()` | Returns next ready task (all deps satisfied) |
| Cycle detection | Raises `CyclicDependencyError` |
| Unknown dep | Treat as satisfied → immediate dispatch |
| Failed predecessor | Cascading failure to all dependents |
| FIFO within priority | Equal-priority tasks dispatched in arrival order |

---

## 7. Prompt & LLM Subsystem

**Location**: `k1/concierge/prompt/` (9 files, ~3,200 lines) + `k1/concierge/llm/` (9 files, ~3,800 lines)

### 7.1 Prompt Modes (`prompt/mode.py`)

10 cognitive modes governing tool selection, SS reads, prompt sections, and iteration limits:

| Mode | Trigger | Purpose |
|------|---------|---------|
| `STANDARD` | Default (DISPATCHING + user_input) | Full ReAct with all tools |
| `CLARIFY_ASK` | Gaps detected → CLARIFYING_USER | Ask clarifying questions |
| `CLARIFY_RESOLVE` | User answered → DISPATCHING | Integrate clarification |
| `HITL_RELAY` | HITL surface → CLARIFYING_WORKER | Present HITL question |
| `HITL_RESOLVE` | User answered HITL → CLARIFYING_WORKER | Forward to Back |
| `PRESENT` | Task complete → DELIVERING | Present results |
| `WEAVE` | Pending results → WEAVING | Batch async delivery |
| `CANCEL` | Cancel flow → CANCELLING | Cancellation acknowledgment |
| `INTERRUPT` | User interrupt → INTERRUPT_HANDLING | Full ReAct (new context) |
| `ERROR` | Error fallback | Graceful degradation |

**Mode Resolution** (`determine_mode()`): 6-step priority — (1) topic overrides, (2) FSM state map, (3) SS signal overrides, (4) HITL detection, (5) pending results → WEAVE, (6) fallback → STANDARD.

### 7.2 Affect System (`prompt/affect.py`)

5 affect bands modulating tone, iteration budget, token caps, and vocabulary tier:

| Band | Valence Range | Token Cap | Iterations | Vocabulary |
|------|---------------|-----------|------------|------------|
| `CRISIS` | valence ≤ -0.6 | Reduced | Reduced (see CRISIS_MAX_ITERATIONS) | Safety-focused |
| `ELEVATED` | -0.6 < v ≤ -0.2 | Standard | Standard | Empathetic |
| `NEUTRAL` | -0.2 < v ≤ 0.2 | Standard | Standard | Standard |
| `POSITIVE` | 0.2 < v ≤ 0.6 | Standard | Standard | Warm |
| `LOW` | v > 0.6 | Standard | Standard | Standard |

`AffectModifiers` dataclass carries per-band overrides for `tone_guidance`, `iteration_cap_multiplier`, `max_tokens_multiplier`, `tool_budget_multiplier`, and `vocabulary_tier`.

### 7.3 Composable Prompt Sections (`prompt/sections.py`)

20 composable sections assembled per-mode via `MODE_SECTIONS` map:

| Section | Category | Description |
|---------|----------|-------------|
| `identity_core` | Identity | Core persona definition |
| `persona_prefs` | Identity | User-specific persona preferences |
| `safety_rules` | Safety | Safety band rules + crisis protocols |
| `domain_rules` | Safety | Domain-specific rules (8 domains) |
| `affect_guidance` | Affect | Tone + vocabulary from affect band |
| `temporal_context` | Context | Time, day, season, occasion |
| `beliefs_summary` | Context | Active beliefs (SPO triples) |
| `scoreboard` | Context | QUD, referents, topic, commitments |
| `clarifications` | Context | Open semantic gaps |
| `narrative_threads` | Context | Active conversation threads |
| `history_summary` | Context | Compressed history |
| `task_state` | Task | Active/completed/failed tasks |
| `task_artifacts` | Task | Task output artifacts |
| `pending_results` | Task | Queued async results |
| `tool_instructions` | Tools | Available tools + usage rules |
| `tool_budget` | Tools | Remaining tool budget |
| `output_format` | Output | Response formatting rules |
| `weave_items` | Weave | Pending weave items for delivery |
| `hitl_context` | HITL | Current HITL question + context |
| `cancel_context` | Cancel | Cancel flow context |

**11 SS Section Renderers**: Each renderer reads a specific SessionState section via `_safe_get_ss_section()` (catches all exceptions, returns None on failure).

**`SECTION_SOURCE_MAP`**: Maps logical section names to SS section readers. `temporal_context` maps to `control` sub-field (POC path; production reads from multimodal section).

### 7.4 Domain Rules (`prompt/domain_rules.py`)

8 domain rule sets with safety floors and mode-scoped applicability:

| Domain | Safety Floor | Key Rules |
|--------|-------------|-----------|
| `health` | AMBER | No diagnosis, no prescriptions |
| `finance` | AMBER | No specific investment advice |
| `legal` | AMBER | Not legal advice, suggest professionals |
| `travel` | GREEN | Validate dates, check advisories |
| `education` | GREEN | Age-appropriate, encourage autonomy |
| `family` | GREEN | Neutral, respect all perspectives |
| `home` | GREEN | Safety warnings for maintenance |
| `general` | GREEN | Default rules |

Coherence hierarchy: Safety rules > Domain rules > Affect guidance > Persona.

### 7.5 Clarification Depth (`prompt/clarify_depth.py`)

3-level escalation preventing infinite clarification loops:

| Depth | Strategy | Behavior |
|-------|----------|----------|
| 0 | Open question | Ask for more info |
| 1 | Specific options | Present 2-3 choices |
| 2 | Best guess | Proceed with most likely interpretation |

### 7.6 DynamicPromptBuilder (`prompt/builder.py`)

9-stage pipeline producing immutable `BuiltContext`:

| Stage | Action |
|-------|--------|
| 1 | Resolve mode → section list from `MODE_SECTIONS` |
| 2 | Apply affect modifiers (tone, iterations, tokens) |
| 3 | Read SS sections via `_read_ss_sections()` |
| 4 | Render section templates with data |
| 5 | Apply domain rules overlay |
| 6 | Format scenario-specific data |
| 7 | Interpolate placeholders |
| 8 | Estimate token count (`len(text) // 4` heuristic) |
| 9 | Compress if over budget (`_compress_prompt()` truncates from end) |

**Output**: `BuiltContext { system_prompt, messages, tools, max_iterations, mode, affect_band }`

### 7.7 Back Prompt (`prompt/back_prompt.py`)

Simple template substitution (~1,800-word constant template):

| Section | Content |
|---------|---------|
| Task description | From dispatch payload |
| Beliefs context | Active SPO triples |
| Task state | Current task progress |
| Artifacts | Previous task outputs |
| Safety band | Current safety level |
| Persona preferences | User preferences |
| Tier-based tool notes | Tool budget and allowed tools per tier |

### 7.8 LLM Port & Types (`llm/types.py`, `llm/ports.py`)

**`IConciergeModelPort`** — `@runtime_checkable` Protocol with 2 async methods:

| Method | Purpose |
|--------|---------|
| `generate(ConciergeModelRequest) → ConciergeModelResponse` | Single-shot LLM call |
| `generate_stream(ConciergeModelRequest) → AsyncIterator[StreamChunk]` | Streaming LLM call |

**Key Types**:

| Type | Kind | Purpose |
|------|------|---------|
| `Capability` (5 values) | Enum | CHAT, TOOL_CALL, STRUCTURED, STREAM, REASON |
| `FinishReason` (7 values) | Enum | STOP, TOOL_CALLS, LENGTH, ERROR, SAFETY, VALIDATION_FALLBACK, MALFORMED_TOOL_CALL |
| `ThinkingLevel` (4 values) | Enum | NONE, LOW, MEDIUM, HIGH |
| `ToolSchema` | Frozen DC | Provider-agnostic tool definition (name, params, actor, category, side_effects) |
| `ModelMessage` | Frozen DC | Role-based message (user/assistant/tool) with `_raw_provider_content` for thought signatures |
| `ConciergeModelRequest` | Frozen DC | Full LLM request (capability, system_prompt, messages, tools, tool_choice, temperature, thinking, model_hint, etc.) |
| `ConciergeModelResponse` | Mutable DC | Response with text, tool_calls, json_output, tokens, latency, finish_reason, thought_text |
| `StreamChunk` | Mutable DC | Streaming delta (text_delta, tool_call_delta, thought_delta, done) |
| `ToolCallResult` | Frozen DC | Parsed tool call (id, name, arguments) |

### 7.9 Model Selection (`llm/model_selection.py`)

Callers express INTENT ("fast", "smart", "cheap"), not model names.

**`MODEL_SELECTION_TABLE`** — (capability, actor) → model:

| Capability | Actor | Model |
|------------|-------|-------|
| CHAT/TOOL_CALL/STRUCTURED/REASON | front/back/planner | gemini-2.5-flash |
| CHAT | back | gemini-2.5-flash-lite |
| STREAM | front | gemini-2.5-flash-lite |

**`MODEL_HINT_OVERRIDES`**: fast/cheap → flash-lite, smart/thinking/pro/flash → flash.

**`select_model()` priority**: (1) hint override, (2) hint looks like model name → use directly, (3) table lookup, (4) capability-only fallback, (5) default model.

### 7.10 Gemini Adapter (`llm/gemini_adapter.py`)

The ONLY class that imports `google.genai`. All provider-specific translation happens here.

**Lazy Import**: `_ensure_genai()` defers SDK import until first use — fails fast with clear error if not installed.

**`GeminiConciergeAdapter`** methods:

| Method | Purpose |
|--------|---------|
| `generate(request)` | Single-shot with timeout enforcement via `asyncio.wait_for` |
| `generate_stream(request)` | Streaming via thread executor, accumulates raw Parts for thought signature round-trip |
| `generate_json(request, schema)` | Structured JSON output using Gemini JSON mode |
| `generate_batch(requests, max_concurrency)` | Concurrent batch via `asyncio.gather` + `Semaphore` |

**Critical Implementation Details**:

- **Tool result merging**: Consecutive tool-result messages merged into single Content(role="user") with multiple FunctionResponse parts — REQUIRED by Gemini for parallel tool calls
- **Thought signature preservation**: `_raw_provider_content` field preserves Gemini thought signatures across function-calling round-trips
- **Thinking budget**: 2.5 models use `ThinkingConfig(thinking_budget=N)` — LOW=1024, MEDIUM=8192, HIGH=24576 tokens
- **Error handling**: Timeout → FinishReason.ERROR, quota exhaustion (429) → specific log, generic errors → exc_info log

### 7.11 ModelHub Bridge (`llm/model_hub_bridge.py`)

Bridge connecting Concierge's POC LLM adapter to K1's ModelHub interface. Translates between POC types (`ConciergeModelRequest/Response`) and K1 types (`HubRequest/HubResponse`).

**`ModelHubPOCBridge`** — implements `IModelHubPort`:

| Method | Translation |
|--------|-------------|
| `execute(HubRequest) → HubResponse` | HubRequest → ConciergeModelRequest → inner.generate() → ConciergeModelResponse → HubResponse |
| `stream_execute(HubRequest) → AsyncIterator[HubChunk]` | Streaming delegation with chunk type mapping |
| `discover_capabilities()` | Returns POC capabilities from static table |
| `discover_models(capability)` | Reads `MODEL_SELECTION_TABLE` |
| `health()` | Always returns HEALTHY (no real health check) |

**Translation tables**: K1↔POC mappings for Capability, FinishReason, ThinkingLevel. Handles 4 payload types: ChatPayload, ToolCallPayload, StructuredOutputPayload, ReasonPayload.

**Cross-component imports**: 18 types from `k1.model_hub.types`, 2 from `k1.model_hub.ports`.

**Lifecycle note**: After M5 (Big Copy), the bridge swaps for the real Model Hub (M7).

### 7.12 Output Validation (`llm/validator.py`)

`LLMOutputValidator` — guardrails against hallucinated tool calls:

| Check | Behavior |
|-------|----------|
| Tool allowlist | All tool_calls reference known schemas |
| Required params | Each tool call supplies required arguments from JSON Schema |
| Param type spot-check | Top-level type mismatches (string, number, boolean, object, array) |

**Auto-fix**: Strips invalid tool calls, keeps valid ones. If no valid calls remain → returns None (caller applies fallback). Fixed responses get `FinishReason.VALIDATION_FALLBACK`.

### 7.13 Test Infrastructure

| Adapter | Purpose |
|---------|---------|
| `TestConciergeAdapter` | Deterministic test adapter keyed by (actor, scenario). Supports fixed responses, response sequences, call recording, assertion helpers |
| `TestModelHubBridge` | Convenience wrapper creating `ModelHubPOCBridge` around `TestConciergeAdapter` for K1-typed tests |

---

## 8. Tools & ReAct Loop

**Location**: `k1/concierge/tools/` (7 files, ~1,600 lines) + `k1/concierge/react/` (3 files, ~970 lines)

### 8.1 Tool Taxonomy

16 registered tool implementations split across Front and Back actors:

#### Front Tools (10)

| Tool | Category | Side Effects | Purpose |
|------|----------|-------------|---------|
| `update_beliefs` | cognitive | Yes | Create/correct factual beliefs (SPO triples with confidence) |
| `update_scoreboard` | cognitive | Yes | QUD, referent resolution, salience, topic shifts, commitments |
| `update_clarifications` | cognitive | Yes | Record semantic gaps in user intent |
| `update_narrative` | cognitive | Yes | Thread switches, resumptions, closures |
| `refine_affect` | cognitive | Yes | Override Phase 1 emotion classification with LLM assessment |
| `promote_belief` | cognitive | Yes | Promote low-confidence belief to HOT tier (MED/HIGH only) |
| `update_session_bundle` | cognitive | Yes | Batch write to multiple SS sections with idempotency |
| `recall_memory` | read | No | Query K0 long-term memory (shared with Back) |
| `summarize_context` | read | No | Compress SS sections to fit token budget |
| `dispatch_task` | control | No | Dispatch task to Back worker pool |

#### Back Tools (7)

| Tool | Category | Side Effects | Async | HITL Guard |
|------|----------|-------------|-------|------------|
| `recall_memory` | read | No | Yes | No |
| `discover_capabilities` | read | No | Yes | No |
| `invoke_capability` | action | Yes | Yes | **Yes** |
| `batch_invoke_capabilities` | action | Yes | Yes | No |
| `spawn_via_fabric` | action | Yes | Yes | No |
| `execute_workflow` | action | Yes | Yes | No |
| `submit_result` | control | No | No | No |

### 8.2 Tier-Based Tool Allowlists

#### Front Tier Allowlists (from `dispatcher.py`)

| Tier | Tools Available |
|------|----------------|
| LOW | 8 tools (all cognitive + recall_memory + summarize_context + dispatch_task) |
| MEDIUM | LOW + promote_belief |
| HIGH | Same as MEDIUM |
| CRISIS | ∅ (Front doesn't run ReAct in CRISIS) |

#### Back Tier Allowlists (from `schemas_back.py`)

| Tier | Tools Available |
|------|----------------|
| LOW | recall_memory, discover_capabilities, invoke_capability, submit_result |
| MEDIUM | ALL 7 tools |
| HIGH | ALL 7 tools |

#### Budget Limits

| Tier | Max Tool Calls |
|------|---------------|
| LOW | 5 |
| MEDIUM | 10 |
| HIGH | 20 |
| CRISIS | 3 |

`submit_result` is budget-exempt (Back must always be able to return results).

### 8.3 Tool Dispatch Pipeline (`tools/dispatcher.py`)

`ToolDispatcher` — 7-step validation and execution pipeline:

| Step | Check | On Failure |
|------|-------|------------|
| 1 | **Allowlist** — tool in actor's allowlist? | Error: "not allowed for actor" |
| 2 | **Budget** — `call_count < budget_limit`? | Error: "budget exhausted" (submit_result exempt) |
| 3 | **Schema validation** — JSON Schema validation of arguments | Error: "Invalid arguments: ..." |
| 4 | **Safety band** — CRISIS blocks side-effect tools | Error: "blocked in CRISIS tier" |
| 5 | **Execute** — `execute_tool(name, args, ctx)` | Error result from tool |
| 6 | **Bus events** — emit `tool.started` + `tool.completed` | Silently caught, never breaks execution |
| 7 | **Record** — increment `call_count`, append `DispatchRecord` | — |

Factory functions: `create_front_dispatcher(tier, ctx)`, `create_back_dispatcher(tier, ctx)`.

### 8.4 Tool Context & Implementations (`tools/implementations.py`)

`ToolContext` — execution context passed to every tool:

| Field | Type | Purpose |
|-------|------|---------|
| `session_manager` | Any | SessionStateManager |
| `writer_port` | Any | IWriterPort for SS mutations |
| `fabric_port` | IFabricPort | K1 Fabric for capability execution |
| `recall_fn` | Callable | K0 long-term memory callback |
| `hil_coordinator` | Any | HILCoordinator for safety gates |
| `bundle_idempotency_cache` | dict | Per-session dedup for bundle ops |
| `capability_cache` | dict | Per-session discover_capabilities cache |
| `active_task_id` | str | Current task ID |
| `actor` | str | "front" or "back" |

**HITL Safety Gate** (`invoke_capability`): Checks `hil_coordinator.get_pending_request()` before execution. Blocks if HITL pending. Checks `validate_before_invoke()` → may return `block_red` or `block_needs_approval`.

### 8.5 Parallel Execution Rules (`tools/parallelism.py`)

| Group | Tools | Cross-Group Parallelism |
|-------|-------|------------------------|
| `cognitive` | update_beliefs, update_scoreboard, update_clarifications, update_narrative, refine_affect, promote_belief | + read ✓ |
| `read` | recall_memory, summarize_context, discover_capabilities | + cognitive ✓, + action ✓ |
| `action` | invoke_capability, spawn_via_fabric, execute_workflow | + read ✓ |

**Always Sequential**: `dispatch_task` (must be last Front call), `submit_result` (must be last Back call).

`partition_calls(tools)` → batches: parallelizable first (one batch), then sequential tools each in own batch.

### 8.6 ReAct Loop (`react/loop.py`)

Single async implementation for both Front and Back actors.

#### Loop Signature

```
react_loop(actor, system_prompt, messages, tools, max_iterations,
           model: IModelHubPort, tool_dispatcher: ToolDispatcher,
           cancellation_check, validator, on_stream) → ReactResult
```

#### Iteration Constants

| Mode | Standard | Crisis |
|------|----------|--------|
| STANDARD | 6 | 4 |
| CLARIFY_ASK | 3 | 2 |
| CLARIFY_RESOLVE | 5 | 4 |
| HITL_RELAY | 1 | 1 |
| HITL_RESOLVE | 3 | 2 |
| PRESENT | 3 | 2 |
| WEAVE | 3 | 2 |
| CANCEL | 3 | 2 |
| INTERRUPT | 6 | 4 |
| ERROR | 2 | 2 |

#### Per-Iteration Flow

1. Restore tools after degenerate retry
2. **Cancellation check** → returns `ReactResult(status="cancelled")` if true
3. Build `HubRequest` (ChatPayload or ToolCallPayload depending on tools)
4. LLM call with timeout (`asyncio.wait_for`, from config)
5. Streaming for Front via `_streaming_generate()` when `on_stream` provided

#### Termination Conditions

| Condition | Actor | Result Status |
|-----------|-------|---------------|
| Text response, no tool calls | Front | `complete` |
| `submit_result()` tool call | Back | `complete` |
| `cancellation_check()` returns True | Both | `cancelled` |
| `max_iterations` reached | Both | `budget_exhausted` |

#### Special Behaviors

| Scenario | Behavior |
|----------|----------|
| **Iteration 0 (Front)** | `tool_choice="required"` — forces first tool call |
| **Last iteration (Front)** | Strip tools → force text-only output |
| **Last iteration (Back)** | Inject nudge message to call `submit_result` |
| **LLM ERROR finish** | Immediate bail with fallback |
| **Malformed tool call** | Nudge LLM to simplify, continue |
| **Degenerate (no text, no tools)** | Front: retry once with nudge + strip tools; Back: gentle/urgent nudge |
| **Validation failure** | Use fixed response if available; else fallback |
| **submit_result + other tools** | Warning logged, submit processed first, others skipped |

#### Tool Execution Within Iteration

1. Check for `submit_result` (Back termination, processed first)
2. Classify remaining tools via `classify_tool_batch()` → parallel vs sequential
3. Parallel tools: `asyncio.gather()` concurrent execution
4. Sequential tools: dispatched one-by-one
5. Results re-sorted to match LLM's original call order
6. `dispatch_task` results collected in `dispatched_tasks` with merged `task_id` and `_dispatch`
7. Tool results appended as observations via `tool_result_to_message()`

#### ReactResult

```
ReactResult:
  status: "complete" | "suspended" | "cancelled" | "budget_exhausted"
  text: str | None          # Front: final response. Back: None
  data: dict | None         # Back: submit_result args. Front: None
  dispatched_tasks: list    # dispatch_task calls collected
  parallel_tool_calls: int  # Observability
  sequential_tool_calls: int
  iteration_durations_ms: list  # Per-iteration wall-clock ms
```

### 8.7 Chat History Helpers (`react/history.py`)

| Function | Actor | Window | Filtering |
|----------|-------|--------|-----------|
| `build_chat_history()` | Front | Last `window * 2` entries | user, final, proactive |
| `build_chat_history_for_back()` | Back | Last `window` entries | user, final, hitl_response (truncated to 500 chars) |

### 8.8 End-to-End Pipeline

**Front LLM Pipeline**:

```
User Input → Envelope on bus → determine_mode() → compute_affect_band()
→ DynamicPromptBuilder.build() (9-stage) → BuiltContext
→ ConciergeModelRequest → LLMOutputValidator.validate()
→ react_loop() iterates until text response or max_iterations
```

**Back LLM Pipeline**:

```
Task dispatch → build_back_prompt() (template substitution)
→ ConciergeModelRequest → react_loop() with Back tools
→ submit_result() or budget_exhausted
```

---

## 9. Cross-Component Integration (Fabric, Bus, Orchestrator)

### 9.1 Fabric Subsystem (`fabric/`, 8 files)

Internal capability registry bridging POC mock handlers to K1 Fabric's typed contract system.

#### Capability Inventory

| Domain | Count | Examples |
|--------|-------|---------|
| Travel | 4 | hotel_search, hotel_booking, restaurant_search, restaurant_booking |
| Productivity | 5 | weather_forecast, calendar_create, get_todo_list, add_todo_item, complete_todo_item |
| Shopping | 4 | product_search, get_grocery_list, add_grocery_item, grocery_order |
| Messaging | 4 | send_message, send_group_message, send_reminder, send_notification |
| Household | 3 | get_chore_schedule, assign_chore, log_chore_complete |
| School | 3 | get_school_schedule, check_homework, school_pickup_status |
| Health | 4 | medication_reminder, schedule_appointment, pharmacy_refill, vet_appointment |
| Transport | 3 | ride_request, carpool_coordinate, package_tracking |
| IoT | 4 | smart_home_control, set_timer, nap_timer, home_security_status |
| Family | 3 | family_calendar, meal_planner, swim_bag_check |
| Finance | 1 | family_budget |
| Search (web) | 2 | web_search (DuckDuckGo), web_fetch (SSRF-protected HTTP) |
| **Total** | **40** | |

#### Key Components

| Component | Purpose |
|-----------|---------|
| `CapabilityRegistry` | In-memory registry with fuzzy intent matching (word overlap) + exact-name dispatch |
| `POCMockBridgeAdapter` | Implements K1 `IBridgePort` — bridges POC handlers to K1 Fabric's BridgeProvider |
| `IFabricPort` (Protocol) | Typed interface matching K1 Fabric's public API (`execute`, `discover_capabilities`) |
| `contract_converter` | Converts 40 POC dicts → K1 `CapabilityContract` objects |

**Dual-type design**: `IFabricPort` uses K1 types (`k1.fabric.types.CapabilityRequest`), while `OrchestratorStub` uses concierge-local types (`k1.concierge.orchestrator.types.CapabilityRequest`). Bootstrap adapters bridge between them.

### 9.2 Bus Subsystem (`bus/`, 5 files)

45 bus topics organized by prefix, with strict/relaxed delivery semantics.

#### Topic Summary

| Prefix | Count | Delivery | Purpose |
|--------|-------|----------|---------|
| `k1.session.*` | 5 | STRICT | User input, artifacts, turns, state |
| `k1.response.*` | 3 | STRICT | Stream, final response, clarification |
| `k1.orchestration.*` | 13 | STRICT | Task lifecycle, DAG, delta |
| `k1.tool.*` | 2 | STRICT | Tool started/completed |
| `k1.hil.*` | 2 | STRICT | HITL request/response |
| `k1.hitl.*` | 4 | STRICT | M6 HITL lifecycle audit |
| `k1.planner.*` | 1 | STRICT | Plan ready |
| `k1.internal.*` | 2 | STRICT | Weave batch, dead letter |
| `k1.backpool.*` | 3 | STRICT | Worker/lease lifecycle |
| `k1.arbiter.*` | 1 | STRICT | Intent arbitrated |
| `k1.affect/proactive/ui/conversation/metrics` | 10 | RELAXED | Background observability |

**Subscription Groups**:

- **FSM-routed** (8 topics): task_complete, task_failed, task_suspended, findings_ready, clarification_request, dag_completed, weave_batch, proactive_fill — must NOT appear in FRONT_SUBSCRIPTIONS (enforced with import-time assert)
- **Front** (4 topics): task_accepted, orchestration_delta, hil_request, plan_ready
- **Back** (7 topics): user_input, task_dispatch, task_cancel, task_resume, clarification_response, hil_response, affect_update

#### Envelope Builders

45+ builder functions producing `Envelope` objects with correct topic, priority (URGENT/INTERACTIVE/BACKGROUND), JSON payload, and `parent_id` for causal chaining. 14 topics have V3 canonical event schemas with typed `CanonicalEventMeta` subclasses.

#### Bus Setup (`bus/setup.py`)

Boot-time wiring using K1 infrastructure:

- `create_poc_bus()` → `BusFactory.create_local_ordered()` with middleware chain (TopicValidation → Tracing → Metrics)
- `create_poc_router()` → `BusFactory.create_mailbox_router(backend="python")`
- `register_poc_actors()` → front_half + back_half mailboxes with config-driven capacity

### 9.3 Orchestrator Subsystem (`orchestrator/`, 7 files)

Tier-based task routing with degradation cascade.

#### Routing Rules

| Tier | Route | Budget | Handler |
|------|-------|--------|---------|
| LOW | Bus → Back directly | — | Back ReAct loop via Fabric |
| MEDIUM | `TaskEnvelope` → `OrchestratorStub` | 2 Fabric calls | 1-2 coordinated Fabric calls |
| HIGH | `TaskEnvelope` → Orchestrator (future) | 10 Fabric + 3500 planner tokens | DAGExecutor + Planner (interface only) |

#### Degradation Cascade

```
HIGH + CB_PLANNER open → MEDIUM
MEDIUM + CB_ORCHESTRATOR open → LOW
LOW + CB_FABRIC open → CannedResponse
```

Circuit breakers are POC-simplified (open/closed only). Production needs HALF_OPEN + failure counting.

#### Orchestrator Invariants (structural enforcement)

| Invariant | Enforcement |
|-----------|-------------|
| ORCH-01: No SS writes | Only `IStateReadPort` injected (no write port) |
| ORCH-02: No LLM calls | No `IConciergeModelPort` dependency |
| ORCH-03: No tool execution | No `ToolDispatcher` dependency |
| ORCH-04: Every step through Fabric | Only `IFabricGatewayPort` for execution |
| ORCH-10: Max Fabric calls per budget | `_check_budget()` raises `BudgetExceededError` |

#### HIGH Tier Deferred Interfaces

6 abstract classes defined but not implemented: `IDAGExecutor`, `IPlannerService`, `IWorkflowEngine`, `IConnectorManager`, `IConstraintResolver`, `ISagaRecovery`.

---

## 10. Events, Delta & Observability

### 10.1 Event System (`events/`, 10 files)

V3 canonical event schema layer with 30 defined event types (24 registered for deserialization).

#### Event Hierarchy

| Category | Events | Registered |
|----------|--------|------------|
| Conversation | UserInputReceived, IntentArbitrated, DeadLettered, ResponseFinalDecided, Phase1Classified, TaskRouted | 4 of 6 |
| Task Lifecycle | TaskCreated, TaskLeased, TaskProgressed, TaskCompleted, TaskFailed, TaskCancelled | 6 of 6 |
| HITL (M1) | HILRequested, HILResolved, TaskSuspended, TaskResumed | 4 of 4 |
| HITL Lifecycle (M6) | HITLRequestedEvent, HITLResolvedEvent, HITLTimedOutEvent, HITLBlockedRedEvent | 0 of 4 |
| Weave | WeaveCandidateArrived, WeaveDecisionMade, WeaveEmitted, WeaveMetricsEvent | 4 of 4 |
| Mutation | TurnMutationSummary | 1 of 1 |
| BackPool | WorkerAcquired, WorkerReleased, TaskLeased, LeaseExpired, LeaseRenewed, TaskDeferred, DependencyFailed | 7 of 7 |

**`CanonicalEventMeta`** base class: 11 metadata fields providing correlation, causation tracking, and schema versioning. Separate from bus Envelope transport metadata (`event_id` ≠ `envelope_id`, `causation_id` ≠ `parent_id`).

**Validation**: Two-layer — (1) 8 required canonical metadata fields, (2) type-specific domain field presence. Chain validation ensures `causation_id` references earlier `event_id` in ordered lists.

### 10.2 Delta Subsystem (`delta/`, 9 files)

SessionState mutation pipeline enforcing the Single Writer Invariant.

#### Delta Pipeline

```
Back actor → emit_artifact() / emit_task_state_change()
  → SessionDelta(section, key, operation, data) → bus topic
    → DeltaAggregator (500ms fixed window, dedup, causal order)
      → DeltaApplicator (MutationGuard preflight → write → notify)
```

#### SessionDelta

| Field | Purpose |
|-------|---------|
| `section` | Target SS section (task_state, task_artifacts, history_active, control, meta) |
| `key` | Sub-key within section (e.g. task_id) |
| `operation` | set, append, update, delete |
| `data` | Mutation payload |
| `parent_delta_id` | Causal parent for ordering |

#### Aggregation Rules

- First delta starts 500ms timer (NOT sliding — new deltas don't reset)
- Dedup: last-write-wins per `section:key`
- Causal ordering: topological sort (BFS), parents before children
- Manual flush at turn boundaries

#### Applicator Pipeline

Per-delta: preflight (MutationGuard) → if rejected: evict → retry once → write to SS → notify.

#### Section Overflow Budgets

| Section | Budget | Eviction Strategy |
|---------|--------|-------------------|
| `control` | 8KB | No eviction |
| `beliefs_active` | 8KB | No eviction |
| `history_active` | 8KB | Sliding window (keep last 20) |
| `task_state` | 4KB | Evict terminal tasks |
| `task_artifacts` | 4KB | Evict oldest by timestamp |

#### Single Writer Invariant (ADR-0017g)

| Section | Authorized Writers |
|---------|-------------------|
| beliefs_active, clarifications, narrative_active | FRONT_LLM only |
| scoreboard | PHASE1, FRONT_LLM |
| affective_now | PHASE1, FRONT_LLM, EXPERIENCE_LAYER |
| control | FSM, PHASE1 |
| history_active, meta, task_state, task_artifacts | FSM only |
| persona | SESSION_INIT only |

Back LLM is **intentionally absent** — it never writes SS directly (emits deltas to bus instead).

#### Snapshot Reader

Lock-free SS reads returning shallow copies. Read isolation: concurrent reads get same snapshot, writes don't affect in-flight reads. Target: <1ms snapshot creation.

### 10.3 Observability (`obs/`, 4 files)

37+ Prometheus-style metrics across three subsystem instrumentations.

#### Metrics Infrastructure

| Component | Purpose |
|-----------|---------|
| `MetricEnvelope` | Frozen dataclass: name, type (counter/gauge/histogram/summary), value, labels, session_id |
| `MetricsCollector` | Per-session: increment/gauge/observe, drain to bus via `build_metric_emitted()` |
| `SlidingWindow` | 5-minute window: count, sum, mean, rate, percentile (p50/p95/p99) |
| `MetricAggregator` | Auto-creates SlidingWindow per (name, labels) key |
| `TurnTimer` | Per-turn latency breakdown: phase1, arbiter, front, fsm_routing, back, weave |

#### Actor Metrics

**Front** (per-mode, 7 metrics): invocation_count, iterations_used, iteration_utilization, tool_calls, degenerate_count, dispatched_tasks, duration_ms. Alerts on mode-specific violations (e.g. HITL_RELAY with >0 tool calls).

**Back** (per-tier, 7 metrics): invocation_count, iterations_used, budget_utilization, tool_calls, suspension_count, cancel_to_exit_latency_ms, duration_ms. Budget utilization classified: under (<0.3), healthy (0.3–0.8), near_exhaustion (0.8–1.0), exhausted (1.0).

#### ReAct Loop Metrics (~15 metrics per actor)

Exit path classification (priority): cancelled → suspended → budget_exhausted → forced_text → degenerate → normal. Counters per exit path + histograms for iterations, tool calls, duration.

#### Missing Obs Submodules

`__init__.py` docstring references alerts, fsm_metrics, hitl_metrics, arbiter_metrics, weave_metrics, phase1_metrics — these files do not exist yet.

---

## 11. Task, Scheduler & Kernel

### 11.1 Task Subsystem (`task/`, 12 files)

Pure data-model layer — no bus, no async, no I/O. Defines all task payloads, intent classification, complexity budgeting, and dependency resolution.

#### Core Types

| Type | Purpose |
|------|---------|
| `TaskIntent` (frozen DC) | Single discrete action: action, params, domain, urgency. Supports `$ref` placeholders for chained tasks |
| `ComplexityTier` (enum) | LOW / MEDIUM / HIGH with budget mapping (6 / 10 / 14 tool calls) |
| `TaskDispatch` (DC) | Front → Back payload: intents, tier, budget_hint, safety_band, depends_on, context_snapshot |
| `TaskComplete` (DC) | Back → Front success: final_answer, results, artifacts_created, tool_calls count |
| `TaskFailed` (DC) | Back → Front error: reason (8 valid values), error_code, partial_results, retries_attempted |

#### Intent Classification

| Classification | Condition | Dispatch Strategy |
|----------------|-----------|-------------------|
| SINGLE | 0–1 intents | 1 TaskDispatch with all intents |
| BUNDLED | 2+ intents, no `$ref` | 1 TaskDispatch with all intents |
| CHAINED | 2+ intents, any has `$ref` | N TaskDispatches linked via `depends_on` |

#### Dependency Queue

`TaskDependencyQueue` holds chained tasks until predecessor completes, then hydrates `$ref` placeholders:

- Pattern: `$prev.result.field.subfield` → `parent.results[0]["field"]["subfield"]`
- Graceful degradation: unresolvable `$ref` left as-is, Back detects and requests human input
- Failed predecessor: synthetic `TaskComplete` with `_parent_failed` marker cascaded to children

#### Parallel Safety (`parallel_safety.py`)

| Group | Tools | Parallelizable |
|-------|-------|---------------|
| reads | recall_memory, summarize_context, discover_capabilities | Yes (cross-group with cognitive) |
| cognitive_writes | update_beliefs, update_scoreboard, update_clarifications, update_narrative, refine_affect | Yes (cross-group with reads) |
| Sequential | promote_belief, dispatch_task, invoke_capability, spawn_via_fabric, execute_workflow, submit_result | No |

Unknown tools default to **sequential** (fail-safe). Config toggle `react.parallel_tools_enabled` can force all sequential.

#### Bundled Execution Plan

`BundledExecutionPlan` tracks sequential execution of multiple intents within a bundled dispatch. Records `IntentResult` per intent (success/error + tool_calls_used). Produces combined result for `submit_result`.

#### Task Receiver

Back-side actor routing incoming dispatches through dependency resolution:

- No dependency → execute immediately
- Dependency already complete → hydrate and execute immediately
- Dependency pending → buffer in dependency queue
- Failed predecessor → synthetic completion cascaded to children

### 11.2 Scheduler (`scheduler/`, 2 files)

`ProactiveScheduler` (OPP-5) — determines WHEN to trigger proactive messages during idle periods. Pure logic, no bus or async.

#### Trigger Types

| Type | Condition |
|------|-----------|
| `WAIT_STATUS` | Inflight tasks, idle ≤ 15s |
| `PROGRESS_UPDATE` | Inflight tasks, idle > 15s |
| `CONTEXT_TIP` | No tasks, idle ≤ 30s |
| `IDLE_CHECK_IN` | No tasks, idle > 30s |

#### Suppression Cascade (checked in order)

1. Disabled → None
2. Max triggers per session (10) reached → None
3. Below idle threshold (5s) → None
4. HITL pending → None (suppressed)
5. Affect band in suppress list (crisis, low) → None (suppressed)
6. Cooldown not elapsed (15s) → None

### 11.3 Kernel (`kernel/`, 3 files)

`bootstrap.py` is the **single point of truth** for how all components connect. No component self-registers.

#### Assembly Order (22 steps)

| Step | Component | Wiring |
|------|-----------|--------|
| 1 | Infrastructure | Bus, router, adapter, mailboxes via `poc.k1_poc.main.boot()` |
| 2 | Model | TestModelHubBridge or ModelHubPOCBridge(GeminiConciergeAdapter) |
| 3 | SessionState | `SessionStateFactory.create_standalone()` |
| 4 | CapabilityRegistry | `create_demo_registry()` (40 capabilities) |
| 5 | Fabric | POCMockBridgeAdapter → FabricFactory → register contracts |
| 6 | Ledger | InMemoryLedgerStore + LedgerWriter |
| 7 | FSM | ConciergeController(bus, router) |
| 8 | Phase 1 | UltraBERT adapter (if available) or stub |
| 9-11 | FSM wiring | Ledger, history sink, session state |
| 12-13 | Tool contexts + dispatchers | Front and Back ToolContext + ToolDispatcher |
| 14 | KernelRuntime | All components assembled |
| 15 | ExperienceLayer | Emotional + rhythm processing |
| 16 | Delta system | DeltaAggregator + DeltaApplicator |
| 17 | HITL | HILCoordinator with bus callbacks |
| 18-19 | Weave | WeaveBatcher + WeavePolicy |
| 20 | DeadLetterConsumer | Attached to bus |
| 21 | Orchestrator | OrchestratorStub with adapters |
| 22-23 | Subscriptions + consumer | Front events + mailbox polling |

#### Shutdown Order

Cancel consumer → flush ledger → log dead-letter summary → flush delta → FSM teardown → SS close → model close.

#### Mailbox Consumer

Polling loop: front_mailbox + back_mailbox with `timeout_ms=0`. Deduplication via `seen_front_ids`/`seen_back_ids` sets. Experience layer tick after each front handler. Back envelopes routed via `route_back_envelope()`.

#### Runner (`runner.py`)

CLI entry point: `python -m k1.concierge.kernel.runner` with args for `--test-mode`, `--tool-tier`, `--session-mode`, `--log-level`. Signal handling: SIGINT/SIGTERM → graceful shutdown.

---

## 12. Ledger, Experience, Identity & Compression

### 12.1 Ledger — Event-Sourced Conversation Timeline

The ledger is an append-only event log that captures every domain event in a session. All mutable session state can be derived as a pure projection from ledger events, enabling zero-state-loss crash recovery.

**Core types** (`ledger/store.py`):

| Type | Description |
|---|---|
| `LedgerEntry` | Frozen dataclass: `seq` (monotonic 1-based), `event_id` (UUID4 idempotency key), `event_type`, `session_id`, `payload` (serialized event), `written_at_utc` (ISO 8601) |
| `ILedgerStore` | Protocol: `append()`, `read()`, `read_by_type()`, `exists()` |
| `InMemoryLedgerStore` | Thread-safe in-memory implementation (POC). `SqliteLedgerStore` planned for M2+ |

**Writer** (`ledger/writer.py`): `LedgerWriter` — one per FSM controller instance, scoped to a single `session_id`. Both `append` (async) and `append_sync` provide idempotency via `event_id` deduplication. `_find_existing_seq()` is O(n) scan (POC; index planned).

**Projections** (`ledger/projections.py`): Six pure functions — events in, state out, zero side effects:

| Projection | Returns | Used For |
|---|---|---|
| `project_history` | `list[dict]` with turn/type/role/text/timestamp | History replay, debugging |
| `project_cancel_state` | `(active_task_ids, cancelled_task_ids)` | Cancel protocol recovery |
| `project_suspension_state` | `(active_suspensions, suspension_counts)` | Suspension recovery |
| `project_hitl_state` | `(pending_requests, hil_counts, hil_histories)` | HITL coordinator recovery |
| `project_task_states` | `task_id → TaskStateEntry` | Full task lifecycle |
| `project_pending_results` | `deque[dict]` | Weave candidate reconstruction |

History event mapping covers 12 canonical event types (user input, task lifecycle, HITL, weave, dead letter). Turn increments only on `conversation.user_input.received`.

**Recovery** (`ledger/recovery.py`): `CrashRecoveryOrchestrator` rebuilds FSM state from ledger events in dependency-safe order:

1. `project_task_states` → `fsm._task_bridge.rebuild_from_projection()`
2. `project_cancel_state` → `fsm._cancel_handler.rebuild_from_events()`
3. `project_suspension_state` → `fsm._suspension_manager.rebuild_from_events()`
4. `project_hitl_state` → `fsm._hil_coordinator.rebuild_from_events()`
5. `project_pending_results` → `fsm._turn_state.rebuild_from_projection()`
6. `project_history` → stored in `CrashRecoveryReport`
7. Derive `_active_task_ids` from projected task states
8. Derive FSM state: CLARIFYING_WORKER > WEAVING > COMPANIONING > DISPATCHING > LISTENING

Safe fallback on any failure (E9.5.5): recovery returns a report with `recovered=False` and error string.

### 12.2 Experience Layer — Cadence-Based Processing Pipeline

The Experience Layer orchestrates 6 components that run at configurable cadences after every turn, producing typed dataclass outputs consumed by the prompt builder and bus.

**Orchestrator** (`experience/layer.py`): `ExperienceLayer.tick(fsm_state, context)` returns `dict[str, typed_output]` with keys: `"emotional"`, `"tone"`, `"narrative"`, `"anticipation"`, `"fill"`, `"timing"`.

| Component | Output Dataclass | Cadence | Budget | Status |
|---|---|---|---|---|
| `EmotionalProcessor` | `EmotionalTrajectory` (valence/arousal/dominance/trend/confidence) | Every 25th turn | 1ms | ✅ Real |
| `AffectiveMirror` | `ToneAdjustment` (warmth/formality/pace/mirror_intensity) | Chained after EP | 1ms | ✅ Real |
| `NarrativeWeaver` | `NarrativeContext` (active_threads/salience/suggestion) | Every 20th turn | 10ms | ⬜ Stub |
| `AnticipatoryResponder` | `Anticipation` (predicted_intent/confidence/pre_fetch/hint) | Every 30th turn | 15ms | ⬜ Stub |
| `ProactiveAgent` | `FillMessage` (message/style/show_progress) | COMPANIONING + wait>5s | 50ms | ⬜ Stub |
| `RhythmController` | `TimingParams` (pre_delay/inter_chunk/typing_indicator/beat) | Every tick | 0.5ms | ✅ Real |

**EmotionalProcessor** algorithm: Extracts valence/arousal sequences from UltraBERT affect history → exponentially weighted averages (decay=0.7) → valence slope for trend (rising/falling/stable, threshold=0.08) → confidence = exp(-2 × variance) × sample_factor → dominance from transcript pattern heuristics (imperative starters, hedges, `?`/`!` signals).

**AffectiveMirror** strategy: Fulfillment-based, NOT emotional mirroring. Crisis → warmth+0.1, formality+0.1, pace=slow. Excited → warmth+0.1, pace=fast, mirror=0.7. Neutral → base values.

**RhythmController**: Computes `ResponseStyle` (concise/balanced/detailed) from user message lengths. < 30 chars → concise (verbosity 0.3); > 100 chars → detailed (0.7); linear interpolation between. Burst detection: avg_gap < 5s + ≥ 2 samples → `conversational_bursts`.

**EP skip rule**: If Front's `refine_affect()` confidence > threshold, EmotionalProcessor is skipped to avoid overwriting high-quality LLM corrections.

### 12.3 Identity — Dynamic Overlay on Static Persona

Static `PersonaSection` (frozen at session init) + dynamic `DynamicIdentityContext` (recomputed each turn).

**`DynamicIdentityContext.compute()`** produces `IdentitySnapshot` with:

| Field | Logic |
|---|---|
| `conversational_role` | Priority cascade: crisis/low→SUPPORTER, HIGH complexity→EXPERT, inflight→EXECUTOR, >10 turns→PEER, else→GUIDE |
| `domain_expertise` | Incremental: +0.1/turn in domain, capped at 1.0 |
| `formality_level` | Drift: ≤3 turns→0.6, >20 turns→0.3, linear decay between |
| `emotional_attunement` | Map: crisis→"Be calm and grounding", low→"Be gentle", neutral→"Natural", positive→"Match energy", elevated→"Acknowledge feeling" |
| `context_tags` | Tags: `multitasking`, `extended_session`, `domain:X`, `returning_topic` |

Output: `IdentitySnapshot.to_prompt_block()` injected into LLM prompts via OPP-7 hook.

### 12.4 Compression — Episodic Turn Compression

`EpisodicCompressor` compresses old conversation turns into episodic summaries to reduce token usage. Extractive heuristics (no LLM calls); subclass `compress_segment()` for abstractive compression.

| Config | Default | Description |
|---|---|---|
| `recent_window` | 10 | Recent turns kept uncompressed |
| `episode_size` | 5 | Turns per compressed episode |
| `compression_strategy` | `KEY_FACTS` | `KEY_FACTS` / `EXTRACTIVE` / `TOPIC_SUMMARY` |
| `preserve_hitl_turns` | `True` | Never compress HITL turns |
| `preserve_safety_turns` | `True` | Never compress RED/AMBER turns |
| `min_turns_to_compress` | 15 | Activation threshold |

**Token economics**: 25 raw turns × ~200 tokens = ~5000 tokens → 5 episodes × ~80 + 10 recent × ~200 = ~2400 tokens (~50% reduction). Wired via OPP-6 `on_pre_prompt_build` hook.

### 12.5 Cross-Component Dependencies

All four subsystems are highly self-contained:

- **Ledger**: Only imports `k1.concierge.events.base` (TYPE_CHECKING) and `k1.concierge.protocols.hitl_persistence` (TaskStateEntry). Recovery uses duck-typed FSM (5 `rebuild_*` methods).
- **Experience**: Only imports `k1.concierge.config` (get_config). All 6 components are stdlib-only.
- **Identity**: Zero cross-component imports. Stdlib only.
- **Compression**: Zero cross-component imports. Stdlib only.

---

## 13. Cross-Component Wiring Analysis

### 13.1 Unified Architecture Diagram

The single source of truth is `concierge_unified.mmd` (1,334 lines, `flowchart TB` with `elk` layout, merged 2026-04-01). It supersedes the POC diagram (`docs/concierge_poc_architecture.mmd`, 1,086 lines). The unified diagram adds hexagonal port/adapter layer, streaming infrastructure, lifecycle phases, invariant annotations, and performance baselines not present in the POC.

### 13.2 Layered Architecture (Inside → Out)

| Layer | Components | Function |
|---|---|---|
| Input/Output Boundary | 8 Ports + 16 Adapters (8 prod + 8 test) | Hexagonal boundary with 7 circuit breakers |
| Phase 1 (Deterministic, 22ms) | ACKING_CORE: UltraBERT v4 (12 heads), Safety Gate, Complexity Router, Hypothesis Pipeline, Temporal/Spatial Resolution, Context Inference, Uncertainty Routing, OPP-2 Decay, Write Elision Gate | Pre-LLM classification and routing |
| Phase 2 (LLM-Driven) | Front Actor (10 tools), Back Actor (7 tools), ReactLoopScratchpad, ReAct Recovery | Dual-LLM conversation + task execution |
| State Layer | SessionState (HOT 52KB + WARM 48KB), MutationGuard (3-tier) | Shared memory with single-writer invariant |
| Protocol Layer | HITL (3 variants + L2), Weave, Cancel, Suspend, OPP Pipeline (8 primitives, 9 hooks) | Cross-cutting coordination protocols |
| Experience Layer | 6 components (3 real + 3 stubs) | Emotional processing, rhythm, narrative |
| Streaming Layer | 8 components (~150 tests) | StreamConsumer, ChunkRouter, TextChunkAggregator, ToolCallStreamHandler, ThinkingTraceHandler, PartialResponseBuffer, SSEEmitter, StreamCancellationGuard |
| Service Layer | 9 internal services (~585 tests) | FSMController, TurnProcessor, IntentProcessor, ComplexityRouter, ToolDispatcher, OutputManager, DeltaAggregator, ClarificationTracker, ContextAssembler |
| Lifecycle Layer | 6 phases | init, turn_start, turn_end, abbreviated, shutdown, crash_recovery |

### 13.3 External Touchpoint Wiring

| Touchpoint | Direction | Port | Protocol | Circuit Breaker |
|---|---|---|---|---|
| Orchestrator | Concierge → Orch (TaskEnvelope); Orch → Concierge (accepted/delta/dag.completed) | IDispatchPort + IDeltaPort | dispatch_envelope → task.accepted | CB_ORCHESTRATOR (60s, 2/min) |
| Planner | Via Orchestrator → PlanRequest → CommittedPlan | IDispatchPort (indirect) | Orchestrator internal | CB_PLANNER (45s, 2/min) |
| Fabric | Back tools → dispatch_direct; Orchestrator → per-step | IDispatchPort | CapabilityRequest / batch | CB_FABRIC (30s, 5/min) + CB_MCP (10s, 3/min) |
| Model Hub | Front/Back LLM calls | ILLMPort | execute / stream_execute (5 capabilities) | CB_MODEL |
| Session State | Read/Write all sections | IStatePort | MutationGuard 3-tier validation | CB_SESSIONSTATE (100ms, 10/min) |
| K0 Bridge | recall_memory; turn_end checkpoint | IMemoryPort + direct | recall(); fire-and-forget checkpoint | — |
| Memory Writer | Subscribes to turn.complete.v1 | IDeltaPort (event) | 0-3 factual memories/turn | — |
| Learning Loop | Subscribes to turn.complete.v1 | IDeltaPort (event) | FeedbackEnvelope, 5 detectors | — |
| Output System | All output through OUTPUT_CHANNEL | IOutputPort | SSE / WebSocket, 3 priority queues | CB_SSE (5s reconnect, 3/min) |

### 13.4 Tier Routing & Degradation Cascade

| Tier | Latency | Path | Tool Budget | Token Budget |
|---|---|---|---|---|
| LOW | < 2s | Front → dispatch → Back → invoke_capability → submit | 4 | 500 |
| MEDIUM | 2-10s | Front → dispatch → OrchestratorStub (1-2 Fabric calls) | 8 | 2K |
| HIGH | 10-45s | Front → TaskEnvelope → Orchestrator → Planner 4-stage → DAG | 12 | 8K |
| CRISIS | < 5s | Safety Override → hardcoded string, zero deps | 0 | 0 |

**Degradation cascade**: HIGH (CB_PLANNER open) → MEDIUM → (CB_ORCH open) → LOW → (CB_FABRIC open) → canned response.

### 13.5 Complete Event Flow Traces

**Happy Path (LOW)**:

```
User → IInputPort → FSM(LISTENING→DISPATCHING) → UltraBERT(22ms) → WriteElisionGate → IStatePort
  → Bus(user.input.v1) → Front(subscribe) → react_loop: ack → recall → beliefs → dispatch_task
  → Bus(task.dispatch.v1) → FSM(DISPATCHING→COMPANIONING) → Back(subscribe)
  → react_loop: invoke_capability → IDispatchPort → Fabric → submit_result(complete)
  → Bus(task.complete.v1) → FSM(COMPANIONING→DELIVERING) → Front(PRESENT mode) → response.final
  → OUTPUT_CHANNEL → FSM(DELIVERING→LISTENING)
```

**Interrupt**: New user.input during COMPANIONING → FSM → INTERRUPT_HANDLING → turn_end_abbreviated → re-classify → DISPATCHING.

**HITL**: submit_result(needs_human) → task.suspended → FSM → CLARIFYING_WORKER → Front(HITL_RELAY) → clarification → user responds → task.resume → Back resumes from ReAct history.

**Weave**: task.complete while Front busy → Guard: QUEUE → WeaveBatcher(500ms window) → weave.batch.v1 → FSM → WEAVING → Front(WEAVE mode) → drain → LISTENING.

**Causal chain**: Every event carries `parent_id` forming a tree: user.input(#1) → ack(#2,p=1) + task.dispatch(#3,p=1) → tool.started(#4,p=3) → tool.completed(#5,p=4) → task.complete(#6,p=3) → response.final(#7,p=6).

### 13.6 OPP Pipeline Wiring

| Hook | OPP | Key Parameters |
|---|---|---|
| `on_classify` | OPP-2 Recency Bias Decay | decay_per_turn=0.15, short_input<3 words=50% penalty |
| `on_pre_prompt_build` | OPP-6 Episodic Compression + OPP-7 Dynamic Identity | recent_window=10, episode_size=5 |
| `on_pre_llm_call` | OPP-3 Affect Hard Caps | CRISIS=512tok, LOW=1024, NEUTRAL=uncapped, POSITIVE=2048, ELEVATED=1536 |
| `on_hitl_outcome` / `on_pre_invoke` | OPP-4 Trust Accumulator | initial=0.5, auto-approve ≥0.85 AND risk≤0.5 |
| `on_idle_tick` | OPP-5 Proactive Scheduler | idle=5000ms, cooldown=15000ms, max=10/session |
| `on_weave_flush` | OPP-1 Paced Delivery | NONE / STAGGER / GROUP_BY_DOMAIN / PRIORITY_CASCADE |
| `on_task_complete` / `on_natural_pause` | OPP-8 Natural Flow Delivery | 13-rule table (D1-D13), 5 modes |

### 13.7 SessionState Architecture

**HOT tier** (52KB, 10 sections):

| Section | Size | Writer | Eviction |
|---|---|---|---|
| `beliefs_active` | 8KB | Front LLM | → beliefs_warm after 20 turns |
| `scoreboard` | 6KB | Phase1 + Front | Rewritten per turn |
| `affective_now` | 4KB | Phase1 + Front + EP | Later write wins |
| `clarifications` | 4KB | Front LLM | Clear resolved after 5 turns |
| `narrative_active` | 4KB | Front LLM | Summarize after 50 turns |
| `control` | 8KB | FSM + Phase1 | FlowState, TurnLock, IntentClass, DomainCtx, SafetyCtx |
| `history_active` | 8KB | FSM | 9 entry types, sliding window 20 |
| `meta` | 2KB | FSM | Turn count, latency, telemetry |
| `task_state` | 4KB | FSM (via DeltaAggregator) | Per-task status tracking |
| `task_artifacts` | 4KB | FSM (via DeltaAggregator) | → artifacts_warm after 10 turns |

**WARM tier** (48KB, 4 sections): beliefs_warm, history_warm, artifacts_warm, narrative_warm.

**Static**: `persona` (immutable — tone, personality, family members, preferences).

**MutationGuard**: 3-tier validation (section capacity → HOT/WARM budget → overall limit). Emergency: ≥95% → ALL writes rejected.

### 13.8 Performance Baselines

| Component | P99 |
|---|---|
| UltraBERT classify | 25ms |
| Intent ack SSE | 50ms |
| FSM transition | 1ms |
| MutationGuard | 0.2ms |
| Phase 1 write | 0.02ms |
| Phase 2 write | 0.1ms |
| Output → SSE | 5ms |
| Orchestration dispatch | 2ms |
| **Total overhead/turn** | **~32ms** (excluding LLM) |

Budget envelopes: LOW=2s, MED=10s, HIGH=45s, CRISIS=5s. Single LLM timeout=30s. Planner stage=10s/stage.

### 13.9 Lifecycle Phases

| Phase | Key Steps |
|---|---|
| `init(session_id)` | Create 9 services, connect 8 ports, restore state (LOCAL COLD first), load persona, init 7 CBs→CLOSED, start subscriptions + DeltaAggregator, FSM→LISTENING |
| `turn_start(message)` | Acquire Single Writer lock (lock_version++), increment turn_sequence_number, read HOT snapshot, reset ToolDispatcher/ClarificationTracker/ContextAssembler, allocate budget |
| `turn_end()` | Flush OutputManager, append history, update telemetry, release lock, checkpoint LOCAL COLD (<1ms), checkpoint K0 (fire-and-forget), check experience triggers, emit turn.complete.v1 |
| `turn_end_abbreviated()` | Cancel in-flight, flush partial, record INTERRUPTED, release lock, checkpoint LOCAL COLD. SKIP: history, telemetry, K0, experience |
| `shutdown()` | Close IInputPort, wait active turn 30s, flush aggregator + output, final checkpoint (LOCAL COLD + K0 5s wait), stop background, disconnect ports LIFO |
| `crash_recovery(session_id)` | Bootstrap, detect turn_lock, rollback, reconcile Local Outbox, restore from LOCAL COLD, resume LISTENING. Max loss: 1 turn |

---

## 14. Invariants

### FSM Invariants (16)

| # | Invariant | Enforced By |
|---|-----------|-------------|
| 1 | FSM is sole writer to `history_active` | `_write_history()` single path |
| 2 | FSM is sole writer to `task_state` and `task_artifacts` | All writes via `TaskBridge` |
| 3 | Phase 1 completes before Front LLM starts | `TurnLock` sequencing |
| 4 | Front LLM is single-actor (no concurrent calls) | `FrontLock` serializes |
| 5 | Every (state, topic) pair has explicit guard action | 330-cell `FULL_GUARD_TABLE` |
| 6 | Transitions validated against `TRANSITION_TABLE` | `is_legal()` check |
| 7 | Cancellation wins over late completion | `CancellationHandler` dedup |
| 8 | Same `envelope_id` processed at most once | `IdempotencyLedger` (LRU 500) |
| 9 | Dead-letters are observable, not silent drops | `DeadLetterConsumer` |
| 10 | Ledger write before in-memory mutation | TaskBridge + FSMTurnState + _write_history |
| 11 | ControlExtension syncs to SS on every mutation | `_sync_to_section()` |
| 12 | TaskBridge rejects mid-flight rebind | RuntimeError if task ACTIVE |
| 13 | Arbiter is deterministic (same inputs = same output) | No LLM, no randomness |
| 14 | Overflow → dead-letter, never silent discard | FrontLock, FSMTurnState |
| 15 | Safety RED always forces CANCEL ALL | Arbiter priority 1 |
| 16 | Deferred results force-deliver after 5 consecutive defers | `mark_deferred()` counter |

### Protocol Invariants (10)

| # | Invariant | Enforced By |
|---|-----------|-------------|
| P1 | No side-effect capability without user approval | `detect_approval_required()`, L2 `validate_before_invoke()` |
| P2 | Every HITL shape follows the same closed cycle | `HILCoordinator` uniform flow |
| P3 | Every HITL cycle closes (timeout guarantees) | `SuspensionManager._watch_timeout()` |
| P4 | `pending_hil` survives process restarts | `TaskStateEntry.pending_hil` → SessionState |
| P5 | Max 2 suspensions per task | `SuspensionManager.suspend()` |
| P6 | Max 1 concurrent suspension per task | `SuspensionManager.suspend()` |
| P7 | ReAct history preserved across suspension | `SuspensionRequest.react_history` |
| P8 | Approval modifications applied before execution | `apply_approval_modifications()` |
| P9 | No heuristic flags in HITL flows | `validate_hitl_wiring()` |
| P10 | Cancellation is cooperative, not preemptive | `CancellationToken.check()` at tool boundaries |

---

## 15. Test Coverage

### 15.1 Aggregate Statistics

| Metric | Count |
|---|---|
| Test files (tests/k1/concierge/) | 75 |
| POC test file (tests/poc/) | 1 |
| In-source test helpers (k1/concierge/llm/) | 2 |
| Total test classes | 548 |
| Total test functions | 2,679 |
| Total test lines | 38,286 |

Tests follow `test_mXX_eYY_*.py` naming (milestone + epic) or `test_<feature>.py` for standalone features.

### 15.2 Coverage by Subsystem

| Subsystem | Test Files | Classes | Funcs | % of Total |
|---|---|---|---|---|
| FSM (guard, arbiter, controller, response-final) | 11 | 99 | 551 | 20.6% |
| Weave (signal, decision, batch, policy) | 4 | 33 | 299 | 11.2% |
| Delta + Overflow | 3 | 50 | 254 | 9.5% |
| Tools (travel, calendar, family, monitor, fabric) | 8 | 67 | 224 | 8.4% |
| Experience Layer | 1 | 11 | 171 | 6.4% |
| Observability (metrics, react metrics) | 2 | 19 | 153 | 5.7% |
| Session State (binding, write, bundle, prompt-SS) | 4 | 33 | 152 | 5.7% |
| LLM (bridge, types, ports, adapter, validator) | 5 | 62 | 139 | 5.2% |
| UltraBERT / Phase1 | 5 | 29 | 134 | 5.0% |
| Task (dispatch, receiver, parallel) | 3 | 32 | 131 | 4.9% |
| Recovery (M09) | 6 | 22 | 105 | 3.9% |
| Protocol (resume, conformance) | 3 | 17 | 89 | 3.3% |
| Fabric (port, wiring, converter, POC) | 4 | 14 | 75 | 2.8% |
| Bus (topics, builders, compliance) | 3 | 15 | 71 | 2.7% |
| Ports + Adapters | 12 | 24 | 73 | 2.7% |
| Events / Ledger | 2 | 17 | 69 | 2.6% |
| Cross-cutting (C1, gap, two-way) | 3 | 23 | 60 | 2.2% |
| V3 Conformance | 1 | 17 | 55 | 2.1% |

### 15.3 Top 5 Largest Test Files

| File | Funcs | Lines | Focus |
|---|---|---|---|
| `test_m00_v3_conformance.py` | 55 | 1,992 | Full V3 FSM conformance |
| `test_m15_experience_layer.py` | 171 | 1,492 | All 7 experience components |
| `test_m11_epics_7_8_9.py` | 79 | 1,170 | Delta overflow, E2E pipelines |
| `test_m02_e24_conformance.py` | 47 | 1,095 | Guard matrix, dead letter, HITL |
| `test_m11_obs_e111.py` | 98 | 1,064 | Metric envelope, collector, aggregator |

### 15.4 Coverage Gaps (25 of ~120 source files untested, ~21%)

| Category | Untested Modules | Risk |
|---|---|---|
| **kernel/** (bootstrap.py, runner.py) | 2 | 🔴 HIGH — core wiring & execution |
| **orchestrator/** (all 6 files: degradation, interfaces, ports, routing, stub, types) | 6 | 🟡 MEDIUM — orchestration layer |
| **prompt/** (back_prompt, clarify_depth, domain_rules, scenario_templates) | 3-4 | 🟡 MEDIUM — prompt construction |
| **protocols/** (delivery_strategy, hitl_flow, hitl_persistence, hitl_pipeline, opp_pipeline, task_lease, trust_accumulator) | 5-7 | 🟡 MEDIUM — protocol definitions |
| **llm/** (gemini_adapter, model_selection) | 2 | 🟡 MEDIUM — live adapter + model selection |
| **Other** (bus/deserialize, compression, identity, scheduler, task/dependency_queue) | 5-7 | 🟢 LOW-MEDIUM |

### 15.5 Key Observations

1. **FSM + Weave dominate**: 850 test functions (31.7%) reflecting state machine and delivery complexity.
2. **Recovery tests are systematic**: Each protocol has its own ledger-write + projection + rebuild file, plus full E2E orchestrator test.
3. **No M06/M07 tests in k1**: These milestones only have tests in `tests/poc/`.
4. **Orchestrator entirely untested**: All 6 files in `orchestrator/` have zero coverage — highest-risk gap.
5. **Kernel bootstrap/runner untested**: Core assembly has no dedicated tests.
6. **Port compliance double-tested**: Both `test_c1_port_protocols.py` (35 funcs) and `ports/test_port_protocols.py` (16 funcs).
7. **In-source test helpers** (`llm/test_adapter.py`, `llm/test_model_hub_bridge.py`): Test infrastructure imported by real tests; contain zero `test_*` functions themselves.

---

## 16. Gaps & Risks

### 16.1 Critical Gaps (🔴)

| # | Gap | Impact | Location |
|---|---|---|---|
| G-1 | **Kernel bootstrap/runner have zero tests** | Core 22-step assembly and CLI entry point are untested. Bootstrap wiring errors would only surface at runtime. | `kernel/bootstrap.py`, `kernel/runner.py` |
| G-2 | **Orchestrator subsystem entirely untested** | All 6 files (degradation, interfaces, ports, routing, stub, types) have no test coverage. OrchestratorStub is the MED/HIGH tier gateway. | `orchestrator/*.py` |
| G-3 | **6 unregistered event types** | `Phase1Classified`, `TaskRouted`, and 4 M6 HITL lifecycle events are defined but NOT in `EVENT_TYPE_REGISTRY`. Deserialization will fail for these types. | `events/registry.py` |
| G-4 | **Missing obs submodules** | `alerts`, `fsm_metrics`, `hitl_metrics`, `arbiter_metrics`, `weave_metrics`, `phase1_metrics` referenced in `obs/__init__.py` but files do not exist. Importing these will raise ImportError. | `obs/__init__.py` |

### 16.2 Architectural Risks (🟡)

| # | Risk | Impact | Location |
|---|---|---|---|
| R-1 | **Dual-type design** in orchestrator/fabric | `IFabricPort` uses K1 types (`k1.fabric.types.CapabilityRequest`), while `OrchestratorStub` uses concierge-local types (`k1.concierge.orchestrator.types.CapabilityRequest`). Bootstrap adapter `_FabricGatewayAdapter` bridges between them. Types are structurally incompatible by design (different field names/types). ✅ Verified correct in E-0.5.5. | `orchestrator/types.py`, `fabric/ports.py`, `kernel/bootstrap.py` |
| R-2 | **InMemoryLedgerStore is POC-only** | Thread-safe but not persistent. `_find_existing_seq()` is O(n). No `SqliteLedgerStore` implemented yet (planned M2+). Crash recovery works but data is lost on process restart. | `ledger/store.py` |
| R-3 | **Circuit breakers are POC placeholders** | Referenced in unified diagram with specific parameters (timeouts, rates) but actual implementations are not wired in the current codebase. Degradation cascade relies on them. | Diagram vs. code |
| R-4 | **3 experience components are stubs** | NarrativeWeaver, AnticipatoryResponder, ProactiveAgent return defaults. OPP-5 proactive scheduler exists but the ProactiveAgent it triggers is a no-op. | `experience/narrative_weaver.py`, `experience/anticipatory_responder.py`, `experience/proactive_agent.py` |
| R-5 | **Trust accumulator untested** | OPP-4 auto-approve logic (≥0.85 trust AND ≤0.5 risk) has no test coverage. Incorrect trust scores could auto-approve dangerous operations. | `protocols/trust_accumulator.py` |
| R-6 | **Compression has no tests** | `EpisodicCompressor` (OPP-6) is wired via `on_pre_prompt_build` but has zero test coverage. Incorrect compression could drop important context. | `compression/episodic_compressor.py` |
| R-7 | **Identity has no tests** | `DynamicIdentityContext` (OPP-7) computes per-turn identity snapshots for prompt injection with zero test coverage. | `identity/dynamic_identity.py` |

### 16.3 Cross-Component Wiring Gaps (from prior scans)

| # | Gap | Components |
|---|---|---|
| W-1 | ModelHub↔Planner: `HubRequest`/`HubResponse`/`RequestConstraints` type duplication | `k1.model_hub.types` vs `k1.planner.types` |
| W-2 | Fabric: `IModelGatewayPort` missing production adapter | `k1.fabric.ports` |
| W-3 | ModelHub: Fabric bridge missing, MemoryWriter bridge missing | `k1.model_hub` |
| W-4 | Fabric: Bridge client not built | `k1.fabric` |
| W-5 | ~~Orchestrator: Concierge POC types still present~~ ✅ E-0.5.5: Verified as intentional concierge-local contract layer with translation adapter | `k1.concierge.orchestrator.types` |
| W-6 | SessionState: MemoryWriter adapter missing, Concierge direct imports | `k1.sessionstate` |
| W-7 | ModelHub: Concierge import bug | `k1.model_hub` |

### 16.4 Recommended Priorities

1. **Immediate**: Register the 6 missing event types in `EVENT_TYPE_REGISTRY` (G-3) — 10 min fix, prevents runtime deserialization failures.
2. **Immediate**: Remove or guard the missing obs submodule references in `obs/__init__.py` (G-4) — prevents ImportError.
3. **High**: Add integration tests for `kernel/bootstrap.py` (G-1) — the 22-step assembly is the single most critical untested code path.
4. **High**: Add tests for `orchestrator/stub.py` and `orchestrator/routing.py` (G-2) — these are the MED/HIGH tier gateways.
5. **Medium**: Consolidate dual-type design (R-1) — either use K1 fabric types everywhere or formalize the adapter bridge as a first-class pattern.
6. **Medium**: Test OPP primitives: trust_accumulator (R-5), compression (R-6), identity (R-7).
