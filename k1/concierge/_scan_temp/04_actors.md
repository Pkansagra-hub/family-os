# Actors Subsystem Scan — k1.concierge.actors

> Scanned: 2026-04-04
> Files: 7 (`__init__.py`, `shared.py`, `front.py`, `back.py`, `back_pool.py`, `back_router.py`, `ready_queue.py`)
> Total scope: ~2,200 lines of production code

---

## 1. Subsystem Purpose

The `actors` package implements the **Front/Back Actor Model** — the two-actor LLM architecture that powers the K1 Concierge. It separates concerns into:

- **Front Actor**: User-facing conversational LLM. Has personality, streams text, handles affect/emotion, dispatches tasks.
- **Back Actor**: Task-executing LLM. No personality, no user-facing text, JSON-only structured I/O, tool-focused ReAct agent.

The package also provides the **parallel worker pool** (BackPool), **topic-based routing** (BackTopicRouter), and **dependency-ordered dispatch queue** (ReadyQueue) that orchestrate concurrent Back task execution.

---

## 2. File-by-File Analysis

---

### 2.1 `__init__.py` (90 lines) — Package Facade

**Purpose**: Re-exports all public API from submodules. Serves as the single import surface for the actors subsystem.

**Exports organized by Epic**:
- **Epic 6.1-6.6 (Front)**: `front_handler`, `_extract_scenario_data`, `_parse_payload`, `_build_resolution`, `subscribe_front_events`, `emit_task_cancel`, `emit_task_resume`
- **Epic 7.1-7.4 (Back)**: `back_handler`, `back_resume_handler`, `back_cancel_handler`, `route_back_envelope`, `subscribe_back_events` (deprecated M3), `emit_tool_started`, `emit_tool_completed`, `emit_artifact_created`, `store_pending_context`, `_budget_to_iterations`, `_filter_back_tools`, `_summarize_args`, `_summarize_result`
- **E3.5 (Shared)**: `parse_envelope_payload`, `safe_get_section`, `never_cancel`

**Deprecation note**: `subscribe_back_events` is deprecated as of M3 E3.1.5, scheduled for removal in M8.

---

### 2.2 `shared.py` (60 lines) — Shared Actor Utilities

**Purpose**: Dependency-minimal utility functions extracted from front.py and back.py (M3 E3.5) to eliminate duplication. Three functions from Duplication Inventory items D1, D2, D3.

**Design constraint**: Only imports `json`, `typing`, `k1.bus.envelope`. No imports from actors.front, actors.back, config, or bus.builders.

**Functions**:

| Function | Signature | Purpose |
|---|---|---|
| `parse_envelope_payload` | `(envelope: Envelope) -> dict[str, Any]` | Safely parse JSON bytes from Envelope.payload. Returns `{}` on empty/invalid. |
| `safe_get_section` | `(ss: Any, name: str) -> Any` | Safely call `ss.get_section(name)`, returning `None` on any exception. |
| `never_cancel` | `async () -> bool` | Always returns `False`. Default cancellation check for non-cancellable paths (Front). |

**Cross-component imports**: `k1.bus.envelope.Envelope` only.

---

### 2.3 `front.py` (~1,250 lines) — Front Handler (Epic 6.1-6.6)

**Purpose**: The Front Actor entry point. Invoked by the FSM when an event targets the conversational LLM. Handles mode-driven prompt assembly, ReAct loop execution, and bus event emission for responses and task dispatches.

#### Identity Contract
Front is the **conversationalist**. Has personality, affect-awareness, streams text to user, dispatches tasks to Back. Front NEVER executes tools directly for task work — it only uses front-specific tools (recall_memory, dispatch_task, etc.).

#### Core Function: `front_handler`

```python
async def front_handler(
    envelope: Envelope,
    model: IModelHubPort,
    ss: Any,
    bus: IBus,
    tool_dispatcher: ToolDispatcher,
    all_tool_schemas: list[Any] | None = None,
    fsm_state: str | None = None,
    opp_pipeline: Any | None = None,
) -> ReactResult
```

**10-step flow**:
1. **Guard**: Skip observability-only topics (`turn.started`, `turn.completed`, `tool.started`, `tool.completed`, `state.updated`) to prevent infinite loops
2. **Resolve FSM state**: Explicit override or from `ss.control.flow_state`
3. **Determine mode**: `determine_mode()` using FSM state, envelope topic, clarification state, task state, affect, routing metadata
4. **Compute affect band**: `compute_affect_band()` from `affective_now` section
5. **Extract domain**: From Phase 1 classification via `control.domain_context`
6. **Build scenario data**: Mode-specific payload extraction via `_extract_scenario_data()`
7. **Build chat history**: Via `build_chat_history()` with mode-specific window size; appends current-turn user text
8. **Assemble prompt**: `DynamicPromptBuilder.build()` with OPP-6/7 enrichment (episodic compression + dynamic identity)
9. **Run ReAct loop**: With streaming callbacks, OPP-3 affect hard caps
10. **Post-loop emission**: Cancel dispatches first (URGENT) → Normal task dispatches → Final response (correct FSM ordering)
11. **HITL auto-resume**: If mode is `HITL_RESOLVE`, auto-emit `task.resume` for suspended tasks

