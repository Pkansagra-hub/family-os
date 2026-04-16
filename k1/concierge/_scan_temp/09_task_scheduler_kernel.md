# 09 — Task, Scheduler, and Kernel Subsystems

> Scanned: 17 Python files across `k1/concierge/task/`, `k1/concierge/scheduler/`, `k1/concierge/kernel/`

---

## A. TASK SUBSYSTEM (`k1/concierge/task/`) — 12 files

The task subsystem is the **canonical data-model and dispatch machinery** for Front→Back task orchestration. It defines all bus payloads, intent classification, complexity budgeting, dependency resolution, parallel-safety rules, envelope bridging, and the tool schema exposed to the LLM.

---

### A.1 `task/__init__.py` — Package Public API

**Purpose:** Re-exports all public symbols from the 11 sub-modules. Serves as the single import surface for the task subsystem.

**Design Refs:** V2 Sections 8.2, 8.4, 8.5, 11.2.1

**Bus Topic Family (documented in docstring):**
| Topic | Direction | Purpose |
|---|---|---|
| `k1.orchestration.task.dispatch.v1` | Front → Back | New task dispatch |
| `k1.orchestration.task.complete.v1` | Back → Front | Success result |
| `k1.orchestration.task.failed.v1` | Back → Front | Error path |
| `k1.orchestration.task.suspended.v1` | Back → Front | HITL path |
| `k1.orchestration.task.cancel.v1` | Front → Back | Cancel |
| `k1.orchestration.task.resume.v1` | Front → Back | Resume after HITL |

**Exported symbols (by Epic):**
- **Epic 10.1 — Complexity:** `ComplexityTier`, `TIER_BUDGET`, `budget_for_tier`
- **Epic 10.2 — Intent:** `TaskIntent`
- **Epic 10.3 — Dispatch payloads:** `TaskDispatch`, `TaskComplete`, `TaskFailed`
- **Epic 10.4 — Topics:** `TASK_DISPATCH`, `TASK_COMPLETE`, `TASK_FAILED`, `TASK_CANCEL`, `TASK_SUSPENDED`, `TASK_RESUME`, `TASK_ACCEPTED`, `ORCHESTRATION_DELTA`, `DAG_COMPLETED`, `ALL_TASK_TOPICS`
- **Epic 10.4 — Envelope bridge:** `dispatch_to_envelope`, `complete_to_envelope`, `failed_to_envelope`
- **Epic 10.5 — Classifier:** `IntentClassification`, `classify_intents`, `build_dispatches`
- **Epic 10.6 — Dependency queue:** `TaskDependencyQueue`
- **Epic 10.7 — dispatch_task tool:** `dispatch_task`, `DISPATCH_TASK_SCHEMA`
- **Epic 10.8 — Receiver:** `TaskReceiver`
- **Epic 10.9 — Bundled executor:** `IntentResult`, `BundledExecutionPlan`
- **Epic 10.14 — Parallel safety:** `PARALLEL_SAFE_GROUPS`, `ALWAYS_SEQUENTIAL`, `is_parallel_safe`, `classify_tool_batch`

**Cross-component imports:** All internal — no external k1.bus/k1.fabric imports at this level.

---

### A.2 `task/intent.py` — TaskIntent Dataclass

**Purpose:** Immutable (`frozen=True`) dataclass representing a single discrete action for the Back actor.

**Class: `TaskIntent`**
- Base: `@dataclass(frozen=True)`
- **Attributes:**
  - `action: str` — what to do (natural language or capability name). **Required, non-empty.**
  - `params: dict[str, Any]` — structured parameters. May contain `$ref` placeholders (e.g. `"$prev.result.address"`) for chained tasks.
  - `domain: str | None` — optional domain hint (travel, health, productivity, etc.)
  - `urgency: str` — `"normal"` (default), `"urgent"`, `"background"`. Maps to bus Priority.

**Key Methods:**
| Method | Signature | Purpose |
|---|---|---|
| `__post_init__` | `() -> None` | Validates action non-empty, urgency in valid set |
| `has_refs` | `() -> bool` | True if any param value starts with `$` |
| `ref_targets` | `() -> list[str]` | Extracts task IDs from `$ref` values (e.g. `"$task-003.result.address"` → `"task-003"`) |
| `to_dict` | `() -> dict[str, Any]` | Minimal serialization (omits defaults) |
| `from_dict` | `(cls, data) -> TaskIntent` | Deserialize from dict |

**Validation:** `_VALID_URGENCIES = frozenset({"normal", "urgent", "background"})` — raises `ValueError` on invalid.

**Cross-component imports:** None (stdlib only).

---

### A.3 `task/complexity.py` — ComplexityTier and Budget

**Purpose:** Enum for task complexity (LOW/MEDIUM/HIGH) and budget mapping that constrains the Back ReAct loop iteration count.

**Class: `ComplexityTier(str, Enum)`**
- Values: `LOW = "LOW"`, `MEDIUM = "MEDIUM"`, `HIGH = "HIGH"`

**Constants:**
```
TIER_BUDGET: dict[ComplexityTier, int] = {
    LOW: 6,    # discover + invoke + 2 fetches + submit
    MEDIUM: 10, # multi-intent bundles
    HIGH: 14,  # chained workflows with intermediate lookups
}
```

**Function: `budget_for_tier(tier: ComplexityTier) -> int`**
- Reads from central config (`get_config().task.tier_budget`) first.
- Falls back to module-level `TIER_BUDGET` if config key missing.

