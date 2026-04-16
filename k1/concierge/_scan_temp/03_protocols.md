# K1 Concierge — Protocols Subsystem Scan

> **Scope**: `k1/concierge/protocols/` — 20 Python files
> **Purpose**: Task lifecycle protocols for cooperative cancellation, suspension, weave batching, HITL coordination, trust accumulation, delivery strategy, OPP pipeline integration, and task leasing.

---

## Table of Contents

1. [Package Overview (`__init__.py`)](#1-package-overview)
2. [Cancellation Subsystem](#2-cancellation-subsystem)
   - 2.1 `cancellation.py` — CancellationToken & CancelReason
   - 2.2 `cancel_events.py` — Cancellation Bus Events
   - 2.3 `cancel_handler.py` — CancellationHandler (FSM-side)
3. [Suspension Subsystem](#3-suspension-subsystem)
   - 3.1 `suspension.py` — Suspension Types & Requests
   - 3.2 `suspension_events.py` — Suspension Bus Events
   - 3.3 `suspension_manager.py` — SuspensionManager (FSM-side)
4. [HITL Subsystem (Human-in-the-Loop)](#4-hitl-subsystem)
   - 4.1 `hitl.py` — Core Types (SafetyBand, HILRequest, HILResponse)
   - 4.2 `hitl_coordinator.py` — HILCoordinator
   - 4.3 `hitl_flow.py` — Flow Helpers (Clarification/Approval/Selection)
   - 4.4 `hitl_pipeline.py` — Approval & Selection Pipelines
   - 4.5 `hitl_persistence.py` — HILSubTask, TaskStateEntry, Crash Recovery
   - 4.6 `hitl_wiring.py` — Cross-layer Wiring & Validation
5. [Weave Subsystem](#5-weave-subsystem)
   - 5.1 `weave_state.py` — FSM State → WeaveAction Decision Table
   - 5.2 `weave_batcher.py` — WeaveBatcher (500ms batching)
   - 5.3 `weave_policy.py` — Adaptive WeavePolicy & Pacing
6. [Delivery Strategy (`delivery_strategy.py`)](#6-delivery-strategy)
7. [Trust Accumulator (`trust_accumulator.py`)](#7-trust-accumulator)
8. [Task Lease (`task_lease.py`)](#8-task-lease)
9. [OPP Pipeline (`opp_pipeline.py`)](#9-opp-pipeline)
10. [Cross-Component Import Map](#10-cross-component-import-map)
11. [Error Handling Patterns](#11-error-handling-patterns)
12. [Key Invariants](#12-key-invariants)

---

## 1. Package Overview

**File**: `__init__.py` (~250 lines)

The `__init__.py` is a comprehensive re-export facade. It imports and re-exports **every public symbol** from all 19 other modules, organized by Epic:

| Epic | Symbols Re-exported |
|------|---------------------|
| Epic 12.1 | `CancellationToken`, `CancelReason`, `TaskCancelledError` |
| Epic 12.2 | `TaskCancelEvent`, `TaskFailedCancelledEvent`, `CancellationHandler` |
| Epic 12.3 | `SuspensionType`, `SuspensionRequest`, `SuspensionResolution`, `SuspensionLimitExceeded`, `SuspensionTimeoutError`, `TaskSuspendedEvent`, `TaskResumeEvent`, `SuspensionManager`, `MAX_SUSPENSIONS_PER_TASK`, `MAX_CONCURRENT_SUSPENSIONS` |
| Epic 12.4 | `WeaveBatcher`, `WeaveResult`, `WEAVE_BATCH_WINDOW_MS` |
| Epic 12.5 | `WeaveAction`, `PendingResult`, `PendingResultsQueue`, `get_weave_action`, `STATE_ACTION_TABLE` |
| Epic 13.1 | `SafetyBand`, `HILRequest`, `HILResponse`, `escalate_safety_band` |
| Epic 13.2 | `HILCoordinator`, `HILCoordinatorConfig`, `HIL_TO_SUSPENSION` |
| Epic 13.3 | `HILFlowType`, `ClarificationContext`, `ApprovalContext`, `SelectionContext`, `build_clarification_request`, `build_approval_request`, `build_selection_request`, `parse_clarification_resolution`, `parse_approval_resolution`, `parse_selection_resolution` |
| Epic 13.4+13.5 | `detect_approval_required`, `apply_approval_modifications`, `process_approval_response`, `ApprovalResult`, `SelectionResult`, `resolve_selection_to_params`, `build_resume_params_from_selection` |
| Epic 13.6 | `TaskStatus`, `TaskStateEntry`, `HILTimeoutEvent`, `CrashRecoveryReport`, `scan_for_recovery`, `build_timeout_events` |
| Epic 13.7-13.9 | `ResumeContext`, `RESUME_INSTRUCTIONS`, `build_resume_context`, `HILModeConfig`, `get_hitl_relay_config`, `get_hitl_resolve_config`, `validate_hitl_wiring` |

**Design refs** in module docstring: V2 Sections 4, 5, 9 (FSM states, FSMTurnState, HITL Protocol).

---

## 2. Cancellation Subsystem

### 2.1 `cancellation.py` — CancellationToken & CancelReason

**Purpose**: Cooperative cancellation primitive. Back checks the token at tool boundaries; Front triggers cancellation via `CancellationHandler`.

**Classes**:

#### `CancelReason(str, Enum)`
```
USER_REQUESTED = "user_requested"
TIMEOUT        = "timeout"
SUPERSEDED     = "superseded"
```

#### `CancellationToken` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | The task this token governs |
| `_cancelled` | `bool` | Internal cancel flag |
| `_cancel_reason` | `CancelReason \| None` | Why cancelled |
| `_cancel_time_ns` | `int` | Monotonic timestamp of cancel |
| `completed_before_cancel` | `bool` | Task finished before check |
| `_event` | `asyncio.Event` | For `wait_for_cancel()` |

**Key Methods**:
- `cancel(reason: CancelReason) -> None` — Idempotent. Sets flag, stores time, signals event.
- `check() -> None` — Raises `TaskCancelledError` if cancelled. Called at tool boundaries.
- `wait_for_cancel(timeout: float | None) -> bool` — Async wait for cancel signal.
- Properties: `is_cancelled`, `cancel_reason`, `cancel_time_ns`

#### `TaskCancelledError(Exception)`
- Fields: `task_id: str`, `reason: CancelReason | None`
- Raised by `CancellationToken.check()` when cancelled.

**Cross-component imports**: None (self-contained primitive).

---

### 2.2 `cancel_events.py` — Cancellation Bus Events

**Purpose**: Structured bus event payloads for the cancellation lifecycle.

**Cross-component imports**:
- `k1.concierge.task.topics.TASK_FAILED` — topic constant

#### `TaskCancelEvent` (dataclass)
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `task_id` | `str` | — | Task to cancel |
| `reason` | `str` | `"user_requested"` | Cancel reason |
| `priority` | `str` | `"URGENT"` | Bus priority (always URGENT) |
| `new_task_id` | `str \| None` | `None` | Replacement task if superseded |

Methods: `to_payload() -> dict`, `from_payload(cls, data) -> TaskCancelEvent`

#### `TaskFailedCancelledEvent` (dataclass)
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `task_id` | `str` | — | Cancelled task |
| `completed_before_cancel` | `bool` | `False` | Task finished before cancel check |
| `tool_calls_completed` | `int` | `0` | Tools finished before abort |
| `error_message` | `str` | `"Task cancelled by user"` | Human-readable message |

Methods: `to_payload() -> dict`, `from_payload(cls, data) -> TaskFailedCancelledEvent`

**Cancellation Timeline** (from V2 Section 4):
```
T=0ms    User: "book Vineyard Inn for June 15-17"
T=300ms  User: "Wait, cancel that, do Marriott instead"
T=302ms  Front emits task.cancel (URGENT) + ack + new dispatch
T=305ms  Back checks cancellation_token at next tool boundary, aborts
T=310ms  Back emits task.failed(cancelled=True)
T=312ms  FSM updates task_state -> CANCELLED, transitions to DELIVERING
```

---

### 2.3 `cancel_handler.py` — CancellationHandler (FSM-side)

**Purpose**: FSM-side lifecycle management for cancellation tokens. Handles registration, cancel, dedup of late completions, and ledger-based crash recovery.

**Cross-component imports**:
- `k1.concierge.protocols.cancellation` — `CancellationToken`, `CancelReason`
- `k1.concierge.ledger.store.LedgerEntry` (TYPE_CHECKING)
- `k1.concierge.ledger.writer.LedgerWriter` (TYPE_CHECKING)
- `k1.concierge.events.task.TaskCancelled` (lazy import in cancel methods)
- `k1.concierge.ledger.projections.project_cancel_state` (lazy import in rebuild)

#### `CancellationHandler`
| Slot | Type | Description |
|------|------|-------------|
| `_tokens` | `dict[str, CancellationToken]` | Active tokens by task_id |
| `_cancelled_tasks` | `set[str]` | IDs of cancelled tasks (dedup) |
| `_on_cancel_fn` | `Callable \| None` | Async callback on cancel |
| `_ledger` | `LedgerWriter \| None` | Event sourcing writer |

**Key Methods**:
| Method | Signature | Description |
|--------|-----------|-------------|
| `set_ledger` | `(ledger: LedgerWriter) -> None` | Wire ledger after construction |
| `register_task` | `(task_id: str) -> CancellationToken` | Create + register token |
| `cancel_task` | `async (task_id, reason, ledger) -> bool` | Async cancel with callback. Write-before-mutate to ledger. |
| `request_cancel` | `(task_id, reason, ledger) -> bool` | Sync cancel (no callback). Auto-creates token if missing. |
| `confirm_cancel` | `(task_id) -> bool` | Confirm and cleanup. Returns True if expected. |
| `is_cancelled` | `(task_id) -> bool` | Check cancelled set (dedup) |
| `handle_late_completion` | `(task_id) -> bool` | Detect task.complete after cancel |
| `cleanup_task` | `(task_id) -> None` | Remove all state for task |
| `rebuild_from_events` | `(entries: list[LedgerEntry]) -> int` | Crash recovery from ledger replay |
| `reset` | `() -> None` | Clear all state |

**Write-before-mutate pattern**: Both `cancel_task` and `request_cancel` write to the ledger BEFORE mutating in-memory state (`_tokens`, `_cancelled_tasks`).

---

## 3. Suspension Subsystem

### 3.1 `suspension.py` — Suspension Types & Requests

**Purpose**: Core suspension protocol types for the HITL flow.

**Cross-component imports**:
- `k1.concierge.config.get_config` — config accessor for timeouts & limits

#### `SuspensionType(str, Enum)`
```
CLARIFICATION = "clarification"   # 60s timeout
APPROVAL      = "approval"        # 120s timeout
SELECTION     = "selection"        # 90s timeout
```

#### Constants
| Constant | Value | Note |
|----------|-------|------|
| `MAX_SUSPENSIONS_PER_TASK` | `2` | Backward-compat re-export; production uses config accessor |
| `MAX_CONCURRENT_SUSPENSIONS` | `1` | Per-task concurrency limit |

#### Config Accessors (private)
- `_get_suspension_timeouts() -> dict[SuspensionType, float]` — from `config/defaults.yaml`
- `_get_max_suspensions_per_task() -> int` — from config
- `_get_max_concurrent_suspensions() -> int` — from config

#### `SuspensionRequest` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Task being suspended |
| `suspension_type` | `SuspensionType` | Why suspended |
| `question` | `str` | Question for user |
| `options` | `list[dict]` | Structured options |
| `react_history` | `list[dict]` | Serialized ReAct history for resume |
| `tool_state` | `dict` | Tool state for resume |
| `suspension_count` | `int` | How many times suspended |
| `created_at_ns` | `int` | Monotonic timestamp |

Property: `timeout_seconds` — reads from config by type.
Methods: `to_payload()`, `from_payload(cls, data)`

#### `SuspensionResolution` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Suspended task |
| `resolution` | `Any` | User's answer |
| `resolution_type` | `str` | Answer type (selection/approval/text) |

Methods: `to_payload()`, `from_payload(cls, data)`

#### Exceptions
- **`SuspensionLimitExceeded(Exception)`**: `task_id: str`, `count: int`. Reads max from config.
- **`SuspensionTimeoutError(Exception)`**: `task_id: str`, `timeout: float`

---

### 3.2 `suspension_events.py` — Suspension Bus Events

**Purpose**: Bus event dataclasses for suspension/resume lifecycle.

**Cross-component imports**: None (no external k1 imports beyond protocols).

#### `TaskSuspendedEvent` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Suspended task |
| `suspension_type` | `str` | Why suspended |
| `question` | `str` | Question for user |
| `options` | `list[dict]` | Structured options |
| `suspension_count` | `int` | Suspension round number |

Methods: `to_payload()`, `from_payload(cls, data)`

#### `TaskResumeEvent` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Task to resume |
| `resolution` | `Any` | User's answer |
| `resolution_type` | `str` | Answer type |

Methods: `to_payload()`, `from_payload(cls, data)`

---

### 3.3 `suspension_manager.py` — SuspensionManager (FSM-side)

**Purpose**: FSM-side suspension lifecycle manager. Enforces limits, manages timeouts, stores context for resume.

**Cross-component imports**:
- `k1.concierge.protocols.suspension` — `SuspensionLimitExceeded`, `SuspensionRequest`, `SuspensionResolution`, `SuspensionType`, `_get_max_suspensions_per_task`
- `k1.concierge.ledger.store.LedgerEntry` (TYPE_CHECKING)
- `k1.concierge.ledger.writer.LedgerWriter` (TYPE_CHECKING)
- `k1.concierge.events.hitl.TaskSuspended` (lazy import)
- `k1.concierge.events.hitl.TaskResumed` (lazy import)

#### `SuspensionManager`
| Slot | Type | Description |
|------|------|-------------|
| `_active` | `dict[str, SuspensionRequest]` | Currently suspended tasks |
| `_contexts` | `dict[str, dict]` | Stored suspension contexts (sync API) |
| `_ledger` | `LedgerWriter \| None` | Event sourcing |
| `_suspension_counts` | `dict[str, int]` | Per-task suspension count |
| `_timeout_tasks` | `dict[str, asyncio.Task]` | Active timeout watchers |
| `_on_timeout_fn` | `Callable \| None` | Timeout callback |
| `_on_resume_fn` | `Callable \| None` | Resume callback |

**Key Methods**:
| Method | Signature | Description |
|--------|-----------|-------------|
| `suspend` | `async (request, ledger) -> None` | Register suspension. Validates: max 1 concurrent, max N total. Starts timeout watcher. Write-before-mutate. |
| `resolve` | `async (resolution, ledger) -> SuspensionRequest \| None` | Cancel timeout, return original request (with ReAct history). Write-before-mutate. |
| `is_suspended` | `(task_id) -> bool` | Check active |
| `get_request` | `(task_id) -> SuspensionRequest \| None` | Get active request |
| `cleanup_task` | `(task_id) -> None` | Full cleanup. Warns if leftover state. |
| `store_context` | `(task_id, context) -> None` | Sync context storage for FSM controller |
| `pop_context` | `(task_id) -> dict \| None` | Pop stored context (destructive) |
| `get_context` | `(task_id) -> dict \| None` | Non-destructive read |

**Timeout mechanism**: `_watch_timeout(task_id, timeout)` — async sleep → on expiry: pop active, invoke `_on_timeout_fn`. Cancelled if user responds first.

---

## 4. HITL Subsystem (Human-in-the-Loop)

### 4.1 `hitl.py` — Core Types

**Purpose**: Foundational HITL types: SafetyBand, HILRequest, HILResponse, escalation logic.

**Cross-component imports**:
- `k1.concierge.config.get_config` — HITL timeouts from config
- `k1.concierge.protocols.suspension.MAX_SUSPENSIONS_PER_TASK` — default max_rounds

#### `SafetyBand(str, Enum)`
```
GREEN = "GREEN"   # Safe, no side effects
AMBER = "AMBER"   # Requires user approval
RED   = "RED"     # Execution blocked entirely
```

#### `escalate_safety_band(band, has_side_effects) -> SafetyBand`
| Input | Output |
|-------|--------|
| RED + any | RED |
| GREEN + side_effects=True | AMBER |
| AMBER + any | AMBER |
| GREEN + side_effects=False | GREEN |

#### `_get_hil_timeouts() -> dict[str, float]`
Returns HITL timeouts in **seconds** from central config (V3 E0.2.1 unified to seconds).

#### `VALID_HIL_TYPES: frozenset[str]` = `{"clarification", "approval", "selection"}`

#### `HILRequest` (dataclass)
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `task_id` | `str` | — | Task being suspended |
| `hil_type` | `str` | — | clarification/approval/selection |
| `question` | `str` | — | Question for user |
| `options` | `list[dict]` | `[]` | Structured options |
| `context` | `dict` | `{}` | Additional context |
| `side_effects` | `list[str]` | `[]` | Side effects for approval |
| `safety_band` | `SafetyBand` | `GREEN` | Effective safety band |
| `timeout_ms` | `int` | `0` | Per-type timeout (auto-set from config) |
| `max_rounds` | `int` | `MAX_SUSPENSIONS_PER_TASK` | Max HITL rounds |
| `created_at_ns` | `int` | `time.monotonic_ns` | Creation timestamp |

`__post_init__`: Validates `hil_type` against `VALID_HIL_TYPES`. Sets default timeout from config if 0.

Methods: `to_payload()`, `from_payload(cls, data)`, `to_persistence()` (adds `suspended_at_ms`).
Property: `timeout_seconds -> float`

#### `HILResponse` (dataclass)
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `task_id` | `str` | — | Suspended task |
| `decision` | `str` | `"answered"` | approve/modify/cancel/answered |
| `resolution` | `dict` | `{}` | Type-specific resolution payload |
| `raw_user_text` | `str` | `""` | Original user text for audit |

Resolution formats by type:
- **clarification**: `{answer: str, resolved_params: {param: value}}`
- **approval**: `{decision: "approve"|"modify"|"cancel", modifications: {param: value}}`
- **selection**: `{selected_option: int, target: str}`

Methods: `to_payload()`, `from_payload(cls, data)`

---

### 4.2 `hitl_coordinator.py` — HILCoordinator

**Purpose**: FSM-side HITL orchestration. The central hub for the HITL closed cycle (V2 Section 9.1, 8 steps).

**Cross-component imports**:
- `k1.concierge.config.get_config` — max rounds config
- `k1.concierge.protocols.hitl` — `HILRequest`, `HILResponse`, `SafetyBand`, `_get_hil_timeouts`, `escalate_safety_band`
- `k1.concierge.protocols.suspension` — `SuspensionLimitExceeded`, `SuspensionRequest`, `SuspensionResolution`, `SuspensionType`
- `k1.concierge.protocols.suspension_manager.SuspensionManager`
- `k1.concierge.ledger.store.LedgerEntry` (TYPE_CHECKING)
- `k1.concierge.ledger.writer.LedgerWriter` (TYPE_CHECKING)
- `k1.concierge.events.hitl.HILRequested` (lazy)
- `k1.concierge.events.hitl.HILResolved` (lazy)

#### `HIL_TO_SUSPENSION: dict[str, SuspensionType]`
Maps `"clarification"` → `CLARIFICATION`, `"approval"` → `APPROVAL`, `"selection"` → `SELECTION`.

#### `HILCoordinatorConfig` (dataclass)
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_rounds` | `int` | from config | Max HITL rounds per task |
| `timeouts` | `dict[str, float]` | from config | Per-type timeouts (seconds) |
| `block_red` | `bool` | `True` | Block RED safety band |
| `auto_escalate_side_effects` | `bool` | `True` | GREEN+side_effects → AMBER |

#### `HILCoordinator`
| Slot | Type | Description |
|------|------|-------------|
| `_config` | `HILCoordinatorConfig` | Configuration |
| `_ledger` | `LedgerWriter \| None` | Event sourcing |
| `_suspension_mgr` | `SuspensionManager` | Delegates timeout management |
| `_pending_requests` | `dict[str, HILRequest]` | Active HITL requests |
| `_hil_counts` | `dict[str, int]` | Per-task HITL round counts |
| `_on_emit_suspended` | `Callable \| None` | Bus emit callback |
| `_on_emit_resume` | `Callable \| None` | Bus emit callback |
| `_on_timeout` | `Callable \| None` | Timeout callback |
| `_on_blocked_red` | `Callable \| None` | RED band callback |

**Key Methods**:

##### `handle_needs_human` (async)
```python
async def handle_needs_human(
    self, task_id, hil_type, question, options, side_effects,
    context, safety_band, react_history, ledger
) -> HILRequest
```
Flow:
1. Normalize & escalate safety band (GREEN+side_effects → AMBER)
2. Check RED → raise ValueError if `block_red=True`
3. Check suspension limits → raise `SuspensionLimitExceeded`
4. Build `HILRequest` with type-specific timeout
5. Persist to `_pending_requests`
6. Write `HILRequested` event to ledger (write-before-mutate)
7. Delegate to `SuspensionManager.suspend()`
8. Invoke `_on_emit_suspended` callback

##### `handle_user_response` (async)
```python
async def handle_user_response(
    self, task_id, decision, resolution, raw_user_text, ledger
) -> HILResponse | None
```
Flow:
1. Build `SuspensionResolution` → `SuspensionManager.resolve()` (cancels timeout)
2. Write `HILResolved` event to ledger
3. Build `HILResponse`
4. Clear `_pending_requests`
5. Invoke `_on_emit_resume` callback

##### `recover_pending_hitl` (async)
```python
async def recover_pending_hitl(
    self, task_state: dict[str, dict], now_ms: int | None
) -> list[str]
```
Scans task_state for `status=SUSPENDED` + `pending_hil`. Timed out → `_on_timeout`. Still valid → re-register.

##### `validate_before_invoke`
```python
def validate_before_invoke(
    self, task_id, capability_contract, task_history
) -> str  # "allow" | "block_needs_approval" | "block_red"
```
L2 defense-in-depth: checks `safety_band` and `has_side_effects` BEFORE capability execution. Verifies `hil_history` for prior approval.

---

### 4.3 `hitl_flow.py` — Flow Helpers

**Purpose**: Structured context builders and resolution parsers for the three HITL shapes.

**Cross-component imports**:
- `k1.concierge.protocols.hitl` — `HILRequest`, `SafetyBand`, `escalate_safety_band`

#### `HILFlowType(str, Enum)`
```
CLARIFICATION = "clarification"
APPROVAL      = "approval"
SELECTION     = "selection"
```

#### Context Builders

##### `ClarificationContext` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `capability` | `str` | Capability being invoked |
| `missing_params` | `list[str]` | Missing required params |
| `available_params` | `dict` | Already resolved params |
| `attempted_sources` | `list[str]` | Where Back looked |

Methods: `to_context() -> dict`, `build_question() -> str`

##### `ApprovalContext` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `capability` | `str` | Capability requesting approval |
| `action_summary` | `str` | What will happen |
| `side_effects` | `list[str]` | Consequences |
| `params` | `dict` | Params to be used |
| `safety_band` | `SafetyBand` | From capability contract |

Methods: `to_context() -> dict`
Property: `default_options` → `[{approve}, {modify}, {cancel}]`

##### `SelectionContext` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `capability` | `str` | Discovery capability |
| `results` | `list[dict]` | Result set to choose from |
| `selection_reason` | `str` | Why Back can't pick |
| `findings_so_far` | `list[dict]` | For resume (skip re-search) |

Methods: `to_context() -> dict`, `to_options() -> list[dict]`

#### Factory Functions
- `build_clarification_request(task_id, context, question, safety_band) -> HILRequest`
- `build_approval_request(task_id, context, question) -> HILRequest` — always escalates to AMBER
- `build_selection_request(task_id, context, question, safety_band) -> HILRequest`

#### Resolution Parsers
- `parse_clarification_resolution(raw) -> dict` — normalizes to `{answer, resolved_params}`
- `parse_approval_resolution(raw) -> dict` — normalizes to `{decision, modifications?}`
- `parse_selection_resolution(raw, available_options) -> dict` — normalizes to `{selected_option, target}` or `{selected_options}` (multi-select)

---

### 4.4 `hitl_pipeline.py` — Approval & Selection Pipelines

**Purpose**: End-to-end pipeline helpers wiring safety detection, approval merge logic, and selection resolution.

**Cross-component imports**:
- `k1.concierge.protocols.hitl` — `HILResponse`, `SafetyBand`
- `k1.concierge.protocols.hitl_flow` — `parse_approval_resolution`, `parse_selection_resolution`

#### `detect_approval_required(capability_contract: dict) -> bool`
Rules:
- `has_side_effects=True` → True
- `safety_band="AMBER"` → True
- `safety_band="RED"` → True (always blocked)
- `GREEN` + no side_effects → False
- Unknown band → defaults to AMBER (err on side of caution)

#### `apply_approval_modifications(original_params, modifications) -> dict`
Shallow merge. Original NOT mutated. **Invariant 8**: modifications applied BEFORE execution.

#### `ApprovalResult` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `decision` | `str` | approve/modify/cancel |
| `merged_params` | `dict` | Params with mods applied |
| `modifications` | `dict` | User's requested changes |
| `raw_user_text` | `str` | Audit trail |
| `should_execute` | `bool` | Whether to invoke capability |
| `should_re_present` | `bool` | Whether to re-present for approval |

#### `process_approval_response(response, original_params) -> ApprovalResult`
Decision table:
| Decision | should_execute | should_re_present |
|----------|---------------|-------------------|
| approve | True | False |
| approve + mods | True | False |
| modify + mods | False | True |
| cancel | False | False |

#### `SelectionResult` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `selected_option` | `int \| None` | Single selection |
| `selected_options` | `list[int] \| None` | Multi-select |
| `target` | `str` | Resolved label |
| `selected_data` | `dict` | Full option data |
| `raw_user_text` | `str` | Audit trail |

Properties: `is_multi_select`, `is_valid`

#### `resolve_selection_to_params(response, available_options, param_name) -> SelectionResult`
Maps selection index back to original option data.

#### `build_resume_params_from_selection(selection, original_params, param_mapping) -> dict`
Merges selected data into original params. If `param_mapping` provided, remaps keys. Always sets `_selected_target`.

---

### 4.5 `hitl_persistence.py` — HILSubTask, TaskStateEntry, Crash Recovery

**Purpose**: Persistence models for HITL lifecycle, task state, crash recovery scanning, and timeout events.

**Cross-component imports**:
- `k1.concierge.protocols.hitl` — `HILRequest`, `SafetyBand`

#### `HILSubTaskStatus(str, Enum)`
```
PENDING    = "PENDING"     # Awaiting user response
RESOLVED   = "RESOLVED"    # User answered
TIMED_OUT  = "TIMED_OUT"   # Timeout fired
CANCELLED  = "CANCELLED"   # Explicit cancel or limit exceeded
```

#### `HILSubTask` (dataclass) — M6 E6.1.1
Single source of truth wrapping HILRequest + ReAct snapshot + resume_token.

| Field | Type | Description |
|-------|------|-------------|
| `pending_hil_id` | `str` | UUID for this sub-task |
| `hil_type` | `str` | clarification/approval/selection |
| `parent_task_id` | `str` | Owning task |
| `question` | `str` | Question asked |
| `options` | `list[dict]` | Structured options |
| `side_effects` | `list[str]` | For approval |
| `safety_band` | `str` | Effective band |
| `hil_deadline` | `int` | Absolute deadline (ns) |
| `timeout_ms` | `int` | Configured timeout |
| `resume_token` | `str` | UUID4 for validating resume events |
| `react_snapshot` | `dict` | `{prior_messages, tool_history, last_iteration}` |
| `status` | `HILSubTaskStatus` | Current lifecycle status |
| `created_at_ns` | `int` | Creation timestamp |
| `resolved_at_ns` | `int` | Resolution timestamp |
| `device_id` | `str` | Originating device (M5) |
| `context` | `dict` | Additional context |

**State Machine**:
```
PENDING → RESOLVED   (user answered)
PENDING → TIMED_OUT  (timeout fired)
PENDING → CANCELLED  (explicit cancel / limit exceeded)
TIMED_OUT → CANCELLED (explicit cancel after timeout)
```

Methods: `from_hil_request(cls, request, react_snapshot, device_id)`, `resolve(decision_branch)`, `time_out()`, `cancel(reason)`, `to_persistence()`, `from_persistence(cls, data)`, `to_hil_request()` (for recovery re-presentation)

Properties: `is_pending`, `is_terminal`, `elapsed_ms`, `remaining_timeout_ms`

#### `TaskStatus(str, Enum)`
```
DISPATCHED  = "DISPATCHED"
IN_PROGRESS = "IN_PROGRESS"
SUSPENDED   = "SUSPENDED"
COMPLETED   = "COMPLETED"
FAILED      = "FAILED"
CANCELLED   = "CANCELLED"
```

#### `TaskStateEntry` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Unique task ID |
| `action` | `str` | Action being performed |
| `status` | `TaskStatus` | Current lifecycle status |
| `dispatched_at_ms` | `int` | Dispatch timestamp |
| `completed_at_ms` | `int \| None` | Completion timestamp |
| `depends_on` | `str \| None` | Task dependency |
| `progress_pct` | `int` | 0-100 progress |
| `pending_hil` | `dict \| None` | Serialized HILRequest for crash recovery |
| `hil_suspensions_count` | `int` | Total HITL rounds used |
| `findings_so_far` | `list[dict]` | Accumulated results |
| `hil_history` | `list[dict]` | HITL interaction history for L2 checks |
| `cancel_reason` | `str \| None` | Why cancelled |

Methods: `suspend(hil_request)`, `resume() -> dict|None`, `cancel(reason)`, `complete()`, `fail(reason)`, `record_hil_interaction(hil_type, resolution)`, `to_dict()`, `from_dict(cls, data)`

Properties: `is_suspended`, `has_pending_hil`, `is_terminal`

#### `HILTimeoutEvent` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Timed-out task |
| `hil_type` | `str` | HITL type |
| `timeout_ms` | `int` | Configured timeout |
| `elapsed_ms` | `int` | Actual elapsed |
| `question` | `str` | Unanswered question |
| `error_code` | `str` | `"HITL_TIMEOUT"` |
| `reason` | `str` | `"hil_timeout"` |

Methods: `to_payload()`, `from_payload(cls, data)`, `from_task_state(cls, entry, now_ms)`

#### `CrashRecoveryReport` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `recovered_task_ids` | `list[str]` | Within timeout, re-present |
| `timed_out_task_ids` | `list[str]` | Past timeout, auto-cancel |
| `skipped_task_ids` | `list[str]` | Not SUSPENDED or no pending_hil |
| `total_scanned` | `int` | Total entries scanned |

#### Free Functions
- `scan_for_recovery(task_state, now_ms) -> CrashRecoveryReport` — Scans for SUSPENDED tasks with pending_hil. Categorizes as recovered/timed_out/skipped.
- `build_timeout_events(report, task_state, now_ms) -> list[HILTimeoutEvent]` — Builds bus events for timed-out tasks.

---

### 4.6 `hitl_wiring.py` — Cross-layer Wiring & Validation

**Purpose**: Assembles resume context for Back, defines HITL mode configurations, and validates cross-layer wiring consistency.

**Cross-component imports**:
- `k1.concierge.prompt.builder` — `SS_READ_CONFIGS`, `SSReadConfig`
- `k1.concierge.prompt.mode` — `CRISIS_ITERATIONS_TABLE`, `MAX_ITERATIONS_TABLE`, `TOOL_ALLOWLIST`, `PromptMode`
- `k1.concierge.prompt.sections` — `ANTI_PATTERN_KEYS`, `MODE_EXAMPLES`, `MODE_SECTIONS`
- `k1.concierge.events.hitl` (lazy in validate) — `HILRequested`, `HILResolved`, `TaskResumed`, `TaskSuspended`
- `k1.concierge.events.validator` (lazy in validate) — `EVENT_SCHEMA_REGISTRY`, `validate_event`
- `k1.concierge.fsm.arbiter.ConversationArbiter` (lazy in validate)

#### `RESUME_INSTRUCTIONS: dict[str, str]`
Per-type natural language instructions for Back when resuming:
- **clarification**: "Use findings_so_far as starting state. Do NOT re-execute succeeded tools."
- **approval**: "If approved: execute with merged_params. Do NOT call discover_capabilities again."
- **selection**: "Resume with selected option. Do NOT re-execute discovery search."

#### `ResumeContext` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Task being resumed |
| `hil_type` | `str` | HITL type resolved |
| `original_task` | `dict` | Original dispatch spec |
| `findings_so_far` | `list[dict]` | ReAct history before suspension |
| `tool_history` | `list[dict]` | Tool-call-only subset of findings |
| `last_iteration` | `int` | Iteration at suspension |
| `resolution` | `dict` | User's answer |
| `resume_instruction` | `str` | Natural language instruction |
| `remaining_budget` | `int` | Iterations left (min floor=2) |
| `merged_params` | `dict` | Params with user mods |

Properties: `has_findings`, `tool_count`
Method: `to_back_context() -> dict` — serializes to BackContext_TaskResume format.

#### `build_resume_context(...) -> ResumeContext`
Assembles from task_id, hil_type, resolution, findings_so_far, original_task, last_iteration, total_budget, merged_params.
- Extracts tool history from findings (entries with role=tool or type=tool_call)
- Computes remaining_budget with **min-2 floor** (M6 E6.2.5: guarantees ≥1 tool call + submit_result)

#### `HILModeConfig` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `mode` | `PromptMode` | The prompt mode |
| `tool_allowlist` | `list[str]` | Tools available |
| `max_iterations` | `int` | Normal budget |
| `crisis_iterations` | `int` | Crisis-adjusted budget |
| `prompt_sections` | `list[str]` | Ordered section keys |
| `anti_pattern_key` | `str` | Anti-pattern section |
| `ss_read_configs` | `list[SSReadConfig]` | SS section reads |
| `has_examples` | `bool` | In-context examples exist |

#### Mode Configurations

##### `get_hitl_relay_config() -> HILModeConfig`
HITL_RELAY: Pure text-only mode
- **0 tools** (empty allowlist)
- **1 iteration** (single translation pass)
- Sections: IDENTITY + EMOTIONAL_CALIB + SAFETY_HITL
- 4 SS reads: affective_now, control, persona, task_state
- Anti-pattern: ANTI_PATTERNS_HITL

##### `get_hitl_resolve_config() -> HILModeConfig`
HITL_RESOLVE: Short cognitive mode
- **1 tool**: `update_beliefs`
- **3 iterations** (normal) / **2 iterations** (crisis)
- 5 sections: IDENTITY + REACT_RHYTHM_REDUCED + ...
- 7 SS reads: beliefs, scoreboard, affect, control, history, persona, task
- Anti-pattern: ANTI_PATTERNS_HITL

#### `validate_hitl_wiring() -> list[str]`
Returns list of issues (empty = all good). 14+ checks across layers:
1. HITL_RELAY: empty tools, max_iter=1, crisis_iter=1, SAFETY_HITL section, task_state SS read
2. HITL_RESOLVE: tools={update_beliefs}, max_iter=3, crisis_iter=2, STATE_INTERP_TASK section, history_active SS read, beliefs_active SS read
3. Both: ANTI_PATTERNS_HITL, IDENTITY section, EMOTIONAL_CALIB section, in-context examples
4. Resume instructions for all 3 types
5. Canonical event schema registry validation (roundtrip construct → to_payload → validate_event)
6. Multi-device HITL: Arbiter has `resolve_device_conflict`, `detect_high_impact_conflict`

---

## 5. Weave Subsystem

### 5.1 `weave_state.py` — FSM State → WeaveAction Decision Table

**Purpose**: Maps FSM state to weave action when task.complete arrives. Plus pending results queue.

**Cross-component imports**:
- `k1.concierge.fsm.states.ConciergeState`

#### `WeaveAction(str, Enum)`
```
IMMEDIATE   = "immediate"    # Front idle, invoke now
QUEUE_WEAVE = "queue_weave"  # Queue, weave after Front finishes
QUEUE       = "queue"        # Just queue, drain later
CHAIN       = "chain"        # Append to current delivery
DEAD_LETTER = "dead_letter"  # Queue at capacity (overflow)
```

#### `STATE_ACTION_TABLE: dict[ConciergeState, WeaveAction]`
| FSM State | WeaveAction |
|-----------|-------------|
| LISTENING | IMMEDIATE |
| COMPANIONING | QUEUE_WEAVE |
| DISPATCHING | QUEUE |
| DELIVERING | CHAIN |
| WEAVING | QUEUE |
| CANCELLING | QUEUE |
| CLARIFYING_USER | QUEUE |
| CLARIFYING_WORKER | QUEUE |
| INTERRUPT_HANDLING | QUEUE |
| PROGRESSING | QUEUE |
| PROACTIVE_WAKE | IMMEDIATE |

#### `get_weave_action(fsm_state) -> WeaveAction`
Lookup with QUEUE as default for unknown states.

#### `PendingResult` (dataclass)
Fields: `task_id`, `task_description`, `result_data`, `queued_at_ns`.
Methods: `to_payload()`, `from_payload(cls, data)`

#### `PendingResultsQueue`
Bounded FIFO queue with overflow eviction (M2 E2.2.5).
- `push(result) -> PendingResult | None` — returns evicted if overflow
- `drain() -> list[PendingResult]` — drains and clears
- `peek() -> list[PendingResult]` — non-destructive
- Properties: `count`, `is_empty`
- Default `max_depth=16`

---

### 5.2 `weave_batcher.py` — WeaveBatcher

**Purpose**: Batches completed-task results in 500ms windows. Handles Front-busy queueing, immediate flush on user input, and paced delivery.

**Cross-component imports**:
- `k1.concierge.config.get_config` — batch window & max queued depth from config

#### `WEAVE_BATCH_WINDOW_MS: int = 500`

#### `WeaveResult` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Task ID |
| `task_description` | `str` | Human-readable name |
| `result_data` | `dict` | Structured results |
| `completed_at_ns` | `int` | Completion timestamp |

Methods: `to_prompt_block() -> str` (formats `[ASYNC RESULT ARRIVED]...[END ASYNC RESULT]` block), `to_payload()`, `from_payload(cls, data)`

#### `WeaveBatcher`
| Slot | Type | Description |
|------|------|-------------|
| `batch_window_ms` | `int` | From config |
| `_flush_fn` | `Callable` | Callback to invoke Front LLM |
| `_pending` | `list[WeaveResult]` | Current batch window |
| `_timer` | `asyncio.Task \| None` | Batch window timer |
| `_front_busy` | `bool` | Whether Front is generating |
| `_queued` | `list[WeaveResult]` | Queued while Front busy |
| `_batch_count` | `int` | Total batches flushed |
| `_max_queued_depth` | `int` | From config |

**Key Methods**:
| Method | Description |
|--------|-------------|
| `on_task_complete(result) -> WeaveResult \| None` | If Front busy: queue (evict oldest if overflow, return evicted). Otherwise: add to pending, start timer. |
| `flush() -> list[WeaveResult] \| None` | Cancel timer, flush all pending via flush_fn |
| `flush_paced(pacing_plan) -> list[WeaveResult] \| None` | OPP-1: deliver in groups with inter-group delays |
| `flush_for_user_input() -> list[WeaveResult] \| None` | Immediate flush on user input |
| `set_front_busy(busy)` | Toggle Front-busy flag |
| `drain_queued() -> list[WeaveResult]` | Move queued → pending after Front finishes |

**Edge Cases**:
1. Single result in window → normal weave
2. Result during Front LLM → queue
3. User input during batch → flush immediately
4. 0 results at expiry → no-op
5. Late arrival after flush → new batch window
6. Queue overflow → evict oldest, return for dead-letter

---

### 5.3 `weave_policy.py` — Adaptive WeavePolicy & Pacing

**Purpose**: Adaptive weave decision engine with 6 signal categories, 9-rule priority-ordered decision table, pacing strategies, and integration router.

**Cross-component imports**:
- `k1.concierge.fsm.states.ConciergeState`

#### Signal Constants
| Constant | Value | Meaning |
|----------|-------|---------|
| `IDLE_EAGER_MS` | `10_000` | Idle 10s+ → eager delivery |
| `IDLE_BATCH_MS` | `3_000` | Active within 3s → extend window |
| `TYPING_SUPPRESS_MS` | `500` | Typing within 500ms → suppress |
| `EMOTIONAL_GATE_OPEN` | `"open"` | All results can be woven |
| `EMOTIONAL_GATE_SUPPRESS_TRIVIAL` | `"suppress_trivial"` | Only critical/urgent |
| `EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY` | `"suppress_all_non_safety"` | Only safety-critical |
| `EMOTIONAL_SUPPRESS_VALENCE` | `-0.5` | Valence threshold for suppress_trivial |

#### `UserActivityTracker`
Tracks typing status and idle duration.
- `on_typing_start()`, `on_typing_stop()`, `on_user_input()`
- Properties: `is_typing`, `idle_ms`, `last_user_input_ns`, `typing_duration_ms`

#### `WeaveSignal` (frozen dataclass)
12 fields across 6 signal categories:
1. **FSM state**: `fsm_state`
2. **Task urgency**: `pending_count`, `pending_urgency_profile`, `has_critical`
3. **User activity**: `user_typing`, `user_idle_ms`
4. **Affect**: `affect_band`, `affect_valence`, `emotional_gate`
5. **BackPool**: `backpool_utilization`
6. **Cross-milestone**: `hitl_pending`, `recent_weave_count`

Factory: `from_runtime(fsm_state, turn_state, back_pool, ss, activity_tracker, hitl_pending, recent_weave_count)` — atomic synchronous collection.

Methods: `to_dict()`, `from_dict(cls, data)`

#### `WeaveDecision(IntEnum)`
```
IMMEDIATE = 0   # Deliver now (0ms)
BATCH     = 1   # Dynamic window (200-5000ms)
DEFER     = 2   # Hold until user asks
DIGEST    = 3   # Accumulate 10-30s then summarize
SUPPRESS  = 4   # Do not deliver
```

#### `WeaveDecisionResult` (frozen dataclass)
Fields: `decision`, `window_ms`, `reasoning`, `urgency_override`, `emotional_gate_applied`

#### `WeavePolicy`
Stateless decision engine. 9-rule priority table:

| Rule | Condition | Decision | Window |
|------|-----------|----------|--------|
| R1 | LISTENING + idle > 10s | IMMEDIATE | 0 |
| R2 | has_critical + gate=open | IMMEDIATE | 0 |
| R3 | user_typing | DEFER | 0 |
| R4 | gate=suppress_all_non_safety | SUPPRESS | 0 |
| R5 | gate=suppress_trivial + no critical | DEFER | 0 |
| R5.5 | hitl_pending + no critical | DEFER | 0 |
| R6 | pending≥3 + all low | DIGEST | 15000 |
| R7 | pending≥1 + idle > 3s | BATCH | dynamic |
| R8 | pool_util > 0.8 | BATCH | 2000 |
| R9 | default | BATCH | 500 |

Config properties with fallbacks: `_idle_eager_ms`, `_idle_batch_ms`, `_digest_threshold_count`, `_digest_window_ms`, `_pool_pressure_threshold`, `_pool_pressure_batch_ms`, `_default_batch_ms`, `_max_batch_ms`, `_max_consecutive_defers`.

#### Pacing (OPP-1)

##### `PacingStrategy(IntEnum)`
```
NONE             = 0   # Single envelope
STAGGER          = 1   # One at a time with delay
GROUP_BY_DOMAIN  = 2   # Group by domain
PRIORITY_CASCADE = 3   # Critical first, then normal, then low
```

##### `PacingPlan` (frozen dataclass)
Fields: `strategy`, `groups: list[list[dict]]`, `inter_group_delay_ms: list[int]`

##### `compute_pacing_plan(results, strategy, base_delay_ms=800) -> PacingPlan`
Computes groups and delays based on strategy.

#### `WeaveIntegrationRouter`
Maps `WeavePolicy.decide()` → `RoutingResult` action tags for FSM controller.

##### `RoutingResult` (frozen dataclass)
Fields: `action` (flush_now/schedule_flush/mark_deferred/schedule_digest/suppress), `window_ms`, `decision`, `reasoning`

---

## 6. Delivery Strategy

**File**: `delivery_strategy.py`

**Purpose**: Answers HOW to deliver results (presentation mode), complementing WeavePolicy's WHEN. OPP-8 Natural Flow Delivery.

**Cross-component imports**: None directly (reads SessionState via passed `ss` param).

#### `ResultClassification(IntEnum)`
```
AWAITED        = 0   # User explicitly asked for this
FOLLOW_UP      = 1   # Chained/dependent task
BACKGROUND     = 2   # Speculative/prefetched
TIME_SENSITIVE = 3   # Real-world deadline
INFORMATIONAL  = 4   # Status update / FYI
```

#### `classify_result(...) -> ResultClassification`
Args: result dict, active_dispatch_task_ids, current_turn, dispatch_turn, has_expiry, is_chained.
Rules:
- has_expiry or urgency=critical/urgent → TIME_SENSITIVE
- In active_dispatch_task_ids + turn_age≤3 → AWAITED
- is_chained → FOLLOW_UP
- urgency=low → INFORMATIONAL
- default → BACKGROUND

#### `ConversationFlowSignal` (frozen dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `topic_match_score` | `float` | 0.0-1.0 result-topic match |
| `conversation_depth` | `int` | Consecutive turns on same topic |
| `is_natural_pause` | `bool` | Topic shift/lull detected |
| `user_awaiting_result` | `bool` | User waiting for update |
| `last_user_intent` | `str` | Classified intent from Phase 1 |
| `turns_since_dispatch` | `int` | Turns since dispatch |

Factory: `from_session_state(ss, result_domain, current_turn, dispatch_turn)` — reads scoreboard (domain, intent) and narrative (depth, shifts) from SessionState.

#### `DeliveryMode(IntEnum)`
```
DIRECT_PRESENT       = 0   # Result IS the focus → PRESENT prompt mode
CONVERSATIONAL_WEAVE = 1   # Mid-conversation → WEAVE prompt mode
CONTEXTUAL_INJECT    = 2   # Silently add to context → STANDARD mode
BRIEF_NOTIFY         = 3   # One-liner → PRESENT + brief=True
DEFERRED_QUEUE       = 4   # Store for later → no LLM call
```

#### `DeliveryStrategy` (frozen dataclass)
Fields: `delivery_mode`, `result_class`, `reasoning`, `topic_relevant`, `prompt_mode_hint`, `brief`, `inject_as_context`

#### `DeliveryStrategyConfig` (dataclass)
Tunables: `deep_conversation_threshold=5`, `topic_match_weave_threshold=0.3`, `max_deferred_results=5`, `natural_pause_inject_all=True`

#### `DeliveryStrategyEngine`
13-rule priority table (first match wins):

| Rule | Condition | Mode |
|------|-----------|------|
| D1 | AWAITED + awaiting + idle | DIRECT_PRESENT |
| D2 | AWAITED + COMPANIONING + topic>0.3 | CONVERSATIONAL_WEAVE |
| D3 | AWAITED + COMPANIONING + topic≤0.3 | DIRECT_PRESENT |
| D1b | AWAITED + idle | DIRECT_PRESENT |
| D4 | TIME_SENSITIVE | BRIEF_NOTIFY |
| D5 | FOLLOW_UP + topic≥0.5 | CONVERSATIONAL_WEAVE |
| D6 | FOLLOW_UP + pause | BRIEF_NOTIFY |
| D7 | FOLLOW_UP + deep | DEFERRED_QUEUE |
| D8 | BACKGROUND + pause | CONTEXTUAL_INJECT |
| D9 | BACKGROUND + deep | DEFERRED_QUEUE |
| D10 | BACKGROUND + topic≥0.5 | CONTEXTUAL_INJECT |
| D11 | INFORMATIONAL + pause | BRIEF_NOTIFY |
| D12 | INFORMATIONAL | DEFERRED_QUEUE |
| D13 | default | CONVERSATIONAL_WEAVE |

Also respects: WeavePolicy SUPPRESS → DEFERRED_QUEUE, emotional_gate=suppress_all + not TIME_SENSITIVE → DEFERRED_QUEUE.

---

## 7. Trust Accumulator

**File**: `trust_accumulator.py`

**Purpose**: Per-session trust score tracking based on HITL interaction outcomes. Higher trust = fewer HITL interruptions. OPP-4.

**Cross-component imports**: None (self-contained primitive).

#### `TrustConfig` (dataclass)
| Field | Default | Description |
|-------|---------|-------------|
| `initial_trust` | 0.5 | Starting score |
| `reward_approve` | +0.05 | On user approval |
| `penalty_reject` | -0.10 | On rejection |
| `penalty_cancel` | -0.07 | On cancellation |
| `penalty_modify` | -0.03 | On modification |
| `reward_auto_success` | +0.08 | On successful auto-approve |
| `auto_approve_threshold` | 0.85 | Trust level for auto-approve |
| `min_trust` | 0.0 | Floor |
| `max_trust` | 1.0 | Ceiling |
| `decay_per_turn` | 0.0 | Inactivity decay |

#### Trust Event Constants
```python
TRUST_EVENT_APPROVE      = "approve"
TRUST_EVENT_REJECT       = "reject"
TRUST_EVENT_CANCEL       = "cancel"
TRUST_EVENT_MODIFY       = "modify"
TRUST_EVENT_AUTO_SUCCESS = "auto_success"
TRUST_EVENT_TIMEOUT      = "timeout"       # 0.0 delta (absence ≠ distrust)
```

#### `TrustSnapshot` (dataclass)
Fields: `trust_score`, `total_interactions`, `approvals`, `rejections`, `auto_approvals`, `last_event`, `last_event_ns`

#### `TrustAccumulator`
| Method | Signature | Description |
|--------|-----------|-------------|
| `record_outcome` | `(event: str) -> float` | Record event, return new trust |
| `should_auto_approve` | `(risk_level: str) -> bool` | Only for "low" risk + trust ≥ threshold |
| `get_dynamic_max_rounds` | `(base: int) -> int` | trust≥0.9: base-1, trust≤0.2: base+1 |
| `snapshot` | `() -> TrustSnapshot` | Point-in-time snapshot |
| `restore` | `(snapshot) -> None` | Crash recovery |

Properties: `trust_score`, `total_interactions`

**Trust flow summary**:
1. User approves → trust increases (+0.05)
2. User rejects/modifies → trust decreases (-0.10/-0.03)
3. User cancels → moderate decrease (-0.07)
4. Timeout → no change (absence ≠ distrust)
5. Successful auto-approve → trust increases (+0.08)

---

## 8. Task Lease

**File**: `task_lease.py`

**Purpose**: Temporal ownership and expiry for Back worker tasks. Provides cooperative cancellation integration and HITL suspension lifecycle.

**Cross-component imports**:
- `k1.concierge.protocols.cancellation.CancellationToken`

#### `LeaseStatus(str, Enum)`
```
ACTIVE    = "active"     # Lease valid, worker running
SUSPENDED = "suspended"  # HITL wait, TTL paused
EXPIRED   = "expired"    # TTL elapsed
RELEASED  = "released"   # Normal completion
CANCELLED = "cancelled"  # User cancel, arbiter supersede
```

#### `TaskLease` (dataclass)
| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Governed task |
| `worker_id` | `str` | Owning worker |
| `lease_id` | `str` | UUID4 identifier |
| `granted_at_ns` | `int` | Monotonic grant time |
| `expires_at_ns` | `int` | Monotonic expiry |
| `cancellation_token` | `CancellationToken \| None` | Cooperative cancel |
| `renewed_count` | `int` | Times renewed |
| `max_renewals` | `int` | Max allowed (default 3) |
| `status` | `LeaseStatus` | Current status |

**Key Methods**:
| Method | Description |
|--------|-------------|
| `renew(extension_ns, extension_s=60) -> bool` | Extend expiry. Returns False if max exceeded or not ACTIVE. |
| `release()` | ACTIVE → RELEASED |
| `expire()` | ACTIVE → EXPIRED |
| `cancel()` | ACTIVE/SUSPENDED → CANCELLED. Also cancels CancellationToken. |
| `suspend()` | ACTIVE → SUSPENDED. Saves remaining TTL. TTL paused. |
| `resume(new_worker_id)` | SUSPENDED → ACTIVE. Restores remaining TTL. |
| `to_payload() -> dict` | Serialize for bus event |

Properties: `is_expired`, `remaining_ns`, `remaining_s`

**Expiry rules**:
- EXPIRED/RELEASED/CANCELLED → always expired
- SUSPENDED → NOT expired (TTL paused)
- ACTIVE → `monotonic_ns() >= expires_at_ns`

#### `create_task_lease(task_id, worker_id, lease_ttl_s=300, max_renewals=3, cancellation_token=None) -> TaskLease`
Factory function. Sets `expires_at_ns = granted_at_ns + ttl`.

---

## 9. OPP Pipeline

**File**: `opp_pipeline.py`

**Purpose**: Wires all 8 OPP (Opportunity Pattern) primitives into the FSM controller's event lifecycle via hook methods.

**Cross-component imports**:
- `k1.concierge.fsm.arbiter.is_short_input` (lazy in on_classify)
- `k1.concierge.prompt.affect` (lazy in on_pre_llm_call) — `AFFECT_MODIFIERS`, `apply_affect_hard_constraints`
- `k1.concierge.protocols.delivery_strategy` (lazy in on_task_complete) — `ConversationFlowSignal`, `classify_result`
- `k1.concierge.protocols.weave_policy` (lazy in on_weave_flush) — `PacingStrategy`, `compute_pacing_plan`

#### `OppPipelineConfig` (dataclass)
8 boolean toggles, all default True:
```
enable_paced_delivery        # OPP-1
enable_recency_decay         # OPP-2
enable_affect_hard_caps      # OPP-3
enable_trust_accumulator     # OPP-4
enable_proactive_scheduler   # OPP-5
enable_episodic_compression  # OPP-6
enable_dynamic_identity      # OPP-7
enable_delivery_strategy     # OPP-8
```

#### Hook Result Dataclasses
| Dataclass | Hook | Key Fields |
|-----------|------|------------|
| `ClassifyEnrichment` | `on_classify` | `recency_decay_applied`, `short_input_penalty` |
| `PromptEnrichment` | `on_pre_prompt_build` | `compressed_context`, `identity_block`, `episodes_used`, `recent_turns_kept` |
| `LlmParamOverrides` | `on_pre_llm_call` | `max_response_tokens`, `vocabulary_tier`, `tool_budget_override`, `affect_band_applied` |
| `DeliveryDecision` | `on_task_complete` | `delivery_mode`, `prompt_mode_hint`, `brief`, `inject_as_context`, `result_class` |
| `TrustGate` | `on_pre_invoke` | `auto_approved`, `trust_level`, `dynamic_max_rounds`, `gate_reasoning` |
| `ProactiveTriggerResult` | `on_idle_tick` | `should_trigger`, `trigger_type`, `trigger_reason` |
| `PacingResult` | `on_weave_flush` | `use_pacing`, `strategy`, `group_count`, `inter_group_delay_ms` |

#### `OppPipeline`
Primitive attachment (all optional — None = disabled):
- `set_trust_accumulator(accum)` — OPP-4
- `set_proactive_scheduler(sched)` — OPP-5
- `set_episodic_compressor(comp)` — OPP-6
- `set_dynamic_identity(identity)` — OPP-7
- `set_delivery_engine(engine)` — OPP-8

**8 Lifecycle Hooks and their call sites**:

| Hook | OPP | Call Site | Description |
|------|-----|-----------|-------------|
| `on_classify` | OPP-2 | Phase 1 classification | Recency bias decay on arbiter overlap scores |
| `on_pre_prompt_build` | OPP-6, OPP-7 | Front prompt build | Episodic compression + dynamic identity |
| `on_pre_llm_call` | OPP-3 | Front LLM call | Affect hard caps on tokens/vocab/tool budget |
| `on_task_complete` | OPP-8 | task.complete received | Delivery strategy (HOW to present) |
| `on_hitl_outcome` | OPP-4 | HITL resolution | Record trust event |
| `on_pre_invoke` | OPP-4 | Pre-invoke check | Trust-based auto-approve gate |
| `on_idle_tick` | OPP-5 | 1s idle timer | Proactive message trigger |
| `on_weave_flush` | OPP-1 | Weave batch flush | Pacing plan computation |
| `on_natural_pause` | OPP-8 | Topic shift detected | Re-evaluate deferred results |

Each hook is a **no-op passthrough** if the relevant primitive is not attached or not enabled.

**Error handling**: Every hook wraps its logic in try/except with `logger.warning` on failure and a safe default return.

---

## 10. Cross-Component Import Map

| Source Module | Imports From |
|---------------|-------------|
| `cancel_events.py` | `k1.concierge.task.topics` |
| `cancel_handler.py` | `k1.concierge.events.task.TaskCancelled` (lazy), `k1.concierge.ledger.projections.project_cancel_state` (lazy), `k1.concierge.ledger.store.LedgerEntry` (TYPE_CHECKING), `k1.concierge.ledger.writer.LedgerWriter` (TYPE_CHECKING) |
| `cancellation.py` | (none — self-contained) |
| `delivery_strategy.py` | (none — reads SS via params) |
| `hitl.py` | `k1.concierge.config.get_config`, `k1.concierge.protocols.suspension.MAX_SUSPENSIONS_PER_TASK` |
| `hitl_coordinator.py` | `k1.concierge.config.get_config`, `k1.concierge.events.hitl.HILRequested` (lazy), `k1.concierge.events.hitl.HILResolved` (lazy), `k1.concierge.ledger.*` (TYPE_CHECKING) |
| `hitl_flow.py` | (protocols-internal only) |
| `hitl_persistence.py` | (protocols-internal only) |
| `hitl_pipeline.py` | (protocols-internal only) |
| `hitl_wiring.py` | `k1.concierge.prompt.builder.SS_READ_CONFIGS`, `k1.concierge.prompt.mode.*`, `k1.concierge.prompt.sections.*`, `k1.concierge.events.hitl.*` (lazy), `k1.concierge.events.validator.*` (lazy), `k1.concierge.fsm.arbiter.ConversationArbiter` (lazy) |
| `opp_pipeline.py` | `k1.concierge.fsm.arbiter.is_short_input` (lazy), `k1.concierge.prompt.affect.*` (lazy), `k1.concierge.protocols.delivery_strategy.*` (lazy), `k1.concierge.protocols.weave_policy.*` (lazy) |
| `suspension.py` | `k1.concierge.config.get_config` |
| `suspension_events.py` | (none) |
| `suspension_manager.py` | `k1.concierge.events.hitl.TaskSuspended` (lazy), `k1.concierge.events.hitl.TaskResumed` (lazy), `k1.concierge.ledger.*` (TYPE_CHECKING) |
| `task_lease.py` | `k1.concierge.protocols.cancellation.CancellationToken` |
| `trust_accumulator.py` | (none — self-contained) |
| `weave_batcher.py` | `k1.concierge.config.get_config` |
| `weave_policy.py` | `k1.concierge.fsm.states.ConciergeState` |
| `weave_state.py` | `k1.concierge.fsm.states.ConciergeState` |

**Key dependency pattern**: Heavy use of **lazy imports** (inside methods) and **TYPE_CHECKING** guards to avoid circular imports, especially for `ledger.*`, `events.*`, and `fsm.arbiter`.

---

## 11. Error Handling Patterns

### Custom Exceptions
| Exception | Module | Trigger |
|-----------|--------|---------|
| `TaskCancelledError` | `cancellation.py` | Token checked at tool boundary when cancelled |
| `SuspensionLimitExceeded` | `suspension.py` | Task exceeds max suspensions (config, default 2) |
| `SuspensionTimeoutError` | `suspension.py` | User did not respond within timeout |
| `ValueError` | `hitl_coordinator.py` | RED safety band blocks execution |
| `ValueError` | `suspension_manager.py` | Task already has active suspension (concurrent limit) |

### Defensive Patterns
- **Idempotent operations**: `CancellationToken.cancel()` is safe to call multiple times. `CancellationHandler.request_cancel()` returns False on re-cancel.
- **Write-before-mutate**: All ledger writes happen BEFORE in-memory state mutation (cancel_handler, suspension_manager, hitl_coordinator).
- **Graceful degradation**: All OPP pipeline hooks wrap in try/except and return safe defaults.
- **Unknown safety band → AMBER**: `detect_approval_required()` and `validate_before_invoke()` both default unknown bands to AMBER (err on caution).
- **Timeout auto-cancel**: FSM auto-cancels on HITL timeout — Invariant 3 guarantees every HITL cycle closes.

---

## 12. Key Invariants

From V2 Section 9.10 and cross-module enforcement:

| # | Invariant | Enforced By |
|---|-----------|-------------|
| 1 | No side-effect capability executes without user approval | `detect_approval_required()`, L2 `validate_before_invoke()` |
| 2 | Every HITL shape follows the same closed cycle | `HILCoordinator` (uniform handle_needs_human → handle_user_response) |
| 3 | Every HITL cycle closes (timeout guarantees closure) | `SuspensionManager._watch_timeout()`, `HILTimeoutEvent` |
| 4 | pending_hil survives process restarts | `TaskStateEntry.pending_hil` + `HILSubTask.to_persistence()` → SessionState |
| 5 | Max 2 suspensions per task | `SuspensionManager.suspend()`, `HILCoordinator.handle_needs_human()` |
| 6 | Max 1 concurrent suspension per task | `SuspensionManager.suspend()` |
| 7 | ReAct history preserved across suspension | `SuspensionRequest.react_history`, `HILSubTask.react_snapshot`, `ResumeContext.findings_so_far` |
| 8 | Approval modifications applied BEFORE execution | `apply_approval_modifications()`, `process_approval_response()` |
| 9 | No heuristic flags in HITL flows | `validate_hitl_wiring()` checks HITL modes |
| 10 | Cancellation is cooperative, not preemptive | `CancellationToken.check()` at tool boundaries only |