#### Supporting Functions

| Function | Signature | Purpose |
|---|---|---|
| `_extract_scenario_data` | `(mode: PromptMode, envelope: Envelope, ss: Any) -> dict[str, Any]` | Mode-specific payload extraction. Handles PRESENT, WEAVE, HITL_RELAY, HITL_RESOLVE, ERROR, CANCEL, CLARIFY_ASK, STANDARD, INTERRUPT modes. |
| `_extract_family_context` | `(ss: Any) -> dict[str, Any]` | Build family context (members, preferences, rules) from persona section for STANDARD/INTERRUPT modes. |
| `_build_resolution` | `(scenario_data: dict) -> dict[str, Any]` | Build resolution dict from HITL_RESOLVE scenario data (M06 POC; structured parsing in M09). |
| `_strip_leaked_reasoning` | `(text: str) -> str` | Remove chain-of-thought reasoning leaked by non-thinking models (e.g. gemini-2.5-flash-lite). |
| `_strip_leaked_system_blocks` | `(text: str) -> str` | Remove raw HIL/system blocks leaked into response text by HITL_RELAY mode. |
| `_parse_routing_metadata` | `(envelope: Envelope) -> dict \| None` | Extract `routing_metadata` from enriched envelope payload (M5 E5.3.3). |
| `_extract_current_user_text` | `(mode: PromptMode, envelope: Envelope) -> str` | Extract current-turn user text from envelope payload (distinct from history). |
| `_get_affect_dict` | `(ss: Any) -> dict` | Get affect state from `affective_now` section. |
| `_build_emotional_context` | `(affect_dict: dict) -> str` | Build emotional context string for WEAVE mode based on valence/band (crisis, negative, positive, neutral). |
| `_get_clarification_state` | `(ss: Any) -> dict` | Build clarification state dict (open_gaps, blocking_gaps, depth). |
| `_get_task_state_dict` | `(ss: Any) -> dict` | Build task state dict from task_state section. |
| `_get_fsm_state` | `(ss: Any) -> str` | Get FSM flow_state from control section. |
| `_get_history_active` | `(ss: Any) -> list` | Get typed history entries for `build_chat_history`. |
| `_emit_streaming_response` | `async (bus, text, trace_id, parent_id) -> None` | Emit text as sentence-level stream chunks before final response (Epic 4.2). |
| `subscribe_front_events` | `(bus: IBus, handler_fn) -> list` | Subscribe to all Front-relevant bus topics from `FRONT_SUBSCRIPTIONS`. |
| `emit_task_cancel` | `(bus, task_id, reason, parent_id, trace_id) -> Envelope` | Emit `task.cancel.v1` (Epic 6.3.4). |
| `emit_task_resume` | `(bus, task_id, user_answer, resolution, parent_id, trace_id) -> Envelope` | Emit `task.resume.v1` (Epic 6.3.5). |

#### Cross-Component Imports

| Import | Source |
|---|---|
| `Envelope` | `k1.bus.envelope` |
| `IBus` | `k1.bus.ports.bus` |
| `IModelHubPort` | `k1.model_hub.ports` |
| `build_final_response`, `build_response_stream`, `build_task_cancel`, `build_task_dispatch`, `build_task_resume`, `SYNTHETIC_ID_START` | `k1.concierge.bus.builders` |
| `get_config` | `k1.concierge.config` |
| `ModelMessage` | `k1.concierge.llm.types` |
| `LLMOutputValidator` | `k1.concierge.llm.validator` |
| `compute_affect_band` | `k1.concierge.prompt.affect` |
| `DynamicPromptBuilder`, `SS_READ_CONFIGS`, `SECTION_RENDERERS`, `SSReadConfig` | `k1.concierge.prompt.builder` |
| `PromptMode`, `determine_mode` | `k1.concierge.prompt.mode` |
| `ReactResult`, `react_loop` | `k1.concierge.react.loop` |
| `build_chat_history` | `k1.concierge.react.history` |
| `ComplexityTier`, `budget_for_tier` | `k1.concierge.task.complexity` |
| `ToolDispatcher` | `k1.concierge.tools.dispatcher` |

#### Concurrency/Thread-Safety
- Front uses `_never_cancel` as its cancellation check — Front is never cancellable.
- Single-threaded async: one `front_handler` invocation per FSM cycle.
- Stream callbacks are closures capturing `_stream_chunk_idx` (mutation-safe within single async task).

#### Error Handling
- `safe_get_section` wraps all SS access with exception swallowing (returns None).
- `parse_envelope_payload` returns `{}` on JSON decode errors.
- `_strip_leaked_reasoning` and `_strip_leaked_system_blocks` return original text if stripping fails.
- OPP pipeline failures caught and logged (non-fatal).