**Cross-component imports:**
- `k1.concierge.config.get_config` — central configuration system

---

### A.4 `task/dispatch.py` — TaskDispatch, TaskComplete, TaskFailed

**Purpose:** The three canonical bus payloads for task orchestration. All support JSON round-trip serialization via `to_dict`/`from_dict` and `to_payload`/`from_payload` (bytes).

#### Class: `TaskDispatch` (Front → Back)
- Base: `@dataclass`
- **Attributes:**
  - `intents: list[TaskIntent]` — **non-empty** (validated in `__post_init__`)
  - `tier: ComplexityTier` — default `LOW`
  - `task_id: str` — auto-generated `"task-{uuid.uuid4().hex[:8]}"`
  - `budget_hint: int | None` — auto-computed from tier if not set
  - `reference_context: dict[str, str] | None` — pronoun mappings from Front
  - `safety_band: str` — `GREEN` / `AMBER` / `RED` (default `AMBER`)
  - `depends_on: str | None` — parent task ID for chained tasks
  - `context_snapshot: dict[str, Any] | None` — SS sections at dispatch time

- **Validation (`__post_init__`):**
  - `intents` must be non-empty
  - `budget_hint` auto-set from `budget_for_tier(tier)` if None
  - `depends_on` must start with `"task-"` if provided
  - `safety_band` must be in `{"GREEN", "AMBER", "RED"}`

- **Properties:** `is_bundled` (len > 1), `is_chained` (depends_on set), `has_refs` (any intent has $ref)

- **Serialization:** `to_dict()`, `from_dict()`, `to_payload()` (JSON bytes), `from_payload()` (JSON bytes)

#### Class: `TaskComplete` (Back → Front, success)
- **Attributes:**
  - `task_id: str`
  - `final_answer: str` — technical summary, NOT user-facing (Front rewrites in its voice)
  - `results: list[dict[str, Any]]` — structured data for presenter
  - `artifacts_created: list[dict[str, Any]]` — durable outputs persisted in task_artifacts
  - `completed_before_cancel: bool` — race condition flag for cancel vs complete
  - `tool_calls: int` — budget tracking

- **Serialization:** `to_dict()`, `from_dict()`, `to_payload()`, `from_payload()`

#### Class: `TaskFailed` (Back → Front, error)
- **Attributes:**
  - `task_id: str`
  - `reason: str` — validated against `_VALID_FAILURE_REASONS`
  - `error_code: str | None`
  - `tool_history: list[dict[str, Any]]` — tool calls before failure
  - `partial_results: list[dict[str, Any]]`
  - `retries_attempted: int` — max 1 retry per capability
  - `last_error_detail: str | None` — never shown raw to user

- **Valid failure reasons:**
  ```
  budget_exhausted, cancelled, capability_not_found, capability_failed,
  workflow_failed, agent_failed, timeout, internal_error
  ```

**Cross-component imports:**
- `k1.concierge.task.complexity` — `ComplexityTier`, `budget_for_tier`
- `k1.concierge.task.intent` — `TaskIntent`

---

### A.5 `task/classifier.py` — Intent Classification and Dispatch Building

**Purpose:** Classifies intent lists into SINGLE/BUNDLED/CHAINED and builds the appropriate `TaskDispatch`(es).

**Class: `IntentClassification(str, Enum)`**
- `SINGLE = "single"` — one intent, one dispatch
- `BUNDLED = "bundled"` — multiple independent intents, one dispatch
- `CHAINED = "chained"` — multiple dependent intents, separate dispatches with `depends_on`

**Function: `classify_intents(intents: list[TaskIntent]) -> IntentClassification`**
- Rules:
  - 0–1 intents → `SINGLE`
  - 2+ intents, none have `$ref` params → `BUNDLED`
  - 2+ intents, any has `$ref` params → `CHAINED`

**Function: `build_dispatches(...) -> list[TaskDispatch]`**
```python
def build_dispatches(
    intents: list[TaskIntent],
    classification: IntentClassification,
    tier: ComplexityTier = ComplexityTier.MEDIUM,
    reference_context: dict[str, str] | None = None,
    safety_band: str = "AMBER",
    context_snapshot: dict[str, Any] | None = None,
) -> list[TaskDispatch]
```
- **SINGLE/BUNDLED:** Returns 1 `TaskDispatch` with all intents
- **CHAINED:** Returns N `TaskDispatch`es, each with 1 intent, linked via `depends_on` forming a sequential chain. Only the first dispatch gets `context_snapshot` and `reference_context` (per V2 Section 8.5).

**Cross-component imports:**
- `k1.concierge.task.complexity` — `ComplexityTier`
- `k1.concierge.task.dispatch` — `TaskDispatch`
- `k1.concierge.task.intent` — `TaskIntent`

---

### A.6 `task/bundled_executor.py` — BundledExecutionPlan

**Purpose:** Tracks sequential execution of multiple intents within a bundled dispatch in the Back ReAct loop. Single-intent dispatches also use this (degenerates to one step).

#### Class: `IntentResult`
- Base: `@dataclass`
- **Attributes:** `intent_index: int`, `action: str`, `status: str` (`"success"` or `"error"`), `data: dict`, `error: str | None`, `tool_calls_used: int`
- Validates `status` in `__post_init__`

#### Class: `BundledExecutionPlan`
- Base: `@dataclass`
- **Attributes:** `intents: list[TaskIntent]`, `results: list[IntentResult]`, `_current_index: int`
- **Properties:**
  - `current_intent` — next intent to execute (or None)
  - `current_index`, `is_complete`, `total_intents`, `completed_intents`
  - `total_tool_calls` — sum across all intents
  - `all_success`, `has_errors`
- **Key Methods:**
  - `record_result(result)` — validates index match, advances cursor. Raises `RuntimeError` if already complete, `ValueError` if index mismatch.
  - `combined_result() -> dict` — produces `{"intent_results": [...], "all_success": bool, "total_tool_calls": N, ...}` for `submit_result`
  - `results_as_list() -> list[dict]` — success-only data dicts for `TaskComplete.results`

**Cross-component imports:**
- `k1.concierge.task.intent` — `TaskIntent`

---

### A.7 `task/dependency_queue.py` — TaskDependencyQueue

**Purpose:** Holds chained tasks until their dependency completes, then hydrates `$ref` placeholders and releases them.

**Design note:** Lives in the orchestrator/FSM layer, NOT in Back. Back is a stateless ReAct actor receiving pre-hydrated dispatches.

#### Class: `TaskDependencyQueue`
- Base: `@dataclass`
- **Attributes:**
  - `pending: dict[str, list[TaskDispatch]]` — `depends_on task_id → waiting dispatches`
  - `completed_results: dict[str, TaskComplete]` — stored for $ref resolution
  - `_execute: Callable[[TaskDispatch], None] | None` — release callback

**Key Methods:**
| Method | Signature | Purpose |
|---|---|---|
| `set_execute_callback` | `(fn) -> None` | Set callback for released tasks |
| `enqueue` | `(dispatch) -> bool` | Buffer if dep pending (True), hydrate+return if dep already complete (False). Raises `ValueError` if `depends_on` is None |
| `on_task_complete` | `(complete) -> list[TaskDispatch]` | Stores result, hydrates waiting tasks, returns released list, fires execute callback |
| `_hydrate_dispatch` | `(dispatch, parent) -> None` | Replaces `$ref` placeholders in all intent params. **Mutates in-place** (dict mutation on frozen dataclass field) |
| `_resolve_ref` | `(ref, parent) -> Any` | Resolves `$prev.result.field.subfield` or `$task-XXX.result.field` against `parent.results[0]`. Raises `KeyError` on missing path. Returns original string if pattern doesn't match (graceful degradation) |
| `waiting_count` | `@property -> int` | Total pending tasks |
| `completed_count` | `@property -> int` | Stored results count |
| `clear` | `() -> None` | Clear all state |

**$ref Pattern:** `_REF_PATTERN = re.compile(r"^\$(?:prev|[a-zA-Z0-9_-]+)\.result\.(.+)$")`
- `$prev.result.field` → `parent.results[0]["field"]`
- `$prev.result.field.subfield` → `parent.results[0]["field"]["subfield"]`
- `$task-XXX.result.field` → `parent.results[0]["field"]` (explicit ID form)

**Hydration failure:** If `_resolve_path` returns None (field not found via KeyError), the raw `$ref` string is left in params. Back will call `submit_result(needs_human, clarification)` for the missing value — graceful degradation.

**Cross-component imports:**
- `k1.concierge.task.dispatch` — `TaskComplete`, `TaskDispatch`

---

### A.8 `task/envelope_bridge.py` — K0↔K1 Envelope Translation

**Purpose:** Bridges between task dataclasses and bus envelope dicts. POC uses lightweight dict-based envelopes mirroring canonical fields. Production would use FlatBuffers.

**Urgency → Priority mapping:**
| Urgency | Priority value | Priority name |
|---|---|---|
| `"urgent"` | 0 | URGENT |
| `"normal"` | 2 | INTERACTIVE |
| `"background"` | 3 | BACKGROUND |

**Functions:**
| Function | Signature | Topic | Priority |
|---|---|---|---|
| `dispatch_to_envelope` | `(dispatch, session_id, request_id, cognitive_trace_id, parent_envelope_id=0) -> dict` | `TASK_DISPATCH` | Resolved from highest-urgency intent |
| `complete_to_envelope` | `(complete, session_id, request_id, cognitive_trace_id, parent_envelope_id=0) -> dict` | `TASK_COMPLETE` | INTERACTIVE (2) |
| `failed_to_envelope` | `(failed, session_id, request_id, cognitive_trace_id, parent_envelope_id=0) -> dict` | `TASK_FAILED` | INTERACTIVE (2) |

**Priority resolution for dispatch (`_resolve_dispatch_priority`):**
- If ANY intent is `"urgent"` → URGENT (0)
- If any intent is `"background"` and rest are `"normal"` → BACKGROUND (3)
- Default → INTERACTIVE (2)

**Envelope fields produced:** `topic`, `priority`, `cognitive_trace_id`, `session_id`, `request_id`, `parent_id`, `payload` (JSON bytes), `payload_format` (1 = JSON)

**Note:** Bus stamps `envelope_id`, `sequence`, `created_ns` at publish time via `Envelope.with_bus_fields()` — not set here.

**Cross-component imports:**
- `k1.concierge.task.dispatch` — `TaskComplete`, `TaskDispatch`, `TaskFailed`
- `k1.concierge.task.topics` — `TASK_COMPLETE`, `TASK_DISPATCH`, `TASK_FAILED`

---