#### Key Invariants
1. **Emission ordering**: Cancel dispatches → Normal task dispatches → Final response (prevents FSM IllegalTransitionError).
2. **Observability topic guard**: Observability topics never trigger LLM calls (prevents infinite loops).
3. **Synthetic envelope parent_id**: Synthetic envelopes (e.g. weave batch) fall back to `envelope.parent_id` to avoid timing chain deadlocks.
4. **No duplicate user turns**: Current user text only appended if not already the last message.

---

### 2.4 `back.py` (~1,380 lines) — Back Handler (Epic 7.1-7.4)

**Purpose**: The Back Actor entry point. Invoked by the FSM when a `task.dispatch` event targets the executor LLM. Handles task-focused ReAct loop execution with tier-based tool selection and budget management.

#### Identity Contract (V2 Section 4.2)
Back is the **executor**. Precise, tool-focused, no personality. Back NEVER talks to the user directly. It NEVER streams text. It only consumes and produces structured JSON payloads. Back NEVER writes SessionState directly — all mutations flow as structured deltas via the K1 Bus.

#### SS Read Contract (V3 E0.1.6)
- **Snapshot-at-start**: SS is read ONCE via `_read_ss_snapshot()` at handler entry. The snapshot is immutable for the duration of the ReAct loop.
- **No mid-loop re-reads**: Back MUST NOT access the live SS manager during ReAct iterations.
- **Re-read on resume**: `back_resume_handler` re-reads SS at resume time to capture state changes during suspension.

#### Core Functions

##### `back_handler`
```python
async def back_handler(
    envelope: Envelope,
    model: IModelHubPort,
    ss: Any,
    bus: IBus,
    tool_dispatcher: ToolDispatcher,
    fsm_state: Any | None = None,
    cancel_token: CancellationToken | None = None,
) -> ReactResult
```

**7-step flow**:
1. Read SS snapshot ONCE at task start via `_read_ss_snapshot()`
2. Build system prompt via `build_back_prompt()` with task context + SS snapshot
3. Build messages: N-entry history + task JSON as "user" message
4. Select tools by tier via `_filter_back_tools()`
5. Build cancellation callback from per-task CancellationToken (M3 E3.2)
6. Run ReAct loop with tier-based budget
7. Emit result to bus (task.complete / task.suspended / task.failed)

##### `back_resume_handler`
```python
async def back_resume_handler(
    envelope: Envelope,
    model: IModelHubPort,
    ss: Any,
    bus: IBus,
    tool_dispatcher: ToolDispatcher,
    fsm_state: Any | None = None,
    cancel_token: CancellationToken | None = None,
) -> ReactResult
```

**10-step resume flow**:
1. Retrieve original task + prior ReAct messages from envelope-carried `resume_context` (primary) or legacy `_get_pending_context` (fallback, deprecated)
2. Re-read SS (may have changed during suspension)
3. Build system prompt (same as original dispatch, fresh SS)
4. Hydrate resolution into messages
5. Calculate remaining budget (original - tools already called, floor of 2)
6. Select tools by tier
7. Build cancellation callback
8. Continue ReAct loop
9. Emit result (same as back_handler)
10. Clean up pending context

##### `back_cancel_handler`
```python
def back_cancel_handler(
    envelope: Envelope,
    fsm_state: Any | None = None,
    cancel_token: CancellationToken | None = None,
) -> None
```

**Synchronous** (no pool worker needed). Sets `CancellationToken.cancel(USER_REQUESTED)`. Falls back to legacy `fsm_state.cancellation_requested` boolean.

##### `route_back_envelope`
```python
async def route_back_envelope(
    envelope: Envelope,
    model: IConciergeModelPort,
    ss: Any,
    bus: IBus,
    tool_dispatcher: ToolDispatcher,
    fsm_state: Any | None = None,
    cancel_token: CancellationToken | None = None,
) -> ReactResult | None
```

Central topic-based dispatcher. Routing table:
| Topic | Handler | Notes |
|---|---|---|
| `task.dispatch.v1` | `back_handler` | Async |
| `task.resume.v1` | `back_resume_handler` | Async |
| `task.cancel.v1` | `back_cancel_handler` | Sync, returns None |
| `clarification.response.v1` | `back_resume_handler` | Async |
| Unknown | Dead-lettered | M3 E3.7.1 |

#### Supporting Functions

| Function | Signature | Purpose |
|---|---|---|
| `_budget_to_iterations` | `(budget_hint: int) -> int` | Map budget_hint to max_iterations. Floor from config. |
| `_filter_back_tools` | `(tier: str) -> list` | Filter tool schemas by tier allowlist. LOW=3 tools, MEDIUM/HIGH=6 tools. |
| `_summarize_args` | `(args: dict, max_len: int \| None) -> str` | Summarize tool args for observability, masking sensitive fields. |
| `_summarize_result` | `(result: dict, max_len: int \| None) -> str` | Summarize tool result for observability, truncating to max_len. |
| `_extract_tool_history` | `(result: ReactResult) -> list[dict]` | Extract tool call summary from ReactResult.dispatched_tasks. |
| `_status_to_error_code` | `(status: str) -> str` | Map result status to error_code string. |
| `_read_ss_snapshot` | `(ss: Any) -> dict[str, Any]` | Read selective SS snapshot (beliefs, scoreboard, task_state, task_artifacts, control, history, persona). Uses `SECTION_RENDERERS` for consistent formatting. |
| `_serialize_messages` | `(messages: list[ModelMessage]) -> list[dict]` | Serialize messages for resume context (M3 E3.3.4). |
| `_deserialize_messages` | `(data: list[dict]) -> list[ModelMessage]` | Reconstruct messages from serialized dicts. |
| `_emit_back_result` | `(bus, envelope, task_id, result, react_history, original_task) -> None` | Emit bus event based on ReactResult status (complete→task.complete, suspended→task.suspended, cancelled/budget_exhausted→task.failed). |
| `_extract_cancel_token` | `(fsm_state, task_id) -> CancellationToken \| None` | Extract per-task CancellationToken from FSM's CancellationHandler. |
| `_build_cancellation_check` | `(cancel_token, fsm_state) -> async Callable` | Build cancellation callback. Prefers token, falls back to legacy boolean, falls back to `_never_cancel` with warning. |
| `_get_pending_context` | `(fsm_state, task_id) -> dict \| None` | **Deprecated M3 E3.3.3**: Legacy resume context retrieval. |
| `_clear_pending_context` | `(fsm_state, task_id) -> None` | **Deprecated M3 E3.3.3**: Legacy resume context cleanup. |
| `store_pending_context` | `(fsm_state, task_id, original_task, prior_messages) -> None` | **Deprecated M3 E3.3.3**: Legacy suspend context storage. |
| `subscribe_back_events` | `(bus, handler_fn) -> list` | **Deprecated M3 E3.1.5**: Subscribe to Back bus topics. |
| `emit_tool_started` | `(bus, task_id, tool_name, args, parent_id) -> Envelope` | Emit `tool.started.v1` (Epic 7.3.1). |
| `emit_tool_completed` | `(bus, task_id, tool_name, result, duration_ms, success, parent_id) -> Envelope` | Emit `tool.completed.v1` (Epic 7.3.2). |
| `emit_artifact_created` | `(bus, task_id, artifact_type, data, parent_id) -> Envelope` | Emit `artifact.created.v1` (Epic 7.3.6). |
| `_noop_text` | `async (text: str) -> None` | No-op text callback. Back never emits text to user. |

#### SS Sections Read by Back