### A.9 `task/tools.py` — dispatch_task Front Control Tool

**Purpose:** The LLM-callable tool that the Front ReAct loop uses to dispatch tasks to Back. This is a **SEQUENTIAL** tool (depends on cognitive state being up to date).

**Function: `dispatch_task`**
```python
async def dispatch_task(
    intents_raw: list[dict[str, Any]],
    tier: str = "MEDIUM",
    reference_context: dict[str, str] | None = None,
    urgency: str = "normal",
    depends_on: str | None = None,
    context_snapshot: dict[str, Any] | None = None,
    safety_band: str = "AMBER",
    publish_fn: Callable[[TaskDispatch], Awaitable[None]] | None = None,
) -> dict[str, Any]
```

**Flow:**
1. Parses `intents_raw` dicts into `TaskIntent` objects (applies dispatch-level urgency to intents without explicit urgency)
2. Classifies intents via `classify_intents()`
3. If `depends_on` provided, overrides classification to `CHAINED`
4. Builds dispatches via `build_dispatches()`
5. For explicit `depends_on`, rebuilds first dispatch with the external dependency
6. Publishes each dispatch via `publish_fn` (injected by tool registry / FSM)
7. Returns observation: `{"dispatched": [...task_ids], "classification": "single"|"bundled"|"chained", "count": N}`

**Constant: `DISPATCH_TASK_SCHEMA`**
- OpenAI function-calling schema for LLM system prompt injection
- Parameters: `intents` (array, required), `urgency`, `reference_context`, `depends_on`
- Each intent: `action` (required string), `params` (object), `domain` (string)
- Description explicitly guides LLM: "Do NOT call for pure conversation, emotional support, or clarification"

**Cross-component imports:**
- `k1.concierge.task.classifier` — `IntentClassification`, `build_dispatches`, `classify_intents`
- `k1.concierge.task.complexity` — `ComplexityTier`
- `k1.concierge.task.dispatch` — `TaskDispatch`
- `k1.concierge.task.intent` — `TaskIntent`

---

### A.10 `task/receiver.py` — TaskReceiver

**Purpose:** Back-side actor that receives task dispatches from the bus, routes them through dependency resolution, and manages task state transitions.

**Task State Machine:**
```
DISPATCHED → IN_PROGRESS → COMPLETED | FAILED
```

#### Class: `TaskReceiver`
- **Slots:** `dependency_queue`, `execute_fn`, `_active_tasks`, `_completed_count`, `_failed_count`, `_results`
- Uses `__slots__` for memory efficiency

**Key Methods:**
| Method | Signature | Purpose |
|---|---|---|
| `set_execute_fn` | `(fn: Callable[[TaskDispatch], Awaitable[TaskComplete]]) -> None` | Wire the ReAct loop entry point |
| `handle` | `async (dispatch: TaskDispatch) -> None` | Route incoming dispatch: immediate exec or dep queue |
| `_execute_and_complete` | `async (dispatch: TaskDispatch) -> None` | Execute, handle success/failure, notify dep queue, recursively execute released chained tasks |

**Routing logic in `handle()`:**
- `depends_on is None` → execute immediately
- `depends_on is set`, dep already complete → hydrate and execute immediately (enqueue returns False)
- `depends_on is set`, dep pending → buffer in dependency queue (enqueue returns True)

**Failure handling in `_execute_and_complete()`:**
- On success: stores `TaskComplete`, notifies dep queue
- On exception: wraps in `TaskFailed(reason="internal_error")`, stores it
- On failure with chained waiters: creates **synthetic `TaskComplete`** with `{"_parent_failed": True, "reason": ...}` so chained tasks can detect parent failure via `$ref` resolution
- Released chained tasks are executed **recursively** via `_execute_and_complete()`

**Telemetry properties:** `active_count`, `waiting_count` (delegates to dep queue)

**Cross-component imports:**
- `k1.concierge.task.dependency_queue` — `TaskDependencyQueue`
- `k1.concierge.task.dispatch` — `TaskComplete`, `TaskDispatch`, `TaskFailed`

---

### A.11 `task/parallel_safety.py` — Tool Parallelism Classification

**Purpose:** Classifies tools into parallel-safe vs sequential groups for the ReAct loop's `asyncio.gather` optimization.

**Integration:** `react_loop` calls `classify_tool_batch()` before execution. Config toggle `react.parallel_tools_enabled` can force all sequential.

**Constants:**
```python
PARALLEL_SAFE_GROUPS = {
    "reads": {"recall_memory", "summarize_context", "discover_capabilities"},
    "cognitive_writes": {"update_beliefs", "update_scoreboard", "update_clarifications",
                         "update_narrative", "refine_affect"},
}

ALWAYS_SEQUENTIAL = {
    "promote_belief",     # depends on recall_memory observation
    "dispatch_task",      # depends on cognitive state being up-to-date
    "invoke_capability",  # side effects
    "spawn_via_fabric",   # side effects — creates agents
    "execute_workflow",   # side effects — orchestrates multi-step
    "submit_result",      # terminal — ends the loop
}
```

**Functions:**
| Function | Signature | Purpose |
|---|---|---|
| `is_parallel_safe` | `(tool_name: str) -> bool` | True if in any parallel-safe group. Unknown tools default to **sequential** (fail-safe) |
| `classify_tool_batch` | `(tool_names: list[str]) -> tuple[list[str], list[str]]` | Returns `(parallel_safe, sequential)` lists, preserving input order |