| Section | What's Read | NOT Read |
|---|---|---|
| `beliefs_active` | User facts, constraints, preferences | |
| `scoreboard` | Referent resolution (pronouns) | |
| `task_state` | Dependency info, active tasks | |
| `task_artifacts` | What has been done (avoid re-doing) | |
| `control` | Safety band only | |
| `history_active` | 5 recent entries | |
| `persona` | Payment, dietary, accessibility | |
| | | `affective_now` (Back has no personality) |
| | | `clarifications` (Front's concern) |
| | | `narrative_active` (Thread tracking is Front's job) |
| | | `meta` (Irrelevant to task execution) |

#### Cross-Component Imports

| Import | Source |
|---|---|
| `Envelope` | `k1.bus.envelope` |
| `IBus` | `k1.bus.ports.bus` |
| `IModelHubPort` | `k1.model_hub.ports` |
| `build_artifact_created`, `build_task_complete`, `build_task_failed`, `build_task_suspended`, `build_tool_completed`, `build_tool_started`, `build_dead_letter` | `k1.concierge.bus.builders` |
| `get_config` | `k1.concierge.config` |
| `ModelMessage` | `k1.concierge.llm.types` |
| `LLMOutputValidator` | `k1.concierge.llm.validator` |
| `build_back_prompt` | `k1.concierge.prompt.back_prompt` |
| `SECTION_RENDERERS`, `SSReadConfig` | `k1.concierge.prompt.builder` |
| `CancellationToken`, `CancelReason` | `k1.concierge.protocols.cancellation` |
| `build_chat_history_for_back` | `k1.concierge.react.history` |
| `ReactResult`, `react_loop` | `k1.concierge.react.loop` |
| `ToolDispatcher` | `k1.concierge.tools.dispatcher` |
| `BACK_TIER_ALLOWLISTS`, `BACK_TOOL_SCHEMAS` | `k1.concierge.tools.schemas_back` |
| Bus topic constants | `k1.concierge.bus.topics` |

#### Concurrency/Thread-Safety
- Per-task `CancellationToken` for cooperative cancellation (M3 E3.2). Token checked between ReAct iterations.
- `back_cancel_handler` is synchronous — no pool worker needed.
- M5 E5.5.4: `fsm_state.register_running_task_messages(task_id, messages)` registers the messages list for inter-iteration injection (modify-inflight).

#### Error Handling
- `_emit_back_result`: Maps all terminal states to bus events (complete, suspended, cancelled, budget_exhausted).
- Resume handler emits `task.failed` with `NO_PENDING_CONTEXT` if no resume context is available.
- Dead-lettering for unknown topics (M3 E3.7.1).
- `_build_cancellation_check` warns when no token available (Back loop will not be interruptible).

#### Key Invariants
1. **Snapshot-at-start**: SS read ONCE, never re-read during ReAct loop.
2. **Re-read on resume**: Fresh SS snapshot at resume time.
3. **Back never emits user text**: `_noop_text` callback enforces this.
4. **Back never writes SS**: All mutations flow as bus events.
5. **Tier-based tool filtering**: LOW=3 tools, MEDIUM/HIGH=6 tools.
6. **Budget accounting on resume**: `remaining_budget = original - tools_called`, floor of 2.

#### Constants
- `BACK_MAX_ITERATIONS`: `{"LOW": 4, "MEDIUM": 8, "HIGH": 12}` (compatibility export).

---

### 2.5 `back_pool.py` (~810 lines) — BackPool Worker Management (M7 E7.1)

**Purpose**: Replaces the single-worker Back execution model with a parallel pool where each task gets an isolated worker slot. Enforces `pool_size` and `max_concurrent_per_session` limits.

#### Classes

##### `BackPoolConfig` (dataclass)

```python
@dataclass
class BackPoolConfig:
    pool_size: int = 3
    max_concurrent_per_session: int = 2
    lease_ttl_s: float = 300.0          # 5 minutes
    reclaim_check_interval_s: float = 30.0
    enable_dependency_ordering: bool = True
    max_renewals: int = 3
    lease_grace_period_s: float = 5.0
```

Validates all values in `__post_init__` (pool_size >= 1, max_concurrent >= 1, ttl > 0, etc.).

##### `WorkerSlot` (dataclass)

```python
@dataclass
class WorkerSlot:
    task_id: str
    worker_id: str            # uuid4
    created_at: int           # monotonic_ns
    session_id: str | None
    async_task: asyncio.Task | None
    lease: TaskLease | None   # E7.2
```

Methods:
- `bind_task(task: asyncio.Task, lease: Any = None)` — Bind asyncio.Task and optional lease
- `is_running: bool` (property) — Whether the bound asyncio.Task is still running

##### `BackPoolExhausted(Exception)`

Raised when all worker slots are occupied. Contains `pool_size`, `active_count`, `reason`.

##### `SessionLimitReached(BackPoolExhausted)`

Raised when per-session concurrency limit is hit. Contains `session_id`, `session_count`, `max_per_session`.

##### `BackPool`

Main worker pool manager. Designed for **single-threaded asyncio** usage (same event loop as coordinator consumer).

**Worker Lifecycle Methods**:

| Method | Signature | Purpose |
|---|---|---|
| `acquire_worker` | `(task_id, *, session_id, cancellation_token) -> WorkerSlot` | Acquire a worker slot. Checks pool_size + per-session limits. Idempotent guard (returns existing if task already has worker). Creates `TaskLease`. Warns at >80% utilization. |
| `release_worker` | `(task_id, *, reason) -> WorkerSlot \| None` | Release worker slot. Updates lease status. Tracks released task_ids for late-envelope discard. Reasons: completed, cancelled, lease_expired, suspended, error. |
| `get_active_workers` | `() -> list[WorkerSlot]` | All active slots (auto-cleans done workers). |
| `get_worker_for_task` | `(task_id) -> WorkerSlot \| None` | Look up specific task's worker. |

**Pool State Queries**:
- `active_count: int`, `pool_available: int`, `utilization: float`
- `session_count(session_id) -> int`
- `has_worker(task_id) -> bool`
- `is_task_released(task_id) -> bool` — For late-envelope discard (E7.3.4)

**Lease Management (E7.2)**:

| Method | Signature | Purpose |
|---|---|---|
| `get_lease` | `(task_id) -> TaskLease \| None` | Get lease for a task. |
| `renew_lease` | `(task_id, extension_s=60.0) -> bool` | Renew lease (called between ReAct iterations). |
| `get_expired_leases` | `() -> list[WorkerSlot]` | Find all expired leases. |
| `start_lease_watcher` | `async (bus) -> asyncio.Task` | Start background lease expiry watcher. |
| `stop_lease_watcher` | `async () -> None` | Stop the watcher. |

**Lease Expiry Reclamation** (`_reclaim_expired_worker`):
1. Cancel CancellationToken (cooperative, `CancelReason.TIMEOUT`)
2. Wait grace period for react_loop to exit
3. Hard-cancel asyncio.Task if still running (`asyncio.wait_for` + `task.cancel()`)
4. Release worker slot
5. Emit `task.failed` with reason `lease_expired`

**Overflow Queue** (for pool-exhausted envelopes):

| Method | Purpose |
|---|---|
| `enqueue_overflow(envelope)` | Push to FIFO overflow queue. |
| `dequeue_overflow() -> Any \| None` | Pop next. |
| `overflow_depth: int` | Queue depth. |
| `drain_overflow() -> list` | Drain all. |

**Observability**:
- `get_pool_state() -> dict` — Full snapshot: active, size, available, utilization, overflow, per-worker details (task_id, worker_id, session_id, is_running, lease_status, remaining_s, renewed_count)
- Callbacks: `on_worker_acquired(slot)`, `on_worker_released(slot, reason)`
- `_cleanup_done_workers()` — Defensive auto-release of workers whose asyncio.Task completed without explicit release

#### Cross-Component Imports

| Import | Source |
|---|---|
| `TaskLease`, `create_task_lease` | `k1.concierge.protocols.task_lease` (deferred/TYPE_CHECKING) |
| `CancelReason` | `k1.concierge.protocols.cancellation` (deferred in method) |
| `build_task_failed` | `k1.concierge.bus.builders` (deferred in method) |

#### Concurrency/Thread-Safety
- Single-threaded asyncio design. All methods run on the same event loop as the coordinator consumer.
- Each worker's react_loop runs in its own `asyncio.Task` with its own SS snapshot. Workers do NOT share mutable state.
- Lease watcher runs as a background `asyncio.Task` with proper cancellation handling.
- Grace period mechanism: cooperative cancel → wait → hard kill.

#### Key Invariants
1. **Pool size enforced**: `acquire_worker` raises `BackPoolExhausted` if full.
2. **Per-session limit enforced**: `acquire_worker` raises `SessionLimitReached` if session cap hit.
3. **Workers do NOT share mutable state**: Each gets its own SS snapshot.
4. **FSM + TaskBridge are single writer**: Workers only READ SS and EMIT events.
5. **Idempotent acquire**: If task already has worker, returns existing slot.
6. **Late-envelope tracking**: Released task_ids tracked for BackTopicRouter discard.

---

### 2.6 `back_router.py` (~230 lines) — Back Mailbox Topic Router (M7 E7.3)

**Purpose**: Routes incoming Back-bound envelopes to the correct handler based on `envelope.topic`. Integrates with BackPool for cancel dispatch, late-envelope discard, and CancellationToken extraction.

#### Class: `BackTopicRouter`

```python
class BackTopicRouter:
    def __init__(self, back_pool: BackPool | None = None)
```

**Routing Table** (built in `__init__` from bus topic constants):

| Topic | Handler | Pool Worker Needed |
|---|---|---|
| `task.dispatch.v1` | `back_handler` | Yes (async) |
| `task.resume.v1` | `back_resume_handler` | Yes (async) |
| `task.cancel.v1` | `back_cancel_handler` | No (sync) |
| `clarification.response.v1` | `back_resume_handler` | Yes (async) |

**Methods**:

| Method | Signature | Purpose |
|---|---|---|
| `route` | `(envelope) -> Callable \| None` | Route envelope to handler. Returns None to discard (unknown topic or late arrival). |
| `is_cancel_topic` | `(topic: str) -> bool` | Check if topic bypasses pool (synchronous dispatch). |
| `get_cancel_token_for_task` | `(task_id: str) -> CancellationToken \| None` | Extract CancellationToken from task's lease (E7.3.3). |
| `get_stats` | `() -> dict[str, int]` | Routing statistics: routed, cancel_sync, discarded_late, discarded_unknown. |

**Late-Envelope Discard Logic** (`_should_discard`, E7.3.4):
- Checks `BackPool.is_task_released(task_id)` for non-cancel envelopes
- Cancel envelopes are NEVER discarded (they stop running tasks)
- Prevents: task.complete arriving after cancel; stale task.resume for completed tasks

#### Cross-Component Imports

| Import | Source |
|---|---|
| `BackPool` | `k1.concierge.actors.back_pool` (TYPE_CHECKING) |
| `back_handler`, `back_resume_handler`, `back_cancel_handler` | `k1.concierge.actors.back` (deferred in `__init__`) |
| `TOPIC_*` constants | `k1.concierge.bus.topics` (deferred in `__init__`) |

#### Key Invariants
1. **Cancel is synchronous**: No pool worker needed, immediate cooperative termination.
2. **Late-arriving envelopes discarded**: Prevents wasted worker slots on completed/cancelled tasks.
3. **Cancel envelopes never discarded**: They are how we stop things.
4. **Single CancellationToken source**: Extracted from TaskLease (E7.3.3 unification).

---

### 2.7 `ready_queue.py` (~440 lines) — Dependency-Ordered Ready Queue (M7 E7.4)

**Purpose**: Holds Back-bound envelopes with `depends_on` until the dependency task completes. Envelopes without `depends_on` are immediately ready. Polled by the coordinator's consumer loop each cycle.

**Distinct from** `task/dependency_queue.py`: TaskDependencyQueue operates on TaskDispatch objects and performs `$ref` parameter hydration. ReadyQueue operates at the envelope/pool layer and controls when Back workers are acquired.

#### Class: `ReadyQueue` (dataclass)

```python
@dataclass
class ReadyQueue:
    _ready: list[Any]                           # FIFO ready queue
    _waiting: dict[str, list[tuple[Any, str]]]  # depends_on -> [(envelope, task_id)]
    _completed: dict[str, str]                  # task_id -> status
    _known_tasks: set[str]                      # All seen task_ids
    _dep_graph: dict[str, str]                  # task_id -> depends_on
    _stats: dict[str, int]                      # Counters
```

**Methods**:

| Method | Signature | Purpose |
|---|---|---|
| `register_task` | `(task_id: str) -> None` | Register a task_id as known (dispatched). |
| `enqueue` | `(envelope, depends_on: str \| None) -> tuple[str, list[str]]` | Enqueue envelope with optional dependency. Returns (status, failed_task_ids). |
| `dequeue_ready` | `() -> list` | Drain all ready envelopes in FIFO order. |
| `notify_completed` | `(task_id, status) -> tuple[list, list[str]]` | Notify task completion. Releases dependents (if completed) or fails them (if failed/cancelled). |
| `_has_cycle` | `(task_id, depends_on) -> bool` | Cycle detection via graph walk. |
| `_remove_cycle_participants` | `(task_id, depends_on) -> list[str]` | Remove all cycle participants from waiting queue. |

**Enqueue Classification** (return statuses):
- `immediate` — No dependency, placed in ready queue
- `waiting` — Buffered, waiting for depends_on
- `dep_failed` — Dependency already failed/cancelled
- `circular` — Cycle detected, all participants failed
- `unknown_dep` — depends_on not recognized, placed in ready queue immediately (with warning)

**State Queries**:
- `ready_count`, `waiting_count`, `total_pending`
- `is_task_completed(task_id)`, `get_task_status(task_id)`
- `get_stats() -> dict[str, int]`
- `get_queue_state() -> dict` — Full snapshot with waiting details

#### Cross-Component Imports
- `json`, `logging` only. No external k1 imports. Pure data structure.

#### Concurrency/Thread-Safety
- Single-threaded design (same event loop as coordinator consumer).
- All state is internal dataclass fields.

#### Error Handling
- **Circular dependencies**: Detected at enqueue time via graph walk. All cycle participants are failed.
- **Unknown dependencies**: Dispatched immediately with warning (prevents silent stalls).
- **Failed predecessor propagation**: Dependents auto-fail when predecessor fails/cancels.

#### Key Invariants
1. **FIFO ordering**: Ready envelopes dispatched in enqueue order.
2. **Circular dependency prevention**: Detected at enqueue, all participants failed.
3. **Unknown dependency = immediate dispatch**: Prevents silent deadlocks.
4. **Failed predecessor cascading**: Dependents of failed tasks are auto-failed.
5. **Completion tracking**: Once a task is in `_completed`, its status is permanent.

---

## 3. Actor Model Architecture Summary

### Front/Back Separation

```
User Input
    │
    ▼
┌──────────┐   mode resolution    ┌────────────────────┐
│  FSM     │ ─────────────────►   │  front_handler     │
│          │                      │  (conversational)  │
└──────────┘                      │  - personality     │
                                  │  - affect-aware    │
                                  │  - streams text    │
                                  │  - dispatches tasks│
                                  └─────┬──────────────┘
                                        │ task.dispatch.v1
                                        ▼
                              ┌─────────────────────┐
                              │  BackTopicRouter     │
                              │  (topic routing)     │
                              └────────┬────────────┘
                                       │
                              ┌────────▼────────────┐
                              │  BackPool            │
                              │  (worker management) │
                              │  pool_size=3         │
                              │  per_session_max=2   │
                              └────────┬────────────┘
                                       │
                              ┌────────▼────────────┐
                              │  ReadyQueue          │
                              │  (dependency order)  │
                              └────────┬────────────┘
                                       │
                              ┌────────▼────────────┐
                              │  back_handler        │
                              │  (executor)          │
                              │  - no personality    │
                              │  - JSON-only I/O     │
                              │  - tool-focused      │
                              │  - tier-budgeted     │
                              └──────────────────────┘
```

### Message Passing / Queue Mechanisms

1. **Bus (IBus)**: All inter-actor communication via K1 Bus Envelopes. Envelope.payload is JSON bytes.
2. **BackPool overflow queue**: FIFO queue for envelopes when pool is exhausted.
3. **ReadyQueue**: Dependency-ordered FIFO queue for Back-bound envelopes.
4. **Bus builders**: All envelope construction via `k1.concierge.bus.builders` (type-safe factories).
5. **Streaming**: Front emits `response.stream.v1` chunks via bus (sentence-level chunking).

### Cancellation Architecture

```
User Cancel Request
    │
    ▼
FSM emits task.cancel.v1
    │
    ▼
BackTopicRouter (synchronous, no pool worker)
    │
    ▼
back_cancel_handler
    │
    ▼
CancellationToken.cancel(USER_REQUESTED)
    │
    ▼
react_loop checks token.is_cancelled between iterations
    │
    ▼
Cooperative exit → task.failed emitted
```

Additional cancel paths:
- **Lease expiry**: Watcher detects expired lease → cooperative cancel → grace period → hard kill
- **HITL timeout**: CancellationToken propagated from FSM cancel handler through TaskLease

---

## 4. Configuration Dependencies

The actors subsystem reads from `get_config()`:
- `config.actors.front.default_fsm_state` — Default FSM state
- `config.actors.front.default_affect_confidence` — Default affect confidence
- `config.actors.front.default_tier` — Default complexity tier
- `config.actors.front.history_window_fallback` — Fallback history window size
- `config.actors.back.budget_floor` — Minimum budget floor
- `config.actors.back.max_iterations` — Dict[str, int] for tier→iterations mapping
- `config.actors.back.history_window` — Back history window size
- `config.actors.back.hitl_timeout_s` — HITL timeout duration
- `config.actors.back.default_safety_band` — Default safety band
- `config.actors.back.summarize_args_max_len` — Max length for arg summaries
- `config.actors.back.summarize_result_max_len` — Max length for result summaries
- `config.actors.back.sensitive_keys` — Keys to mask in observability

---

## 5. Deprecation Inventory

| Item | Deprecated Since | Removal Target | Replacement |
|---|---|---|---|
| `subscribe_back_events` | M3 E3.1.5 | M8 | `route_back_envelope` / `BackTopicRouter` |
| `store_pending_context` | M3 E3.3.3 | M8 | `SuspensionManager` (envelope-carried resume_context) |
| `_get_pending_context` | M3 E3.3.3 | M8 | `SuspensionManager.pop_context` |
| `_clear_pending_context` | M3 E3.3.3 | M8 | `SuspensionManager.cleanup_task` |

---

## 6. Cross-Component Dependency Map

### External (outside k1.concierge)
- `k1.bus.envelope.Envelope` — Message envelope type
- `k1.bus.ports.bus.IBus` — Bus port interface
- `k1.model_hub.ports.IModelHubPort` — LLM model port interface

### Internal (k1.concierge subpackages)
- `bus.builders` — Envelope factory functions (10+ builders)
- `bus.topics` — Topic constants + subscription lists
- `config` — `get_config()` for all actor configuration
- `llm.types` — `ModelMessage` dataclass
- `llm.validator` — `LLMOutputValidator` for output validation
- `prompt.affect` — `compute_affect_band()`
- `prompt.builder` — `DynamicPromptBuilder`, `SS_READ_CONFIGS`, `SECTION_RENDERERS`
- `prompt.mode` — `PromptMode`, `determine_mode()`
- `prompt.back_prompt` — `build_back_prompt()`
- `protocols.cancellation` — `CancellationToken`, `CancelReason`
- `protocols.task_lease` — `TaskLease`, `create_task_lease`
- `react.loop` — `ReactResult`, `react_loop()`
- `react.history` — `build_chat_history()`, `build_chat_history_for_back()`
- `task.complexity` — `ComplexityTier`, `budget_for_tier()`
- `tools.dispatcher` — `ToolDispatcher`
- `tools.schemas_back` — `BACK_TIER_ALLOWLISTS`, `BACK_TOOL_SCHEMAS`

---

## 7. Key Design Patterns

1. **Actor Model (Front/Back split)**: Conversational personality separated from task execution. Clear identity contracts.
2. **Snapshot-at-start**: Back reads SS once and uses an immutable snapshot for the entire ReAct loop. No concurrent SS mutation risk.
3. **Cooperative cancellation**: Per-task CancellationToken checked between ReAct iterations. Graceful degradation with legacy boolean fallback.
4. **Topic-based routing**: BackTopicRouter replaces manual dispatch, with late-envelope discard for race condition prevention.
5. **Pool + lease management**: Fixed-size worker pool with TTL-based leases, automatic reclamation (cooperative → grace → hard kill).
6. **Dependency ordering**: ReadyQueue with cycle detection prevents deadlocks and cascading failures.
7. **Bus-mediated communication**: All inter-component communication via typed bus envelopes. No direct method calls between actors.
8. **Reasoning-leak stripping**: Front sanitizes LLM output to remove chain-of-thought and system block leakage before user delivery.
9. **Emission ordering**: Front emits cancels → dispatches → final response to prevent FSM transition errors.
10. **Dead-lettering**: Unknown topics are dead-lettered instead of silently dropped.