**Production batching strategy (V2 Section 7.8):**
1. Phase 1: parallel reads (`asyncio.gather`)
2. Phase 2: parallel cognitive writes (`asyncio.gather`)
3. Phase 3: sequential tools one at a time

**Cross-component imports:** None (stdlib only).

---

### A.12 `task/topics.py` — Bus Topic Constants

**Purpose:** Re-exports topic constants from `k1.concierge.bus.topics` (the SINGLE SOURCE OF TRUTH). Exists only for backward compatibility.

**DEPRECATION NOTICE (V3 E0.1.4):** New code should import from `k1.concierge.bus.topics` directly.

**Re-exported topics:**
```python
TASK_DISPATCH   = TOPIC_TASK_DISPATCH
TASK_COMPLETE   = TOPIC_TASK_COMPLETE
TASK_FAILED     = TOPIC_TASK_FAILED
TASK_CANCEL     = TOPIC_TASK_CANCEL
TASK_SUSPENDED  = TOPIC_TASK_SUSPENDED
TASK_RESUME     = TOPIC_TASK_RESUME
TASK_ACCEPTED   = TOPIC_TASK_ACCEPTED
ORCHESTRATION_DELTA = TOPIC_ORCHESTRATION_DELTA
DAG_COMPLETED   = TOPIC_DAG_COMPLETED
WEAVE_BATCH     = TOPIC_WEAVE_BATCH
```

**`ALL_TASK_TOPICS: frozenset[str]`** — all 10 topics for validation/iteration.

**Delivery semantics:** All `k1.orchestration` topics use `DeliveryMode.STRICT`:
- Causal ordering via `parent_id`
- Sequence gap buffering
- Timeout safety net (5s default)

**Cross-component imports:**
- `k1.concierge.bus.topics` — all `TOPIC_*` constants

---

## B. SCHEDULER SUBSYSTEM (`k1/concierge/scheduler/`) — 2 files

---

### B.1 `scheduler/__init__.py`

**Purpose:** Empty init file. No exports.

---

### B.2 `scheduler/proactive_scheduler.py` — ProactiveScheduler (OPP-5)

**Purpose:** Generalized kernel primitive that decides **WHEN** to trigger proactive messages during user idle periods. Separates scheduling logic from content generation.

**Architecture chain:**
```
ProactiveScheduler (WHEN) → ProactiveAgent (WHAT) → Bus PROACTIVE_FILL (HOW) → FSM → Front
```

#### Class: `ProactiveTriggerType(str, Enum)`
- `WAIT_STATUS` — "still working on it"
- `PROGRESS_UPDATE` — task progress report
- `CONTEXT_TIP` — contextual suggestion
- `IDLE_CHECK_IN` — "anything else?"

#### Class: `ProactiveSchedulerConfig`
- Base: `@dataclass`
- **Attributes:**
  - `idle_threshold_ms: int = 5000` — minimum idle before first trigger
  - `cooldown_ms: int = 15000` — minimum between triggers
  - `max_per_session: int = 10` — cap per session
  - `suppress_on_affect: list[str] | None` — defaults to `["crisis", "low"]`
  - `suppress_on_hitl: bool = True` — suppress during pending HITL
  - `enabled: bool = True` — master switch

#### Class: `ProactiveTrigger`
- Base: `@dataclass`
- **Attributes:** `trigger_type`, `reason`, `context: dict[str, str]`, `scheduled_at_ns: int`

#### Class: `ProactiveScheduler`
- Uses `__slots__`: `_config`, `_trigger_count`, `_last_trigger_ns`, `_suppressed_count`, `_session_start_ns`
- Thread safety: single event loop, no locks

**Key Method: `evaluate()`**
```python
def evaluate(
    self,
    idle_ms: int,
    affect_band: str = "neutral",
    has_pending_hitl: bool = False,
    has_inflight_tasks: bool = False,
    inflight_task_count: int = 0,
) -> ProactiveTrigger | None
```

**Suppression cascade (checked in order):**
1. `enabled` is False → None
2. `trigger_count >= max_per_session` → None
3. `idle_ms < idle_threshold_ms` → None
4. HITL pending and `suppress_on_hitl` → None (suppressed_count++)
5. `affect_band` in suppress list → None (suppressed_count++)
6. Cooldown not elapsed → None

**Trigger type selection (`_select_trigger_type`):**
| Condition | Trigger Type | Reason |
|---|---|---|
| Inflight tasks, idle > 15s | `PROGRESS_UPDATE` | `"long_wait_with_tasks"` |
| Inflight tasks, idle ≤ 15s | `WAIT_STATUS` | `"waiting_for_tasks"` |
| No tasks, idle > 30s | `IDLE_CHECK_IN` | `"extended_idle"` |
| No tasks, idle ≤ 30s | `CONTEXT_TIP` | `"moderate_idle"` |

**Telemetry:** `trigger_count`, `suppressed_count` properties.

**`reset()`** — clears all counters and timestamps (for session restart).

**Cross-component imports:** None (stdlib only: `logging`, `time`, `dataclasses`, `enum`).

---

## C. KERNEL SUBSYSTEM (`k1/concierge/kernel/`) — 3 files

---

### C.1 `kernel/__init__.py` — Package Exports

**Exports:** `KernelConfig`, `KernelRuntime`, `start_kernel`, `stop_kernel`

---

### C.2 `kernel/bootstrap.py` — Full Kernel Assembly

**Purpose:** The master wiring file that assembles ALL concierge components into a running system. This is the **single point of truth** for how components connect.

**Design boundary:** Intentionally avoids importing from `poc.k1_poc.demo` to keep a clean system ↔ demo boundary.

**Environment:** Auto-loads `.env` for `GOOGLE_API_KEY` via `python-dotenv`. Searches project-root `.env` first, then `poc/chat_experience_poc/.env` as fallback.

#### Class: `KernelConfig`
- Base: `@dataclass`
- **Attributes:**
  - `ordered_bus: bool = True`
  - `capture_bus: bool = False`
  - `test_mode: bool = False`
  - `tool_tier: str = "LOW"`
  - `session_mode: str = "standalone"` (standalone | testing)
  - `session_id: str | None = None`
  - `enable_experience: bool = True`
  - `enable_delta: bool = True`
  - `enable_hitl: bool = True`
  - `enable_orchestrator: bool = True`
  - `auto_start_consumer: bool = True`
  - `enable_ledger: bool = True` (M1 E1.4.1)
  - `enable_dead_letter_consumer: bool = True` (M2 E2.5.1)
  - `seed_memories: list[dict[str, Any]]` — injected memories for recall

#### Class: `KernelRuntime`
- Base: `@dataclass`
- **Attributes (all live references):**
  - `config`, `bus: IBus`, `router: IMailboxRouter`, `adapter`
  - `front_mailbox: IMailbox`, `back_mailbox: IMailbox`
  - `session_state`, `capability_registry`, `model`
  - `fsm: ConciergeController`
  - `front_dispatcher`, `back_dispatcher`
  - `experience_layer`, `delta_aggregator`, `delta_applicator`
  - `hitl_coordinator`, `orchestrator`
  - `front_subscriptions`, `back_subscriptions`
  - `consumer_task: asyncio.Task | None`
  - `ledger`, `ledger_store` (M1 E1.4.1)
  - `dead_letter_consumer` (M2 E2.5.1)
  - `started: bool`

#### Function: `start_kernel(config=None) -> KernelRuntime`

**Assembly order (critical wiring sequence):**

1. **Infrastructure boot** — calls `poc.k1_poc.main.boot()` for bus, router, adapter, mailboxes
2. **Model creation** — `_create_model(cfg)`:
   - test_mode → `TestModelHubBridge`
   - GOOGLE_API_KEY set → `ModelHubPOCBridge(GeminiConciergeAdapter)`
   - fallback → `TestModelHubBridge`
3. **Session state** — `_create_session_state(cfg)` via `SessionStateFactory.create_standalone()` or `.create_for_testing()`
4. **Capability registry** — `_create_capability_registry()` via `create_demo_registry()`
5. **Fabric (M6 E6.3)** — `_create_fabric(registry)`:
   - Creates `POCMockBridgeAdapter(registry)`
   - Uses `FabricFactory.create_with_ports()` with test adapters for all ports except bridge
   - Registers all 40 POC capability contracts via `convert_all_poc_capabilities()`
   - Re-runs `_auto_register_providers` for provider config
6. **Ledger (M1 E1.4.1)** — `InMemoryLedgerStore` + `LedgerWriter` if enabled
7. **FSM** — `ConciergeController(bus=bus, router=router)`
8. **Phase 1 pipeline (M10 E10.4.2)** — config-driven UltraBERT adapter if available, else STUB
9. **Ledger wiring** — `fsm.set_ledger(ledger_writer)`
10. **FSM history sink** — wires FSM history to SS `history_active` section
11. **FSM session state** — `fsm.set_session_state(session_state)`
12. **Tool contexts** — creates `ToolContext` for front and back with:
    - `session_manager`, `cognitive_trace_id`, `actor`, `recall_fn`, `fabric_port`, `writer_port`
13. **Tool dispatchers** — `create_front_dispatcher(tier, ctx, bus)`, `create_back_dispatcher(tier, ctx, bus)`
14. **KernelRuntime assembly** — all components into dataclass
15. **ExperienceLayer** — `ExperienceLayer()` if enabled
16. **Delta system** — `DeltaAggregator(flush_fn=applicator.apply)` + `DeltaApplicator` if enabled
17. **HITL (Human-in-the-Loop)** — `HILCoordinator` with bus envelope callbacks:
    - `_on_suspended` → `build_task_suspended` → `bus.publish`
    - `_on_resume` → `build_task_resume` → `bus.publish`
    - `_on_timeout` → `build_task_failed` → `bus.publish`
    - Wired into FSM via `fsm.set_hitl_coordinator()`
18. **WeaveBatcher** — wired into FSM for Front-busy queue management
19. **WeavePolicy + UserActivityTracker (M8 E8.5)** — adaptive delivery
20. **DeadLetterConsumer (M2 E2.5.1)** — attached to bus if config enables
21. **Orchestrator** — `OrchestratorStub` with:
    - `_FabricGatewayAdapter(fabric)` — translates POC ↔ K1 capability types
    - `_StateReadAdapter(session_state)` — snapshot/read_section
    - `_DeltaEmitAdapter(aggregator, bus)` — delta emission
    - Wired into FSM via `fsm.set_orchestrator()`
22. **Bus subscriptions** — Front events subscribed via `subscribe_front_events(bus, route_fn)`
    - **Back subscriptions deliberately empty** — FSM is the sole routing authority for back-bound topics (task.dispatch, task.cancel, task.resume, clarification.response). Direct subscription would cause duplicate deliveries.
23. **Mailbox consumer** — `asyncio.create_task(_mailbox_consumer(runtime))`

#### Function: `stop_kernel(runtime) -> None`

**Shutdown order:**
1. Cancel consumer task
2. Flush ledger (log entry count)
3. Log dead-letter summary
4. Flush delta aggregator
5. FSM teardown
6. Session state close
7. Model close
8. Set `started = False`

#### Function: `_mailbox_consumer(runtime) -> None`

**Polling loop:**
- Polls `front_mailbox` and `back_mailbox` with `timeout_ms=0`
- **Deduplication:** `seen_front_ids` / `seen_back_ids` sets, cleared at configurable `dedup_cache_size`
- Front envelope → `front_handler(...)` → `_tick_experience(runtime)`
- Back envelope → `route_back_envelope(...)` (M3 E3.1.3 topic router)
- Sleep: `0` if did work, `poll_interval` if idle (from config)

#### Function: `_tick_experience(runtime) -> None`

**Experience layer integration:**
1. Builds context from SS sections (`_build_experience_context`)
2. Calls `layer.tick(fsm_state, context)`
3. Emotional output → `build_affect_update` → bus publish
4. Tone output → writes to `affective_now._tone_adjustment`
5. ResponseStyle from RhythmController → writes to `affective_now._response_style`
6. Fill output → `build_proactive_fill` → bus publish

#### Function: `_build_experience_context(runtime) -> dict`

**Context snapshot contents:**
- `turn_transcript` — last user message from FSM history
- `affect_history` — from `affective_now.recent_emotions`
- `front_refine_affect_confidence` — from affective_now source
- `conversation_history` — from `history_active.get_typed_entries(10)`
- `user_cadence` — inter-message timing from user entries (avg_gap_ms, last_gap_ms, sample_count)
- `task_state`, `persona`, `wait_duration_ms`, `memory_recalls`, `user_patterns`

#### Helper: `_build_recall_fn(cfg) -> async Callable`

**In-memory keyword recall:**
- Tokenizes query, expands with synonyms and day-of-week mapping
- Scores seed memories by tag + content word overlap
- Synonym groups: `{agenda, schedule, calendar, ...}`, `{todo, tasks, chores, ...}`, etc.
- Returns top N scored results

#### Helper Classes (Adapter Pattern):

**`_FabricGatewayAdapter`** — Translates POC orchestrator `CapabilityRequest` → K1 `CapabilityRequest` → bridge → K1 `CapabilityResult` → POC `CapabilityResult`

**`_StateReadAdapter`** — `snapshot(sections)` and `read_section(session_id, section)` against session state

**`_build_delta_applicator`** — Creates `DeltaApplicator` with:
- `_preflight` — MutationGuard check if available
- `_write` — section-level set/update operations
- `_notify` — bus publish on `STATE_UPDATED`

---

### C.3 `kernel/runner.py` — CLI Entry Point

**Purpose:** One-command standalone kernel startup via `python -m k1.concierge.kernel.runner`.

**CLI arguments:**
| Arg | Type | Default | Purpose |
|---|---|---|---|
| `--test-mode` | flag | False | Use test adapter |
| `--unordered` | flag | False | Disable ordered bus |
| `--session-mode` | choice | `"standalone"` | `standalone` or `testing` |
| `--tool-tier` | choice | `"LOW"` | `LOW` / `MEDIUM` / `HIGH` / `CRISIS` |
| `--log-level` | choice | `"INFO"` | Logging level |

**Lifecycle:**
1. Parse args → configure logging
2. Create `KernelConfig` from args
3. `await start_kernel(cfg)`
4. Print "Kernel started" prompt
5. Wait on `asyncio.Event` (set by SIGINT/SIGTERM handler)
6. `await stop_kernel(runtime)`
7. Print "Kernel stopped"

**Signal handling:** `signal.SIGINT` and `signal.SIGTERM` → set stop event

**Cross-component imports:**
- `k1.concierge.kernel.bootstrap` — `KernelConfig`, `start_kernel`, `stop_kernel`

---

## D. CROSS-COMPONENT IMPORT MAP

### Task subsystem external imports
| Module | External Import |
|---|---|
| `task/complexity.py` | `k1.concierge.config.get_config` |
| `task/topics.py` | `k1.concierge.bus.topics.*` |
| All others | Internal to `k1.concierge.task` only |

### Bootstrap external imports (comprehensive)
| Category | Imports |
|---|---|
| **Bus** | `k1.bus.ports.bus.IBus`, `k1.bus.ports.mailbox.IMailbox`, `k1.bus.ports.mailbox.IMailboxRouter` |
| **Actors** | `k1.concierge.actors.back.route_back_envelope`, `k1.concierge.actors.front.front_handler`, `k1.concierge.actors.front.subscribe_front_events` |
| **Bus builders** | `k1.concierge.bus.builders.build_affect_update`, `build_proactive_fill`, `build_task_failed`, `build_task_resume`, `build_task_suspended` |
| **Experience** | `k1.concierge.experience.layer.ExperienceLayer` |
| **FSM** | `k1.concierge.fsm.controller.ConciergeController` |
| **Tools** | `k1.concierge.tools.dispatcher.create_back_dispatcher`, `create_front_dispatcher` |
| **Tools impl** | `k1.concierge.tools.implementations.ToolContext` |
| **Tool schemas** | `k1.concierge.tools.schemas_front.FRONT_TOOL_SCHEMAS` |
| **Config** | `k1.concierge.config.get_config` |
| **LLM** | `k1.concierge.llm.gemini_adapter.GeminiConciergeAdapter`, `k1.concierge.llm.model_hub_bridge.ModelHubPOCBridge`, `k1.concierge.llm.test_model_hub_bridge.TestModelHubBridge` |
| **Ledger** | `k1.concierge.ledger.store.InMemoryLedgerStore`, `k1.concierge.ledger.writer.LedgerWriter` |
| **Delta** | `k1.concierge.delta.aggregator.DeltaAggregator`, `k1.concierge.delta.applicator.DeltaApplicator` |
| **HITL** | `k1.concierge.protocols.hitl_coordinator.HILCoordinator` |
| **Weave** | `k1.concierge.protocols.weave_batcher.WeaveBatcher`, `k1.concierge.protocols.weave_policy.WeavePolicy`, `UserActivityTracker` |
| **Dead letter** | `k1.concierge.fsm.dead_letter_consumer.DeadLetterConsumer` |
| **UltraBERT** | `k1.concierge.fsm.ultrabert_adapter.K1UltraBERTAdapter`, `k1.concierge.fsm.ultrabert_phase1.UltraBERTPhase1Pipeline` |
| **Orchestrator** | `k1.concierge.orchestrator.stub.OrchestratorStub`, `k1.concierge.orchestrator.types.CapabilityResult` |
| **Fabric** | `k1.concierge.fabric.capability_registry.create_demo_registry`, `k1.concierge.fabric.contract_converter.convert_all_poc_capabilities`, `k1.concierge.fabric.poc_bridge_adapter.POCMockBridgeAdapter` |
| **K1 Fabric** | `k1.fabric.adapters.*` (LocalEvent, TestDeltaBus, TestModelGateway, TestPromptSystem, TestSessionStateReader), `k1.fabric.factory.FabricFactory`, `k1.fabric.types.CapabilityRequest` |
| **SessionState** | `k1.sessionstate.factory.SessionStateFactory` |
| **POC boot** | `poc.k1_poc.main.boot` |

---

## E. ERROR HANDLING PATTERNS

### Task subsystem
| Pattern | Where | Behavior |
|---|---|---|
| `ValueError` on invalid construction | `TaskIntent.__post_init__`, `TaskDispatch.__post_init__`, `TaskFailed.__post_init__`, `IntentResult.__post_init__` | Raises immediately — invalid data never enters the system |
| `ValueError` on invalid enqueue | `TaskDependencyQueue.enqueue()` | Raises if `depends_on` is None |
| `RuntimeError` on plan overflow | `BundledExecutionPlan.record_result()` | Raises if plan already complete |
| `KeyError` on $ref resolution | `TaskDependencyQueue._resolve_ref()` | Raises if path not found in results. Graceful: raw $ref left in params if pattern doesn't match |

### Receiver
| Pattern | Where | Behavior |
|---|---|---|
| `execute_fn` not set | `_execute_and_complete()` | Logs error, drops task silently |
| `execute_fn` raises | `_execute_and_complete()` | Wraps in `TaskFailed(reason="internal_error")`, logs exception |
| Parent task failure + chained children | `_execute_and_complete()` | Synthetic `TaskComplete` with `_parent_failed` marker released to children |

### Bootstrap
| Pattern | Where | Behavior |
|---|---|---|
| `try/except pass` | SS history wiring, tone write, style write, experience tick | Non-critical failures silenced — applies next turn |
| `try/except log` | Stop kernel sequence (ledger, dead-letter, delta, FSM, SS, model) | Each shutdown step catches independently — partial cleanup preferred over crash |
| `.env` load failure | Module level | `ImportError` for dotenv silently caught |

---

## F. KEY ARCHITECTURAL OBSERVATIONS

1. **Task is pure data-model** — No bus, no async, no I/O. All 12 files define dataclasses, enums, classification logic, and safety rules. The only external dependency is `k1.concierge.config` for budget lookups.

2. **Bootstrap is the wiring authority** — `kernel/bootstrap.py` is the ONLY place where all subsystems get connected. No component self-registers; everything is explicitly wired.

3. **Back subscriptions deliberately empty** — The FSM is the sole routing authority for back-bound topics. Direct bus subscription was removed to prevent duplicate deliveries.

4. **Parallel safety is fail-safe** — Unknown tools default to sequential. Only explicitly listed tools can run in parallel.

5. **$ref hydration is graceful** — Unresolvable references are left as-is rather than crashing. Back detects these and asks for human input.

6. **Proactive scheduler is pure logic** — No bus, no async. Just evaluates conditions and returns a trigger or None. Content generation is fully delegated.

7. **Adapter pattern throughout bootstrap** — `_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter` translate between POC and K1 types. This isolates the orchestrator from knowing about K1 fabric internals.

8. **Deduplication in mailbox consumer** — `seen_front_ids` / `seen_back_ids` sets prevent duplicate processing. Sets are cleared at configurable size to bound memory.

9. **Experience layer writes directly to SS** — Tone and ResponseStyle are written to `affective_now` section properties. This is a side-channel outside the normal delta pipeline.

10. **Runner is minimal** — Just CLI parsing, signal handling, and start/stop. No business logic.
