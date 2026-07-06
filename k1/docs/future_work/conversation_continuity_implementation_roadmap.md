# K1 Concierge — Conversation Continuity & HITL: Implementation Roadmap

> **Source:** `k1/docs/future_work/conversation_continuity_and_hitl.md`
> **Date:** 2026-07-03
> **Branch:** `feature/prompt-architecture-refactor`
> **Status:** NOT STARTED — design complete, code-verified, all corrections applied

---

## Overview

16 epics across 4 milestones. Every epic grounded against actual code read end-to-end by subagents. Every line number verified against current source.

---

## MILESTONE P0 — Foundation

---

### Epic P0.1: ReActCheckpoint v2 — Enrich For Long-Pause Resume

**Design:** `conversation_continuity_and_hitl.md` §11
**Files:** `k1/concierge/react/checkpoint.py`, `k1/concierge/actors/back.py`

---

#### FILE 1: `k1/concierge/react/checkpoint.py` (57 lines total)

**Imports (L1-6):**

```
L1: """Versioned ReAct checkpoint model for Back suspension/resume."""
L3: from __future__ import annotations
L5: from dataclasses import dataclass, field
L6: from typing import Any
```

**Error class (L9-10):**

```python
L9:  class ReActCheckpointVersionError(ValueError):
L10:     """Raised when a serialized checkpoint version is unsupported."""
```

**Current dataclass (L13-26):**

```python
L13: @dataclass(frozen=True, slots=True)
L14: class ReActCheckpoint:
L17:     task_id: str
L18:     messages: list[dict[str, Any]] = field(default_factory=list)
L19:     tool_history: list[dict[str, Any]] = field(default_factory=list)
L20:     completed_tool_call_ids: list[str] = field(default_factory=list)
L21:     suspension_count: int = 1
L22:     budget_remaining: int = 0
L23:     last_iteration: int = 0
L24:     scratchpad: dict[str, Any] = field(default_factory=dict)
L25:     version: int = 1
```

**9 fields** (task_id required, 8 with defaults). Frozen. Slotted.

**to_dict() (L27-37):**

```python
L27: def to_dict(self) -> dict[str, Any]:
L28:     return {
L29:         "version": self.version,
L30:         "task_id": self.task_id,
L31:         "messages": list(self.messages),
L32:         "tool_history": list(self.tool_history),
L33:         "completed_tool_call_ids": list(self.completed_tool_call_ids),
L34:         "suspension_count": self.suspension_count,
L35:         "budget_remaining": self.budget_remaining,
L36:         "last_iteration": self.last_iteration,
L37:         "scratchpad": dict(self.scratchpad),
L38:     }
```

Serializes 9 keys. Mutable containers copied via `list()`/`dict()`.

**from_dict() (L39-52):**

```python
L39: @classmethod
L40: def from_dict(cls, data: dict[str, Any]) -> "ReActCheckpoint":
L41:     version = int(data.get("version", 1))
L42:     if version != 1:
L43:         raise ReActCheckpointVersionError(
L44:             f"Unsupported ReActCheckpoint version: {version}"
L45:         )
L46:     return cls(
L47:         version=version,
L48:         task_id=str(data.get("task_id", "")),
L49:         messages=list(data.get("messages") or []),
L50:         tool_history=list(data.get("tool_history") or []),
L51:         completed_tool_call_ids=[
L52:             str(v) for v in data.get("completed_tool_call_ids") or []
L53:         ],
L54:         suspension_count=int(data.get("suspension_count", 1) or 1),
L55:         budget_remaining=int(data.get("budget_remaining", 0) or 0),
L56:         last_iteration=int(data.get("last_iteration", 0) or 0),
L57:         scratchpad=dict(data.get("scratchpad") or {}),
L58:     )
```

**HARD VERSION CHECK at L42:** `version != 1` raises error. Must change to accept v1+v2.

**completed_tool_keys() (L54-57):**

```python
L54: def completed_tool_keys(self) -> set[str]:
L55:     keys: set[str] = set()
L56:     for record in self.tool_history:
L57:         if not isinstance(record, dict): continue
L58:         status = str(record.get("result_status", "")).lower()
L59:         if status not in {"ok", "partial"}: continue
L60:         tool_name = str(record.get("tool_name", "") or "")
L61:         args_hash = str(record.get("args_hash", "") or "")
L62:         if tool_name and args_hash:
L63:             keys.add(f"{tool_name}:{args_hash}")
L64:     return keys
```

Builds `{"tool_name:args_hash"}` dedup set from tool_history records with ok/partial status.

---

#### FILE 2: `k1/concierge/actors/back.py` — THE SOLE CHECKPOINT CONSTRUCTOR

**Import (L72):** `from k1.concierge.react.checkpoint import ReActCheckpoint`

**_build_react_checkpoint() (L866-896) — SOLE CONSTRUCTION SITE:**

```python
L866: def _build_react_checkpoint(
L867:     *,
L868:     task_id: str,
L869:     messages: list[ModelMessage],
L870:     tool_dispatcher: ToolDispatcher,
L871:     max_iterations: int,
L872:     result: ReactResult,
L873:     suspension_count: int = 1,
L874: ) -> ReActCheckpoint:
L875:     tool_history = _execution_records(tool_dispatcher)
L876:     completed_call_ids = [
L877:         str(record.get("call_id", ""))
L878:         for record in tool_history
L879:         if str(record.get("result_status", "")).lower()
L880:            in {"ok", "partial"}
L881:            and record.get("call_id")
L882:     ]
L884:     last_iteration = len(result.iteration_durations_ms)
L885:     remaining_budget = max(0, max_iterations - last_iteration)
L886:     return ReActCheckpoint(
L887:         task_id=task_id,
L888:         messages=_serialize_messages(messages),
L889:         tool_history=tool_history,
L890:         completed_tool_call_ids=completed_call_ids,
L891:         suspension_count=suspension_count,
L892:         budget_remaining=remaining_budget,
L893:         last_iteration=last_iteration,
L894:         scratchpad={
L895:             "loop_events": list(
L896:                 getattr(result, "loop_events", []) or []
L897:             )
L898:         },
L899:     )
```

**Every field populated:**

| Field | Source | How |
|---|---|---|
| `task_id` | Parameter | Direct passthrough from `back_handler` L1640 |
| `messages` | `_serialize_messages(messages)` | `ModelMessage` → JSON-safe dict (role, content, tool_call_id, name, tool_calls) |
| `tool_history` | `_execution_records(tool_dispatcher)` | `tool_dispatcher.get_execution_records()` → list of record dicts |
| `completed_tool_call_ids` | Computed from tool_history | `call_id` for records with result_status "ok"/"partial" |
| `suspension_count` | Parameter (default 1) | Suspension counter |
| `budget_remaining` | `max(0, max_iterations - last_iteration)` | Original budget minus consumed iterations |
| `last_iteration` | `len(result.iteration_durations_ms)` | Count of completed iterations from ReactResult |
| `scratchpad` | `{"loop_events": list(getattr(result, "loop_events", []) or [])}` | Loop event log from ReactResult |
| `version` | **NOT passed — defaults to 1** | From dataclass field default at checkpoint.py L25 |

**_resolve_needs_human_in_process() (L1029-1219) — PRIMARY CONSUMER:**

Checkpoint unpacked at **L1068-1107:**

```python
L1068: completed_call_ids: set[str] = set()
L1069: completed_arg_keys: set[str] = set()
L1070: cp_budget_remaining: int | None = None
L1071: cp_suspension_count: int = 0
L1074: if react_checkpoint is not None:
L1076:     from k1.concierge.react.checkpoint import ReActCheckpoint
L1078:     cp: ReActCheckpoint | None = None
L1079:     if isinstance(react_checkpoint, ReActCheckpoint):
L1080:         cp = react_checkpoint
L1081:     elif isinstance(react_checkpoint, dict):
L1082:         cp = ReActCheckpoint.from_dict(react_checkpoint)
L1084:     if cp is not None:
L1085:         completed_call_ids = set(cp.completed_tool_call_ids)
L1086:         completed_arg_keys = cp.completed_tool_keys()
L1087:         cp_budget_remaining = cp.budget_remaining
L1088:         cp_suspension_count = cp.suspension_count
```

**Resume react_loop() call (L1188-1201):**

```python
L1188: current = await react_loop(
L1189:     actor="back",
L1190:     system_prompt=system_prompt,
L1191:     messages=messages,
L1192:     tools=tools,
L1193:     max_iterations=effective_budget,
L1194:     model=model,
L1195:     tool_dispatcher=tool_dispatcher,
L1196:     on_text_response=_noop_text,
L1197:     cancellation_check=cancellation_check,
L1198:     trace_id=trace_id,
L1199:     scenario="task_execution_after_hil",
L1200:     completed_tool_call_ids=completed_call_ids or None,
L1201:     completed_tool_arg_keys=completed_arg_keys or None,
L1202: )
```

**Only `completed_tool_call_ids` and `completed_tool_arg_keys` are wired from checkpoint.** No `loop_events`, no `paused_at_epoch_ms`, no `data_freshness_ttl_seconds`, no `tool_dispatcher_state`, no `capability_bindings`.

**_handle_react_step_or_submit() (~L2072) — SECONDARY CONSUMER:**

Same pattern — extracts `completed_tool_call_ids` and `completed_tool_arg_keys` from `react_checkpoint`, passes to `react_loop()`. Also does NOT pass `loop_events` or any freshness fields.

---

#### CHANGES — 5 Tasks

**Task 1 — Bump version + add 4 fields to ReActCheckpoint dataclass (checkpoint.py):**

Replace L24-25:

```python
# REMOVE:
    scratchpad: dict[str, Any] = field(default_factory=dict)
    version: int = 1

# INSERT:
    scratchpad: dict[str, Any] = field(default_factory=dict)
    # ── v2 long-pause resume fields ──
    paused_at_epoch_ms: int = 0
    data_freshness_ttl_seconds: int = 3600
    tool_dispatcher_state: dict[str, Any] = field(default_factory=dict)
    capability_bindings: list[dict[str, Any]] = field(default_factory=list)
    version: int = 2
```

~6 lines changed.

**Task 2 — Update to_dict() (checkpoint.py L27-38):**

Replace existing return dict — add 4 keys after "scratchpad":

```python
    "scratchpad": dict(self.scratchpad),
    # ── v2 fields ──
    "paused_at_epoch_ms": self.paused_at_epoch_ms,
    "data_freshness_ttl_seconds": self.data_freshness_ttl_seconds,
    "tool_dispatcher_state": dict(self.tool_dispatcher_state),
    "capability_bindings": list(self.capability_bindings),
    "version": self.version,
```

~6 lines added.

**Task 3 — Update from_dict() to accept v1 AND v2 (checkpoint.py L39-58):**

Replace L41-45 (version check) and add 4 new kwargs:

```python
    version = int(data.get("version", 1))
    if version not in (1, 2):
        raise ReActCheckpointVersionError(
            f"Unsupported ReActCheckpoint version: {version}"
        )
    # ... existing fields unchanged ...
    return cls(
        # ... existing kwargs ...
        scratchpad=dict(data.get("scratchpad") or {}),
        # ── v2 fields (default if missing from v1 data) ──
        paused_at_epoch_ms=int(data.get("paused_at_epoch_ms", 0) or 0),
        data_freshness_ttl_seconds=int(data.get("data_freshness_ttl_seconds", 3600) or 3600),
        tool_dispatcher_state=dict(data.get("tool_dispatcher_state") or {}),
        capability_bindings=list(data.get("capability_bindings") or []),
    )
```

~8 lines changed.

**v1→v2 migration path:**

- `from_dict()` accepts both v1 (8-key JSON) and v2 (12-key JSON)
- v1 data: new fields get defaults — `paused_at_epoch_ms=0`, `data_freshness_ttl_seconds=3600`, `tool_dispatcher_state={}`, `capability_bindings=[]`. **Produces a v2 checkpoint object** (version=2 in cls() call).
- v2 data: full round-trip
- Log migration once per checkpoint: `logger.info("ReActCheckpoint v1→v2 migrated task_id=%s", task_id)`

**Task 4 — Populate new fields in _build_react_checkpoint() (back.py L886-899):**

Replace the `return ReActCheckpoint(...)` call — add 4 kwargs:

```python
    return ReActCheckpoint(
        task_id=task_id,
        messages=_serialize_messages(messages),
        tool_history=tool_history,
        completed_tool_call_ids=completed_call_ids,
        suspension_count=suspension_count,
        budget_remaining=remaining_budget,
        last_iteration=last_iteration,
        scratchpad={
            "loop_events": list(
                getattr(result, "loop_events", []) or []
            )
        },
        # ── v2 fields ──
        paused_at_epoch_ms=int(time.time() * 1000),  # durable: survives restart
        # NOTE: use time.monotonic_ns() for in-process freshness only.
        # paused_at_epoch_ms is authoritative for cross-restart staleness.
        data_freshness_ttl_seconds=3600,  # configurable in P0.4
        tool_dispatcher_state={
            "call_count": tool_dispatcher.call_count,
            "per_tool_counts": dict(tool_dispatcher._per_tool_counts),
        },
        capability_bindings=[],  # placeholder — reserved for future
    )
```

~10 lines added. Requires `import time` at top of back.py (check if already present).

`tool_dispatcher.call_count` is public attr (dispatcher.py). `._per_tool_counts` is private but accessible from same package — consider adding a public getter in P0.3.

**Task 5 — Tests:**

File: `tests/k1/concierge/react/test_react_checkpoint.py` (or `test_checkpoint.py`)

New tests:

- `test_v2_round_trip` — create v2 checkpoint with all 12 fields, serialize, deserialize, verify all fields preserved
- `test_v1_backward_compat` — deserialize old 8-key v1 JSON → verify 4 new fields get defaults
- `test_v2_migration_logged` — verify migration log line emitted on v1→v2 deserialization

**Total lines: ~37.** Tests: `pytest tests/k1/concierge/react/test_checkpoint.py -v`

---

### Epic P0.2: Wire Scratchpad/loop_events Into react_loop()

**Design:** `conversation_continuity_and_hitl.md` (scratchpad gap closure)
**Files:** `k1/concierge/react/loop.py`, `k1/concierge/actors/back.py`
**Prerequisite:** P0.1 (ReActCheckpoint must have v2 fields before wiring them)

---

#### FILE 1: `k1/concierge/react/loop.py` (2258 lines)

**react_loop() signature (L1048-1081) — 18 parameters:**

```python
L1048: async def react_loop(
L1049:     actor: str,
L1050:     system_prompt: str,
L1051:     messages: list[ModelMessage],          # MUTATED in-place
L1052:     tools: list[ToolSchema],
L1053:     max_iterations: int,
L1054:     model: IModelHubPort,
L1055:     tool_dispatcher: ToolDispatcher,
L1056:     on_text_response: Callable[[str], Awaitable[None]],
L1057:     cancellation_check: Callable[[], Awaitable[bool]],
L1058:     trace_id: str = "",
L1059:     session_id: str = "",
L1060:     scenario: str = "",
L1061:     validator: LLMOutputValidator | None = None,
L1062:     on_stream: Callable[[StreamChunk], Awaitable[None]] | None = None,
L1063:     control_queue: asyncio.Queue[BackControlEvent] | None = None,
L1064:     completed_tool_call_ids: set[str] | None = None,
L1065:     completed_tool_arg_keys: set[str] | None = None,
L1066:     reasoning_effort: str | None = "auto",
L1067: ) -> ReactResult:
```

**The last 3 optional parameters (L1064-1066) are the checkpoint-resume dedup state.** These ARE wired from checkpoint today. `loop_events` is NOT among them.

**_loop_events initialization (L1107):**

```python
L1107: _loop_events: list[dict[str, Any]] = []
```

ALWAYS starts empty. No way to seed from prior checkpoint.

**_record_loop_event() (L1129-1142):**

```python
L1129: def _record_loop_event(
L1130:     event_type: str,
L1131:     iteration: int,
L1132:     payload: dict[str, Any] | None = None,
L1133: ) -> None:
L1134:     _loop_events.append(
L1135:         ReactLoopEvent(
L1136:             event_type=event_type,
L1137:             actor=actor,
L1138:             scenario=scenario,
L1139:             iteration=iteration,
L1140:             trace_id=trace_id,
L1141:             payload=payload or {},
L1142:         ).to_dict()
L1143:     )
```

**17 call sites (exact lines):**

| L | event_type |
|---|---|
| 1272 | raw control event type from queue |
| 1282 | `"parameter_update_extra_iteration"` |
| 1288 | `"cannot_apply_parameter_update"` |
| 1337 | `"last_iteration_submit"` (Back force-submit nudge) |
| 1420 | `"cancel"` (control queue cancel) |
| 1436 | `"forced_text"` (Front last-iteration text-only) |
| 1460 | `"last_iteration_submit"` (duplicate) |
| 1607 | `"schema_repair"` (validation failed) |
| 1613 | `"degenerate_loop"` (3 invalid schemas) |
| 1653 | `"schema_repair"` (malformed tool call) |
| 1693 | `"degenerate_response"` (empty response) |
| 1695 | `"degenerate_loop"` (3 empty responses) |
| 1975 | `"tool_retryable_error"` |
| 1340 | `"tool_already_completed"` (in _run_tool closure) |
| 2075 | `"front_spin_nudge"` (recall_memory spin guard) |
| 2115 | `"back_capability_spin_nudge"` |
| 2248 | `"last_iteration_submit"` (budget exhausted) |

**_make_result() (L1145-1159) — assembles ReactResult:**

```python
L1145: def _make_result(status, *, text=None, data=None) -> ReactResult:
L1150:     return ReactResult(
L1151:         status=status,
L1152:         text=text,
L1153:         data=data,
L1154:         dispatched_tasks=dispatched_tasks,
L1155:         parallel_tool_calls=_parallel_count,
L1156:         sequential_tool_calls=_sequential_count,
L1157:         iteration_durations_ms=_iteration_durations,
L1158:         loop_events=list(_loop_events),
L1159:     )
```

**ReactResult dataclass (L448-467):**

```python
L448: class ReactResult:
L455:     status: str
L456:     text: str | None = None
L457:     data: dict | None = None
L458:     dispatched_tasks: list[dict] = field(default_factory=list)
L459:     parallel_tool_calls: int = 0
L460:     sequential_tool_calls: int = 0
L461:     iteration_durations_ms: list[int] = field(default_factory=list)
L462:     loop_events: list[dict[str, Any]] = field(default_factory=list)
```

**LLM call site (L1503-1539):** `system_prompt` is embedded in `ToolCallPayload` or `ChatPayload`, sent via `model.execute(request)` or `model.stream_execute(request)`. Messages converted via `_to_k1_messages(messages)`. System prompt is sent EVERY API call — part of the request payload, not cached by the loop.

---

#### FILE 2: `k1/concierge/actors/back.py` — THE GAP

**Where checkpoint→loop data pipe breaks:**

1. `_build_react_checkpoint()` (L866-899) — **serializes** `loop_events` into `scratchpad` ✓
2. `_resolve_needs_human_in_process()` (L1085-1086) — **extracts** `completed_tool_call_ids` and `completed_tool_arg_keys` from checkpoint ✓
3. `_resolve_needs_human_in_process()` (L1188-1202) — **passes** `completed_tool_call_ids` and `completed_tool_arg_keys` to `react_loop()` ✓
4. **loop_events from scratchpad is NEVER extracted from checkpoint and NEVER passed to react_loop()** ✗

The checkpoint at L1084-1088 reads `completed_tool_call_ids`, `completed_tool_keys()`, `budget_remaining`, `suspension_count`. It does NOT read `scratchpad` or `loop_events`.

---

#### CHANGES — 4 Tasks

**Task 1 — Add `loop_events` parameter to react_loop() (loop.py):**

Insert after L1065 (`completed_tool_arg_keys`), before L1066 (`reasoning_effort`):

```python
    completed_tool_arg_keys: set[str] | None = None,
    loop_events: list[dict[str, Any]] | None = None,  # ← P0.2
    reasoning_effort: str | None = "auto",
```

~2 lines.

**Task 2 — Seed `_loop_events` from parameter (loop.py L1107):**

Replace:

```python
    _loop_events: list[dict[str, Any]] = []
```

With:

```python
    _loop_events: list[dict[str, Any]] = list(loop_events or [])
```

~1 line changed. Default `None` → empty list, behavior unchanged.

**Task 3 — Pass `cp.scratchpad.get("loop_events")` on resume in _resolve_needs_human_in_process() (back.py L1188-1202):**

Add to the `react_loop()` call:

```python
    current = await react_loop(
        # ... existing params unchanged ...
        completed_tool_call_ids=completed_call_ids or None,
        completed_tool_arg_keys=completed_arg_keys or None,
        loop_events=cp.scratchpad.get("loop_events") if cp is not None else None,  # ← P0.2
    )
```

~2 lines added. Requires extracting `cp = react_checkpoint` earlier (already available at L1079-1082).

**Also need to extract scratchpad from checkpoint at L1084-1088:**

```python
    if cp is not None:
        completed_call_ids = set(cp.completed_tool_call_ids)
        completed_arg_keys = cp.completed_tool_keys()
        cp_budget_remaining = cp.budget_remaining
        cp_suspension_count = cp.suspension_count
        cp_scratchpad = cp.scratchpad  # ← P0.2: extract scratchpad
```

~1 line added.

**Task 4 — Same wiring in _handle_react_step_or_submit() (back.py ~L2072):**

Extract from `react_checkpoint.scratchpad`, pass to `react_loop()` call. Same pattern as Task 3.
~3 lines.

---

#### VERIFICATION

| Check | How |
|---|---|
| `react_loop()` signature has 19 params (was 18) | Count params |
| Existing callers unaffected | Default `None` → empty list |
| Resume loop's `_loop_events` starts with prior events | Integration test |
| Traces continuous across suspension→resume | Observability check |

**Total lines: ~9.** Tests: existing regression (default None = unchanged). New: `test_loop_events_survive_resume` — checkpoint with loop_events → resume → verify_loop_events contains prior events.

---

### Epic P0.3: HITL Persistent State — Backend

**Design:** `conversation_continuity_and_hitl.md` §5, §12
**Files:** 7 files: `task_state.py`, `back.py`, `suspension.py`, `schemas_back.py`, `implementations.py`, `builder.py`, `controller.py`
**Lines:** ~225

---

#### FILE 1: `k1/sessionstate/sections/task_state.py` (637 lines)

**TaskStateEntry dataclass (L118-132):**

| L | Field | Type | Default |
|---|---|---|---|
| 122 | `task_id` | `str` | `""` |
| 123 | `action` | `str` | `""` |
| 124 | `status` | `str` | `TaskStatus.PENDING` |
| 125 | `dispatched_at_ms` | `int` | `0` |
| 126 | `completed_at_ms` | `int` | `0` |
| 127 | `depends_on` | `List[str]` | `field(default_factory=list)` |
| 128 | `progress_pct` | `int` | `0` |
| **129** | **`pending_hil`** | **`bool`** | **`False`** |
| 130 | `hil_suspensions_count` | `int` | `0` |
| 131 | `presented_at_turn` | `int` | `0` |
| **132** | **`pending_hil_data`** | **`Optional[Dict[str, Any]]`** | **`None`** |

**INSERTION POINT for 4 new decision fields: after L132 (pending_hil_data), creating new L133-136:**

```python
    pending_hil_data: Optional[Dict[str, Any]] = None
    # ── P0.3 persistent decision fields ──
    pending_decision_id: str = ""
    pending_decision_question: str = ""
    pending_decision_options: list[dict] = field(default_factory=list)
    pending_decision_status: str = ""  # "awaiting_user" | "resolved" | "superseded"
```

**TaskStatus enum (L74-84):**

```python
L74: PENDING = "pending"
L75: DISPATCHED = "dispatched"
L76: ACTIVE = "active"
L77: SUSPENDED = "suspended"
L78: COMPLETED = "completed"
L79: FAILED = "failed"
L80: CANCELLED = "cancelled"
```

New status needed: `AWAITING_DECISION = "awaiting_decision"` at L80 (insert before CANCELLED). Also add to `TaskStatus.ALL` (L82) and `TaskStatus.TERMINAL` (L84 — NO, awaiting_decision is not terminal).

**Existing helper methods on TaskStateSection:**

| Method | L | What |
|---|---|---|
| `add_task()` | 311 | Creates entry, inserts into `self._tasks` |
| `update_status()` | 340 | Validates via `_VALID_TRANSITIONS` dict, manages `pending_hil` flag |
| `set_pending_hil_data()` | 398 | Stores crash-recovery data on entry |
| `get_all()` | 424 | Returns `list(self._tasks.values())` |
| `get_by_id()` | 428 | Returns `self._tasks.get(task_id)` |
| `get_suspended()` | 439 | Filters to `TaskStatus.SUSPENDED` |
| `to_prompt()` | ~450 | Renders task state for LLM; already checks `pending_hil` at L516 |
| `prune_completed()` | 564 | Removes TERMINAL tasks after 10 turns |

**NEW helper methods to add (after L420):**

```python
def set_pending_decision(self, task_id: str, decision_id: str, question: str,
                          options: list[dict], status: str = "awaiting_user") -> None:
    if task_id not in self._tasks:
        raise KeyError(f"Task not found: {task_id}")
    entry = self._tasks[task_id]
    entry.pending_decision_id = decision_id
    entry.pending_decision_question = question
    entry.pending_decision_options = list(options)
    entry.pending_decision_status = status
    self._last_updated_ms = int(time.time() * 1000)
    self._cache_valid = False

def resolve_pending_decision(self, task_id: str) -> None:
    if task_id not in self._tasks: return
    self._tasks[task_id].pending_decision_status = "resolved"
    self._last_updated_ms = int(time.time() * 1000)
    self._cache_valid = False

def clear_pending_decision(self, task_id: str) -> None:
    if task_id not in self._tasks: return
    entry = self._tasks[task_id]
    entry.pending_decision_id = ""
    entry.pending_decision_question = ""
    entry.pending_decision_options = []
    entry.pending_decision_status = ""
    self._last_updated_ms = int(time.time() * 1000)
    self._cache_valid = False
```

**Update to_prompt() (after L516):**

```python
# After existing pending_hil check (~L516), ADD:
if getattr(t, "pending_decision_status", "") == "awaiting_user":
    parts.append(f"[AWAITING DECISION: {t.pending_decision_question}]")
elif getattr(t, "pending_decision_status", "") == "resolved":
    parts.append("[decision resolved]")
```

**Also update _VALID_TRANSITIONS (L88-98):** add `TaskStatus.AWAITING_DECISION` as valid from `TaskStatus.ACTIVE` and `TaskStatus.SUSPENDED`.

---

#### FILE 2: `k1/concierge/actors/back.py` — HITL Flow Changes

**_resolve_needs_human_in_process() (L1029-1219):**

**HITL timeout path (L1148-1155) — CURRENT CODE:**

```python
L1148: if getattr(response, "timed_out", False):
L1149:     logger.warning("back_handler: unified HIL timed out task_id=%s", task_id)
L1150:     return ReactResult(
L1151:         status="cancelled",
L1152:         data={
L1153:             "error_code": "HIL_TIMEOUT",
L1154:             "partial_results": data,
L1155:         },
L1156:     )
```

**REPLACE WITH:**

```python
    if getattr(response, "timed_out", False):
        pending = {
            "decision_id": f"dec-{task_id}-{round_index}",
            "task_id": task_id,
            "question": req.question,
            "options": _serialize_options(req.options),
            "hil_type": req.hil_type,
            "status": "awaiting_user",
            "created_at_turn": 0,
            "react_snapshot": (
                react_checkpoint.to_dict()
                if isinstance(react_checkpoint, ReActCheckpoint)
                else _build_react_checkpoint(
                    task_id=task_id, messages=messages,
                    tool_dispatcher=tool_dispatcher,
                    max_iterations=max_iterations, result=current,
                ).to_dict()
            ),
        }
        logger.info(
            "back_handler: HIL timeout → persistent pending_decision task_id=%s decision_id=%s",
            task_id, pending["decision_id"],
        )
        return ReactResult(
            status="awaiting_decision",
            data={
                "pending_decision": pending,
                "partial_results": data,
                "narrative_summary": data.get("narrative_summary", ""),
                "remaining_work": data.get("remaining_work", ""),
            },
        )
```

~30 lines changed.

**HIL_REQUEST_FAILED path (L1138-1147) — REPLACE same pattern:**

```python
    except Exception as exc:
        logger.exception("back_handler: unified HIL request failed task_id=%s", task_id)
        return ReactResult(
            status="awaiting_decision",  # WAS: "cancelled"
            data={
                "pending_decision": { /* same structure as above */ },
                "partial_results": data,
                "error_detail": str(exc),
            },
        )
```

~15 lines changed.

**_emit_back_result() (L1220-1365) — CURRENT status branches:**

```python
L1262: if result.status == "complete":    → task.complete.v1
L1290: elif result.status == "suspended":  → task.suspended.v1
L1320: else:                              → task.failed.v1 (cancelled, budget_exhausted)
```

**ADD new branch after the "suspended" elif block (after L1330):**

```python
    elif result.status == "awaiting_decision":
        data = result.data or {}
        pending = data.get("pending_decision") or {}
        complete_payload = {
            "task_id": task_id,
            "action": task_action,
            "result_type": "awaiting_decision",
            "status": "awaiting_decision",
            "final_answer": data.get("narrative_summary", ""),
            "results": data.get("partial_results", {}).get("results", []),
            "pending_decision": pending,
        }
        for key in ("narrative_summary", "remaining_work"):
            if key in data:
                complete_payload[key] = data[key]
        env = build_task_awaiting_decision(payload=complete_payload, parent_id=parent_id)
        env = _correlate_envelope(env, envelope, trace_id=trace_id)
        bus.publish(env)
```

~20 lines. Uses `task.awaiting_decision` event (NOT `task.complete`).

**back_handler() (L1377-1752) — SS write insertion point:**

After `_resolve_needs_human_in_process()` returns (after L1692), add:

```python
    if result.status == "awaiting_decision":
        pending = (result.data or {}).get("pending_decision")
        if isinstance(pending, dict) and fsm_state is not None:
            ss = getattr(fsm_state, "ss", None)
            if ss is not None:
                try:
                    # Store decision metadata on TaskStateEntry
                    ss.task_state.set_pending_decision(
                        task_id=task_id,
                        decision_id=pending["decision_id"],
                        question=pending["question"],
                        options=pending.get("options", []),
                        status="awaiting_user",
                    )
                    # ALSO store react_snapshot in pending_hil_data
                    # (existing field at task_state.py L132, used by set_pending_hil_data at L398)
                    ss.task_state.set_pending_hil_data(
                        task_id,
                        {"react_snapshot": pending.get("react_snapshot")}
                    )
                except Exception:
                    logger.exception("back_handler: failed to write pending_decision to SS")
```

~15 lines.

**_build_react_checkpoint() (L866-899):** Already handled in P0.1 — `paused_at_epoch_ms` and `data_freshness_ttl_seconds` populated there.

---

#### FILE 3: `k1/hil/suspension.py` — Soft Nudge

**on_timeout_fn type annotation (L81):**

```python
L81: on_timeout_fn: Callable[[str], Awaitable[None]] | None = None
```

**CHANGE TO:**

```python
    on_timeout_fn: Callable[[str, bool], Awaitable[None]] | None = None
```

**_watch_timeout() (L227-255) — CURRENT:**

```python
L244: if self._on_timeout_fn is not None:
L245:     await self._on_timeout_fn(task_id)
```

**CHANGE TO:**

```python
    if self._on_timeout_fn is not None:
        await self._on_timeout_fn(task_id, soft=True)
```

~2 lines changed.

---

#### FILE 4: `k1/concierge/tools/schemas_back.py` — submit_result Schema

**SUBMIT_RESULT_SCHEMA (L311-395):** 10 properties currently. `result_type` enum at L324: `["complete", "needs_human"]`.

**INSERT after L360 (before "required" array) — 2 new OPTIONAL properties:**

```python
    "narrative_summary": {
        "type": "string",
        "description": (
            "Natural-language summary of what was found/done and why. "
            "Write as if briefing a colleague. Front may quote this."
        ),
    },
    "remaining_work": {
        "type": "string",
        "description": (
            "What remains after this decision/task. For continuity context."
        ),
    },
```

~12 lines.

---

#### FILE 5: `k1/concierge/tools/implementations.py` — execute_submit_result()

**Around L1440-1500 — submission dict construction:**

```python
    submission: dict = {"result_type": result_type}
```

**ADD after submission dict init:**

```python
    # ── P0.3: Always capture narrative context ──
    for key in ("narrative_summary", "remaining_work"):
        val = args.get(key)
        if val:
            submission[key] = val
```

Works for BOTH `complete` and `needs_human` — runs before if/else branch split.

---

#### FILE 6: `k1/concierge/prompt/builder.py` — DynamicPromptBuilder

**No `_read_pending_decisions()` exists anywhere in the file (verified: zero matches).**

**NEW method (add after L1496, after `_read_ss_body()`):**

```python
def _read_pending_decisions(self, ss: Any) -> str:
    task_state = self._safe_get_ss_section(ss, "task_state")
    if task_state is None: return ""
    pending = []
    for task in task_state.get_all():
        if getattr(task, "pending_decision_status", "") == "awaiting_user":
            pending.append(
                f"- Decision {task.pending_decision_id}: "
                f"\"{task.pending_decision_question}\" "
                f"(task: {task.action or task.task_id})"
            )
    if not pending: return ""
    return (
        "[PENDING DECISIONS — surface these at natural moments]\n"
        + "\n".join(pending)
        + "\n[/PENDING DECISIONS]"
    )
```

**Call in build() Stage 8 (after L1159, after active_work_block):**

```python
    pending_decisions_block = self._read_pending_decisions(ss)
    if pending_decisions_block:
        prompt_parts.append(pending_decisions_block)
```

**Template variable injection (after L1250, after {open_gaps_list}):**

```python
    # Extract from task_artifacts by task_id/correlation_id, not .latest
    # NOTE: TaskArtifactsSection has NO `latest` property (verified: zero matches in codebase).
    # Artifacts are stored by artifact_id UUID in flat _artifacts dict.
    # Retrieve by get_by_task(task_id) or get_by_id(artifact_id) from completion event.
    back_narrative = ""
    back_remaining = ""
    task_artifacts = self._safe_get_ss_section(ss, "task_artifacts")
    if task_artifacts is not None:
        # Use correlation_id from the task_complete event, not .latest
        completed_task_id = scenario_data.get("completed_task_id", "")
        if completed_task_id:
            artifacts = getattr(task_artifacts, "get_by_task", lambda _: [])(completed_task_id)
            if artifacts:
                latest_artifact = artifacts[-1]  # most recent for this task
                back_narrative = getattr(latest_artifact, "narrative_summary", "") or ""
                back_remaining = getattr(latest_artifact, "remaining_work", "") or ""
    system_prompt = system_prompt.replace("{back_narrative}", back_narrative)
    system_prompt = system_prompt.replace("{back_remaining}", back_remaining)
```

---

#### FILE 7: `k1/concierge/fsm/controller.py` — Decision Continuation

**NEW handler `_on_decision_response()` — MUST be `async def` (contains `await`), registered via async route:**

```python
async def _on_decision_response(self, envelope: Envelope) -> None:
    payload = _parse_payload(envelope)
    decision_id = payload.get("decision_id", "")
    task_id = payload.get("task_id", "")
    if not decision_id or not task_id: return

    # 1. VALIDATE first: check snapshot exists and option is valid
    pending_entry = self._task_bridge.get_task(task_id)
    pending_data = getattr(pending_entry, "pending_hil_data", None) or {}
    snapshot = pending_data.get("react_snapshot") if isinstance(pending_data, dict) else {}
    if not snapshot:
        logger.warning("FSM._on_decision_response: no react_snapshot for task_id=%s", task_id)
        return

    # 2. Evaluate free-text (if not card-click with option_id):
    selected_option = payload.get("selected_option")
    answer_text = payload.get("answer_text", "")
    if selected_option is None and answer_text:
        # Free-text: Back must validate the answer
        evaluation = await self._evaluate_decision(task_id, answer_text)
        if not evaluation.resolved:
            # Not an answer — decision stays pending
            return
        selected_option = evaluation.selected_option_id
        answer_text = evaluation.normalized_answer

    # 3. CAS: transition AWAITING_USER → RESOLVING
    if not self._task_bridge.transition_decision(decision_id, "awaiting_user", "resolving"):
        return  # another process won the race

    # 4. RESOLVE only after validation succeeds
    self._task_bridge.resolve_pending_decision(task_id)

    # 5. Spawn Back resume with ORIGINAL task_id (NOT f"{task_id}-resume")
    resume_ctx = build_resume_context(
        task_id=task_id,
        hil_type="clarification",
        resolution={"selected_option": selected_option, "answer_text": answer_text},
        react_checkpoint=snapshot,
    )
    new_envelope = envelope.derive(
        topic=TOPIC_TASK_DISPATCH,
        payload={
            "task_id": task_id,  # SAME task_id — resume is another attempt, not a new task
            "run_id": str(uuid.uuid4()),
            "attempt_id": str(uuid.uuid4()),
            "resume_generation": pending_data.get("resume_generation", 0) + 1,
            "action": f"continue_{task_id}",
            "resume_context": resume_ctx.to_back_context(),
            "decision_id": decision_id,
            "selected_option": selected_option,
            "answer_text": answer_text,
            "correlation_id": envelope.correlation_id,
        },
    )
    self._deliver_to_back(new_envelope)
```

**CAS lifecycle:** `AWAITING_USER → RESOLVING → RESUME_DISPATCHED → RESOLVED`. Compare-and-swap prevents race between in-process answer, timeout persistence, card click, free-text evaluation. Only one process wins `AWAITING_USER → RESOLVING`.

**Register handler** in FSM topic subscription init — subscribe to `TOPIC_HIL_RESPONSE` or piggyback on existing `_on_hil_request` by detecting `pending_decision_id` in payload.

**Also update `_on_topic_task_suspended` / `_on_task_suspended` (L3646-3866):** When P0.3 is active, `task.awaiting_decision` replaces `task.suspended` → the FSM should NOT transition to CLARIFYING_WORKER (will be removed in P1.1 anyway).

**Total P0.3 lines: ~225.** Tests as listed.

---

### Epic P0.4: Stale World Mitigation

**Design:** `conversation_continuity_and_hitl.md` §17.1
**Files:** `k1/concierge/react/loop.py`, `k1/concierge/actors/back.py`
**Prerequisite:** P0.1 (must have `paused_at_epoch_ms` and `data_freshness_ttl_seconds` on ReActCheckpoint)
**Lines:** ~45

---

#### FILE 1: `k1/concierge/react/loop.py`

**Add 3 parameters to react_loop() — after L1065 (completed_tool_arg_keys), before L1066 (reasoning_effort):**

```python
    completed_tool_arg_keys: set[str] | None = None,
    loop_events: list[dict[str, Any]] | None = None,     # P0.2
    enforce_refresh: bool = False,                         # ← P0.4
    paused_at_epoch_ms: int = 0,                             # ← P0.4
    data_freshness_ttl_seconds: int = 3600,                # ← P0.4
    reasoning_effort: str | None = "auto",
```

~4 lines. NOTE: P0.2's `loop_events` is inserted at L1065+. These go AFTER that.

**Freshness warning injection — after drain_control_events check (~L1440):**

```python
    # After cancellation_check() and drain_control_events():
    if enforce_refresh:
        elapsed_s = (time.time() - paused_at_epoch_ms / 1000.0)
        freshness_prompt = (
            f"\n\n[DATA FRESHNESS WARNING]\n"
            f"Data obtained ~{elapsed_s:.0f}s ago (TTL: {data_freshness_ttl_seconds}s). "
            f"MUST call validation/refresh capability before taking action "
            f"(e.g., invoke_capability for check_availability, recall_memory).\n"
            f"[/DATA FRESHNESS WARNING]\n"
        )
        messages.append(ModelMessage(role="system", content=freshness_prompt))
        _record_loop_event("refresh_enforced", iteration, {
            "elapsed_seconds": elapsed_s,
            "ttl_seconds": data_freshness_ttl_seconds,
        })
        enforce_refresh = False  # one-shot prompt injection
```

~15 lines. Uses `time.time()` (epoch) for durable staleness calculation.

**⚠️ PROMPT-ONLY IS NOT SUFFICIENT.** The LLM may ignore the warning and execute stale action.
**P1.4g dispatcher gate (control_templates.py):** The tool dispatcher MUST reject side-effecting
tool calls when `enforce_refresh` was set and no refresh receipt exists yet:

```
STALE_CHECKPOINT → action request rejected with REFRESH_REQUIRED
→ refresh succeeds → freshness receipt recorded → action allowed
```

The gate lives in the dispatcher's 7-step pipeline (dispatcher.py L508-781), after Step 1
(allowlist check) and before Step 4 (safety band). Reject stale tool calls unless the tool
is itself a validation/refresh operation.

---

#### FILE 2: `k1/concierge/actors/back.py`

**In _resolve_needs_human_in_process() — after checkpoint decode (after L1099):**

```python
    # After: cp_suspension_count = cp.suspension_count
    # ADD:
    enforce_refresh = False
    cp_paused_at_epoch_ms = 0
    cp_data_freshness_ttl = 3600
    if cp is not None:
        cp_paused_at_epoch_ms = getattr(cp, "paused_at_epoch_ms", 0) or 0
        cp_data_freshness_ttl = getattr(cp, "data_freshness_ttl_seconds", 3600) or 3600
        if cp_paused_at_epoch_ms > 0:
            elapsed_s = time.time() - cp_paused_at_epoch_ms / 1000.0
            if elapsed_s > cp_data_freshness_ttl:
                enforce_refresh = True
```

**Pass to react_loop() resume call (L1188-1202) — add 3 kwargs:**

```python
    current = await react_loop(
        # ... existing params ...
        completed_tool_arg_keys=completed_arg_keys or None,
        loop_events=cp.scratchpad.get("loop_events") if cp is not None else None,  # P0.2
        enforce_refresh=enforce_refresh,                                             # P0.4
        paused_at_epoch_ms=cp_paused_at_epoch_ms,                                    # P0.4
        data_freshness_ttl_seconds=cp_data_freshness_ttl,                            # P0.4
    )
```

**Same pattern in _handle_react_step_or_submit() (~L2072)** — extract freshness from react_checkpoint, pass to react_loop().

**Total P0.4 lines: ~45.**

---

### Epic P0.5: Belief Globality Enforcement

**Design:** `conversation_continuity_and_hitl.md` §17.2
**Files:** `k1/concierge/section_update/prompt.py`, `k1/concierge/section_update/plan_compiler.py`
**Lines:** ~30

---

#### FILE 1: `k1/concierge/section_update/prompt.py` — Classifier Prompt

**beliefs_active writing rules (L107-130):** Current rules describe what facts go into beliefs_active vs other sections. No pane/scope rules exist.

**ADD globality rules after L130:**

```python
    # ── P0.5: Globality rules ──
    #
    # GLOBALITY: Facts extracted during scoped conversations (planning, task
    # execution) that should be visible to ALL actors MUST include
    # "global": true in the mutation data.
    #
    # GLOBAL facts (include "global": true):
    #   - Budget constraints: "$3000 total for Hawaii trip"
    #   - Preferences: "User prefers hotels over Airbnbs"
    #   - Decisions: "Hotel A selected for Napa trip"
    #
    # PANE-LOCAL facts (omit "global" or set false):
    #   - Intermediate planning: "Considering 3 hotel options"
    #   - Task-specific context: "Search returned 5 results"
    #
    # When in doubt, set "global": true. Safer to over-share than create
    # context blindness across panes.
```

**Update example JSON in classifier prompt — add `"global": true` to belief mutation example:**

```python
    {
      "section": "beliefs_active",
      "operation": "add_fact",
      "data": {
        "subject": "User",
        "predicate": "has_budget",
        "object": "$3000 for Hawaii trip",
        "confidence": 0.9,
        "source": "planning_pane",
        "global": true                            # ← P0.5
      },
    }
```

---

#### FILE 2: `k1/concierge/section_update/plan_compiler.py` — Diagnostic Gate

**compile() method mutation validation loop (~L150):** After `isinstance(mutation.data, dict)` check, ADD:

```python
    # ── P0.5: Globality enforcement for beliefs ──
    if (
        mutation.section == "beliefs_active"
        and mutation.operation == "add_fact"
        and isinstance(mutation.data, dict)
    ):
        is_global = mutation.data.get("global")
        if is_global is not True:
            diagnostics.append(
                CompileDiagnostic(
                    code="belief_globality_missing",
                    message=(
                        "beliefs_active add_fact missing 'global': True. "
                        "Scoped facts without global=True may create "
                        "context blindness across panes (§10.4)."
                    ),
                    section=mutation.section,
                    operation=mutation.operation,
                    index=index,
                )
            )
            # WARNING only — mutation still proceeds
```

~18 lines. **This is a diagnostic WARNING, not a rejection.** The LLM may forget. The mutation still proceeds. Dormant today (Planner has no write path). Activates automatically when Planner gains write access.

**Total P0.5 lines: ~30.**

### Epic P0.6: Garbage Collection Worker

**Design:** `conversation_continuity_and_hitl.md` §17.3
**Files:** `k1/concierge/hitl/gc.py` (NEW), `k1/concierge/config/kernel.py`, `k1/kernel/service.py`
**Lines:** ~89

---

#### Background — Kernel Service Patterns

**3 existing background task patterns in `service.py`:**

| Worker | Launch | Shutdown Pattern |
|---|---|---|
| **Planner Agent** | L2327: `asyncio.create_task(self._planner.start(), name="planner-agent")` + `add_done_callback` | L653-662: `task.cancel()` → `await task` → catch CancelledError → `= None` |
| **Tool SSE Consumer** | L2033: `asyncio.create_task(self._consume_tool_sse(), name="k1-tool-sse-consumer")` | L743-751: same cancel/await/None pattern |
| **Section Update Worker** | L3565: `section_update_worker.start()` — synchronous, per-session, NOT asyncio.create_task | Per-session teardown |

**Canonical shutdown macro:**

```python
if self._<task> is not None:
    try:
        self._<task>.cancel()
        try:
            await self._<task>
        except (asyncio.CancelledError, Exception):
            pass
    except Exception as exc:
        errors.append(exc)
    self._<task> = None
```

**Session dict pattern:** `self._sessions: dict[str, SessionInstance]` — sessions created in `create_session()`. Each `SessionInstance` has `.ss` (SessionStateManager) and `.task_state` (accessible via `ss.task_state`).

---

#### Task 1: Create `PendingDecisionsGC` class

**File:** `k1/concierge/hitl/gc.py` (NEW)

```python
class PendingDecisionsGC:
    def __init__(self, *, task_state=None, ledger=None,
                 archive_after_s=7*24*3600, purge_after_s=30*24*3600,
                 sweep_interval_s=300.0):
        self._task_state = task_state
        self._ledger = ledger
        self._archive_after_s = archive_after_s
        self._purge_after_s = purge_after_s
        self._sweep_interval_s = sweep_interval_s
        self._task: asyncio.Task | None = None
        self._shutdown = False
        self._session_task_states: dict[str, Any] = {}  # session_id → TaskStateSection

    async def start(self) -> None:
        if self._task is not None: return
        self._shutdown = False
        self._task = asyncio.create_task(self._sweep_loop(), name="pending-decisions-gc")

    async def stop(self) -> None:
        self._shutdown = True
        if self._task is not None:
            self._task.cancel()
            try: await self._task
            except (asyncio.CancelledError, Exception): pass
            self._task = None

    async def _sweep_loop(self) -> None:
        while not self._shutdown:
            try:
                await asyncio.sleep(self._sweep_interval_s)
                if self._shutdown: return
                await self._sweep()
            except asyncio.CancelledError: return
            except Exception:
                logger.exception("PendingDecisionsGC sweep failed")

    async def _sweep(self) -> None:
        for session_id, task_state in list(self._session_task_states.items()):
            try: await self._sweep_session(session_id, task_state)
            except Exception:
                logger.exception("GC sweep failed session=%s", session_id)

    def register_session(self, session_id: str, task_state: Any) -> None:
        self._session_task_states[session_id] = task_state

    def unregister_session(self, session_id: str) -> None:
        self._session_task_states.pop(session_id, None)
```

~60 lines.

**Sweep logic per session:** Iterates `task_state.get_all()`. For each task with `pending_decision_status == "resolved"` and age > 7d → write ledger, call `task_state.archive_decision(task_id)` (public method: transitions to `archived`, clears large snapshots). For `pending_decision_status == "awaiting_user"` and age > 30d → write ledger, call `task_state.expire_decision(task_id)` (public method: transitions to `expired`). **NEVER delete the task itself — only transition decision state and clear snapshots.** The existing `prune_completed()` (task_state.py:564) already handles TERMINAL task cleanup separately.

**Ledger write:** Uses `HILLedgerAdapter._safe_write(event_type, payload)` — tries `write_event()`, `append()`, `write()` in order. Best-effort, never raises.

---

#### Task 2: Add GC config to KernelConfig

**File:** `k1/concierge/config/kernel.py`

Add 4 fields after existing background-worker config patterns:

```python
    # ── P0.6: Pending decisions GC ──
    pending_decisions_gc_enabled: bool = False
    pending_decisions_gc_interval_s: float = 300.0
    pending_decisions_gc_archive_after_days: int = 7
    pending_decisions_gc_purge_after_days: int = 30
```

---

#### Task 3: Wire GC into kernel lifecycle

**File:** `k1/kernel/service.py`

**Launch (after L2337, after Planner launch in `_startup_tier1()`):**

```python
    if self._config.pending_decisions_gc_enabled:
        from k1.concierge.hitl.gc import PendingDecisionsGC
        self._pending_decisions_gc = PendingDecisionsGC(
            ledger=getattr(self._hil_service, "_ledger", None) if self._hil_service else None,
            archive_after_s=self._config.pending_decisions_gc_archive_after_days * 86400,
            purge_after_s=self._config.pending_decisions_gc_purge_after_days * 86400,
            sweep_interval_s=self._config.pending_decisions_gc_interval_s,
        )
        await self._pending_decisions_gc.start()
```

**Session wiring (in `create_session()` after session creation):**

```python
    if self._config.pending_decisions_gc_enabled and hasattr(self, "_pending_decisions_gc"):
        gc = self._pending_decisions_gc
        if gc is not None:
            gc.register_session(session_id, session.ss.task_state)
```

**Shutdown (in `shutdown()` method, alongside Planner/Tool SSE shutdown):**

```python
    if hasattr(self, "_pending_decisions_gc") and self._pending_decisions_gc is not None:
        await self._pending_decisions_gc.stop()
```

---

## MILESTONE P1 — Core Architecture

### Epic P1.1: CLARIFYING_WORKER Removal + RELAY/RESOLVE/WEAVE → STANDARD

**⚠️ BUILD ORDER: Execute AFTER P1.4, behind feature flag.** P1.1 removes the old HITL relay/resolve system. P1.4 must be operational first — otherwise the system has no HITL path (no CLARIFYING_WORKER state AND no persistent Front session = broken). Build P1.4 foundation behind `k1_concierge_persistent_front` feature flag → shadow execution → cutover → THEN remove old modes and state.

**Design:** `conversation_continuity_and_hitl.md` §13
**Files:** 7 files | **Lines:** ~35

---

#### FILE 1: `k1/concierge/fsm/states.py`

**REMOVE L42:** `CLARIFYING_WORKER = auto()` — comment out, add migration note.

**DO NOT TOUCH L41:** `CLARIFYING_USER = auto()` — stays.

**ConciergeState: 10 values (was 11).**

---

#### FILE 2: `k1/concierge/fsm/transition_table.py`

**REMOVE 5 entry rows (re-route to COMPANIONING):**

| L | Change |
|---|---|
| L87 | `LISTENING + TRIGGER_DEFERRED_HITL → COMPANIONING` (was CLARIFYING_WORKER) |
| L101 | `COMPANIONING + TOPIC_TASK_SUSPENDED → COMPANIONING` (stay) |
| L102 | `COMPANIONING + TOPIC_HIL_REQUEST → COMPANIONING` (stay) |
| L121 | `PROGRESSING + TOPIC_TASK_SUSPENDED → COMPANIONING` |
| L122 | `PROGRESSING + TOPIC_HIL_REQUEST → COMPANIONING` |

**REMOVE entire CLARIFYING_WORKER sub-table (L133-L141):** 1 self-loop + 4 exit rows.

**REMOVE CLARIFYING_WORKER from FULL_GUARD_TABLE (L437-L469):** Delete entire guard block.

**Also remove CLARIFYING_WORKER references from other states' guard rows:** L319 (COMPANIONING), L355 (PROGRESSING).

---

#### FILE 3: `k1/concierge/fsm/response_final_table.py`

**REMOVE Branch 11 (L219-L231):** `CLARIFYING_WORKER + has_active_tasks → STAY`

**REMOVE Branch 12 (L232-L241):** `CLARIFYING_WORKER + no active → LISTENING`

**REMOVE doc-comment table rows L83-84.**

---

#### FILE 4: `k1/concierge/fsm/controller.py` — 20 references

| L | Change |
|---|---|
| L1364 | Comment reference — no code change needed, update text |
| L1866 | Comment reference — update |
| L1912-1927 | **DELETE** `if self._state == ConciergeState.CLARIFYING_WORKER:` block in `_on_user_input()` |
| L2765 | Comment reference — update |
| L3579-3582 | **REMOVE** `CLARIFYING_WORKER` from `_on_task_failed` state-whitelist tuple |
| L3666-3827 | Comment/log references — update, transition target changed |
| L4306-4507 | **REMOVE** CLARIFYING_WORKER transition from `_on_hil_request` — non-inline kinds become NO-OP |
| L4603 | Comment reference — update |
| L4895-4943 | **CHANGE** `_surface_deferred_hitl` transition target to COMPANIONING |
| L5617 | **CHANGE** proactive fill suppression from `self._state == CLARIFYING_WORKER` to `self._has_pending_hitl()` only |

---

#### FILE 5: `k1/concierge/prompt/mode.py`

**REMOVE HITL_RELAY and HITL_RESOLVE from PromptMode enum.** Also remove any FSM-state-based mode detection that references CLARIFYING_WORKER (mode.py lines referencing `"CLARIFYING_WORKER"` → return HITL_RELAY/HITL_RESOLVE).

---

#### FILE 6: `k1/concierge/prompt/builder.py` (sections.py imports)

**REMOVE from MODE_SECTIONS:** HITL_RELAY entry (7 sections), HITL_RESOLVE entry (9 sections), WEAVE entry (9 sections).

**REMOVE from SS_READ_CONFIGS:** HITL_RELAY at L112, HITL_RESOLVE at L119, WEAVE at L139.

---

#### FILE 7: `k1/concierge/actors/front.py`

**REMOVE thin-front HITL_RELAY path (BP-19, L1718-1810):** Delete entire zero-LLM pass-through block.

**REMOVE thin-front HITL_RESOLVE path (BP-20):** Delete classification call block.

**REMOVE WEAVE mode post-loop processing:** Delete mode-specific logic from `front_handler()`.

**REMOVE `task.resume` auto-emission (L1995-2040):** Delete auto-emit block.

---

### Epic P1.2: UI Decision Cards

**Design:** `conversation_continuity_and_hitl.md` §13.2.1
**Files:** `ui/web/static/app.js`, `ui/web/static/styles.css`
**Lines:** ~220

---

#### FILE 1: `ui/web/static/app.js`

**1a. Add `pendingDecisions: []` to state object (L112):**

```js
    switching: false,
    pendingDecisions: [],  // ← P1.2
};
```

**1b. Add 3 new WS cases to handleMessage() (after L1796, before L1797):**

```js
        case "decision_pending":    handleDecisionPending(msg); break;    // P1.2
        case "decision_resolved":   handleDecisionResolved(msg); break;   // P1.2
        case "decision_superseded": handleDecisionSuperseded(msg); break; // P1.2
```

**1c. Implement handlers (after L2195, after handleHilPresented block):**

`handleDecisionPending(msg)` — calls `finishStreaming(true)`, builds `.message-row--decision` with `.decision-card` child, iterates `msg.options` to build `.decision-option` buttons with click listeners, appends to `#messages`, pushes to `state.pendingDecisions`, arms input via `data-hil-active` pattern.

`handleDecisionResolved(msg)` — finds card by `#decision-{id}`, transitions to `answered` state via `dataset.decisionState`, highlights selected option, removes from `state.pendingDecisions`, clears HIL markers from input.

`handleDecisionSuperseded(msg)` — collapses card to `superseded` state.

`_onDecisionOptionClick(decisionId, optionIndex)` — optimistic UI (mark answered, disable buttons), sends `hil_response` WS message via existing `send()` function.

**1d. Home dashboard wiring (in `_homeDecisionItems()` or `_renderHomeDecisions()` at L1422):**
Append `state.pendingDecisions` entries to decision items array, capped at 5 total.

---

#### FILE 2: `ui/web/static/styles.css`

**Adapt from existing `.home-decision-row` (L1879)** — `box-shadow: inset 4px 0 0 var(--brand-blue)`, `background: var(--bg-card)`, `border-radius: var(--r-lg)`.

**New CSS blocks (~100 lines):**

- `.decision-card` + 3 state modifiers (`[data-decision-state="pending/answered/superseded"]`)
- `.decision-option` + `:hover` + `--selected`
- `.message-row--decision`
- `.decision-card__header`, `__badge`, `__age`, `__question`, `__options`, `__footer`, `__context`
- `.decision-option__label`, `__detail`

All use existing `--var()` token system. Dark mode auto-remaps via `html[data-theme="dark"]`.

---

### Epic P1.3: Handoff Quality — narrative_summary + remaining_work + action_receipt

**Design:** `conversation_continuity_and_hitl.md` §8.3
**Files:** `k1/concierge/prompt/back_prompt.py`, `k1/concierge/tools/schemas_back.py`, `k1/concierge/prompt/builder.py`
**Lines:** ~61

---

#### FILE 1: `k1/concierge/prompt/back_prompt.py`

**BACK_SYSTEM_PROMPT structure (L47-188):** 8 sections. `== RESULT FORMAT ==` at L167-176.

**Add 3 new directives after L176 (in `== RESULT FORMAT ==` section):**

```
    narrative_summary: Natural-language summary of what was found/done and
      why. Write as if briefing a colleague. Under 3 sentences. Include
      what you found, why it matters, and a recommendation if applicable.
      Front may quote or paraphrase this when weaving results.

    remaining_work: What remains after this decision/task. Provides
      continuity context. Required for needs_human, omit for complete.

    action_receipt: NOT authored by Back's LLM. Back submits ONLY receipt_id
      from the tool dispatcher's invoke_capability result. The dispatcher
      produces the receipt at execution time: ActionReceipt(receipt_id,
      tool_call_id, provider, confirmation_id, completed_at_epoch_ms,
      request_hash, response_hash). Back references receipt_id in
      submit_result — never manufactures receipt fields.

      Schema: add "receipt_id" (string, optional) to SUBMIT_RESULT_SCHEMA.
      Remove the LLM-authored "action_receipt" object from the schema.
      Dispatcher stores receipt in ToolResult.data["action_receipt"] at
      dispatch time (dispatcher.py Step 5, L713-745).
```

**The `build_back_prompt()` function (L225-391):** `.format()` call at L373-391. No change needed here — the directives are in the template, the variables come from Back's submit_result args (not from prompt builder params).

---

#### FILE 2: `k1/concierge/tools/schemas_back.py`

**SUBMIT_RESULT_SCHEMA (L328-400):** 10 properties. `"required"` array at L391 contains only `["result_type"]`.

**Add `receipt_id` property before `"required"` (after L390, before L391):**

```python
    "receipt_id": {
        "type": "string",
        "description": (
            "Reference to the ActionReceipt produced by the tool dispatcher "
            "during invoke_capability execution. Back must NOT manufacture "
            "receipt fields — only reference the receipt_id from tool results."
        ),
    },
```

~8 lines. (Note: `narrative_summary` and `remaining_work` already added in P0.3.)

**Dispatcher-side receipt creation** (new in dispatcher.py Step 5, after L745):

```python
# After successful tool execution, produce ActionReceipt:
if result.is_ok() and hasattr(result, "data"):
    result.data["action_receipt"] = {
        "receipt_id": str(uuid.uuid4()),
        "tool_call_id": tc.id,
        "provider": tool_name,
        "confirmation_id": result.data.get("confirmation_id", ""),
        "completed_at_epoch_ms": int(time.time() * 1000),
        "request_hash": _hash_args(tc.arguments),
        "response_hash": _hash_dict(result.data),
    }
```

---

#### FILE 3: `k1/concierge/prompt/builder.py`

**Front system prompt template variables:**

The `PROMPT_SECTIONS` dict contains Front's system prompt sections. Add `{back_narrative}` and `{back_remaining}` as template variables in the appropriate weaving/presentation section.

**Wire in `build()` (after L1250, after {open_gaps_list} interpolation):**

```python
    back_narrative = ""
    back_remaining = ""
    task_artifacts = self._safe_get_ss_section(ss, "task_artifacts")
    if task_artifacts is not None:
        latest = getattr(task_artifacts, "latest", None)
        if latest is not None:
            back_narrative = getattr(latest, "narrative_summary", "") or ""
            back_remaining = getattr(latest, "remaining_work", "") or ""
    system_prompt = system_prompt.replace("{back_narrative}", back_narrative)
    system_prompt = system_prompt.replace("{back_remaining}", back_remaining)
```

---

### Epic P1.4: Persistent Front Session

**Design:** `conversation_continuity_and_hitl.md` §9, §10
**Files:** 8 new files, 3 modified | **Lines:** ~460

**8 sub-epics:**

| Sub | File | Lines |
|---|---|---|
| P1.4a | `k1/concierge/session/actor.py` (NEW) — FrontSessionActor class | ~60 |
| P1.4b | `k1/concierge/session/episode.py` (NEW) — run_front_episode() bounded runner | ~80 |
| P1.4c | `k1/concierge/session/frame.py` (NEW) — ConversationFrame persistence + crash recovery | ~80 |
| P1.4d | `k1/concierge/session/events.py` (NEW) — ConversationEvent sequencing + dedup | ~50 |
| P1.4e | `k1/sessionstate/sections/obligations.py` (NEW) — ConversationObligation ledger | ~60 |
| P1.4f | `k1/sessionstate/sections/task_state.py` — decision atomic transitions (CAS) | ~30 |
| P1.4g | `k1/concierge/session/control_templates.py` (NEW) — safe control messages | ~50 |
| P1.4h | `k1/concierge/session/compaction.py` (NEW) — context compaction | ~50 |

**FrontSessionActor** wraps ConversationFrame, calls run_front_episode() per event batch, persists frame after each episode.

**run_front_episode()** is a bounded react_loop with per-episode max_iterations and TurnCapabilityEnvelope.

**ConversationFrame** is the durable snapshot: session_id, system_prompt_version, messages, cursor, active_tasks, pending_decisions, obligations, event_cursor, ss_snapshot_version.

**ConversationEvent** carries: event_id, session_sequence, task_id, task_sequence, causation_id, correlation_id, idempotency_key, event_type, payload.

**ConversationObligation** lifecycle: DETECTED → DISPATCHED → WAITING_FOR_RESULT → ANSWER_READY → ANSWERED | FAILED_EXPLICITLY | CANCELLED.

**Decision atomic transitions:** `transition_decision(decision_id, from_status, to_status) -> bool` — compare-and-swap on AWAITING_USER → RESOLVING → RESOLVED.

**Control event safe messages:** `CONTROL_EVENT_DIRECTIVES` + `build_control_message()` — trusted directive + EVENT_DATA_JSON separated, schema-validated.

**Context compaction:** When messages exceed threshold, compact oldest entries preserving obligation references, pending decisions, active commitments in structured prefix.

---

## MILESTONE P2 — Polish

### Epic P2.1: FSM Visual Mapping

**Design:** `conversation_continuity_and_hitl.md` §13.2.3
**Files:** `ui/web/static/app.js`, `ui/web/static/styles.css`
**Lines:** ~45

---

#### Current State

**setFsmBadge() at L3263-3266 — CURRENT:**

```js
function setFsmBadge(stateName) {
    state.fsmState = stateName;
    if (dom.fsmState) dom.fsmState.textContent = stateName;
}
```

Only touches `#fsm-state` text. Does NOT manipulate `.fsm-dot` at all. No conditional styling.

**.fsm-dot CSS at L2558-2569:**

```css
.fsm-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--brand-blue);
    box-shadow: 0 0 6px var(--brand-blue);
    animation: pulse 2s ease-in-out infinite;
}
```

Hardcoded `var(--brand-blue)` — never changes color. Always pulsing.

**.fsm-badge CSS at L2545-2556:** Uses `var(--brand-blue-soft-2)` background, `var(--brand-blue)` text.

**#chat-area:** No existing border-top styling. No `.chat-area--*` modifier classes exist.

**#message-input:** Placeholder set by existing code patterns (`data-hil-active`). No per-FSM-state placeholder logic.

---

#### Changes

**1a. Extend setFsmBadge() (app.js L3263-3266):**

```js
const FSM_VISUAL_MAP = {
    "LISTENING":          { dot: "var(--brand-blue)",      area: "",               hint: "Tell me what needs sorting." },
    "DISPATCHING":        { dot: "var(--brand-blue)",      area: "chat-area--dispatched", hint: null },
    "COMPANIONING":       { dot: "var(--color-green)",     area: "chat-area--companioning", hint: "I'm working on it..." },
    "PROGRESSING":        { dot: "var(--brand-blue)",      area: "chat-area--working", hint: null },
    "DELIVERING":         { dot: "var(--color-green)",     area: "",               hint: null },
    "CLARIFYING_USER":    { dot: "var(--color-yellow)",    area: "chat-area--question", hint: "I need your input on this." },
    "CANCELLING":         { dot: "var(--color-red)",       area: "",               hint: null },
    "INTERRUPT_HANDLING": { dot: "var(--color-purple)",    area: "chat-area--interrupted", hint: null },
    "PROACTIVE_WAKE":     { dot: "var(--brand-blue)",      area: "",               hint: null },
    "WEAVING":            { dot: "var(--color-teal)",      area: "chat-area--weaving", hint: null },
};  // 10 entries (CLARIFYING_WORKER removed per P1.1)

function setFsmBadge(stateName) {
    state.fsmState = stateName;
    if (dom.fsmState) dom.fsmState.textContent = stateName;

    const m = FSM_VISUAL_MAP[stateName];
    if (!m) return;

    // Dot color (L2558: overrides --brand-blue via inline style or CSS var swap)
    const dot = document.querySelector(".fsm-dot");
    if (dot) dot.style.backgroundColor = m.dot;

    // Chat area border class
    const area = document.getElementById("chat-area");
    if (area) {
        area.classList.remove("chat-area--dispatched", "chat-area--companioning",
            "chat-area--working", "chat-area--question",
            "chat-area--interrupted", "chat-area--weaving");
        if (m.area) area.classList.add(m.area);
    }

    // Input placeholder (only if no HIL active)
    const input = dom.input;
    if (input && m.hint && input.dataset.hilActive !== "true") {
        input.placeholder = m.hint;
    }

    applyShellState({ viewId: state.currentView, weather: state.householdWeather });
}
```

**1b. CSS — chat-area border classes (styles.css, new block):**

```css
.chat-area--question      { border-top: 2px solid var(--color-yellow); transition: border-color var(--t-norm); }
.chat-area--companioning  { border-top: 2px solid var(--color-green); transition: border-color var(--t-norm); }
.chat-area--working       { border-top: 2px solid var(--brand-blue); transition: border-color var(--t-norm); }
.chat-area--interrupted   { border-top: 2px solid var(--color-purple); }
.chat-area--weaving       { border-top: 2px solid var(--color-teal); }
.chat-area--dispatched    { border-top: 2px solid var(--brand-blue); }
```

**Existing tokens confirmed (from :root, L6-104):**
`--brand-blue: #4f46e5`, `--color-green: #16a34a`, `--color-yellow: #ca8a04`, `--color-red: #dc2626`, `--color-purple: #9333ea`, `--color-teal: #0d9488`. All remapped in `html[data-theme="dark"]` (L12585+). **No new tokens needed.**

**Total P2.1: ~45 lines.**

---

### Epic P2.2: Actor Source Labels

**Design:** `conversation_continuity_and_hitl.md` §13.2.4
**Files:** `ui/web/static/app.js`, `ui/web/static/styles.css`
**Lines:** ~11

---

#### Current State

**addMessageRow() at L2612:** `opts.label` renders as inline `<span>` with hardcoded `style="color:var(--brand-blue)"` at L2639-2642. Inserted into `.message-meta` at L2650:

```html
<div class="message-meta">Concierge${labelTag} · ${formatTime()}</div>
```

**.message-label-cue CSS at L3450-3456 exists but is NEVER used in JS:**

```css
.message-label-cue {
    color: var(--brand-blue);
    font-size: 10px; font-weight: 800;
    margin-left: 6px; text-transform: uppercase;
}
```

This is a dead CSS rule — confirmed: zero references to `message-label-cue` in `app.js`.

---

#### Changes

**2a. Add source CSS variants (styles.css, after L3456):**

```css
.message-label-cue--back    { color: var(--color-purple); }
.message-label-cue--planner { color: var(--color-teal); }
/* Front keeps default var(--brand-blue) */
```

**2b. Extend addMessageRow() (app.js L2639-2642):**
Replace inline style with CSS class:

```js
const sourceClass = opts.source === "back" ? "message-label-cue--back"
                 : opts.source === "planner" ? "message-label-cue--planner"
                 : "";
const labelTag = opts.label
    ? `<span class="message-label-cue ${sourceClass}">${opts.label}</span>`
    : "";
```

Alternatively, use the existing inline pattern with dynamic color from `FSM_VISUAL_MAP`:

```js
const labelColor = opts.source === "back" ? "var(--color-purple)"
                 : opts.source === "planner" ? "var(--color-teal)"
                 : "var(--brand-blue)";
const labelTag = opts.label
    ? `<span style="background:rgba(37,99,235,0.1);color:${labelColor};padding:1px 6px;border-radius:6px;font-size:10px;margin-left:4px">${opts.label}</span>`
    : "";
```

**Pass `opts.source` from callers:** When Back emits a message, `addAssistantMessage(text, { source: "back" })`. When Planner emits, `{ source: "planner" }`. Default (no source) = Front = `var(--brand-blue)`.

**Total P2.2: ~11 lines.**

---

### Epic P2.3: Voice Consistency — Shared Identity Block

**Design:** `conversation_continuity_and_hitl.md` §10.7
**Files:** `k1/concierge/prompt/builder.py`, `k1/concierge/prompt/back_prompt.py`, `k1/planner/`
**Lines:** ~20

---

#### Current State

**Front identity** is `FRONT_ROLE_CONTRACT` in `sections.py` (L34-72) — ~40 lines. Imported by builder.py at L49 via `PROMPT_SECTIONS`. Key text: "You are the user-visible conversational surface of the kernel. You are the one voice the user experiences."

**Back identity** is `== IDENTITY ==` in `back_prompt.py` (L48-66) — ~18 lines. "You are the Worker. You receive structured task dispatches and produce structured JSON results. You are a pure executor."

**Planner identity** — 5 separate string literals across 3 files:

- `sketch_service.py:528` — `"You are a planning engine.\n"`
- `sketch_service.py:1201` — `"You are a MICRO-REPLAN planning engine.\n"`
- `expand_service.py:710` — `"You are the EXPAND stage planner.\n"`
- `expand_service.py:1700` — `"You are the MICRO-EXPAND stage planner.\n"`
- `validate_service.py:191` — `"You are the VALIDATE stage arbiter for a plan execution pipeline.\n"`

Back and Planner have NO shared identity framing with Front. Back is explicitly "NOT a conversationalist." Planner is a pure engine.

---

#### Changes

**3a. Extract shared identity constant (builder.py or new `identity.py`):**

```python
SHARED_IDENTITY_BLOCK = """
You are part of the K1 Concierge system serving a family. You share one voice,
one set of values, and one relationship with the user. You serve with warmth,
competence, and discretion. Family context, preferences, and safety constraints
apply to everything you do.
"""
```

**3b. Add to Back's IDENTITY section (back_prompt.py, after L66):**
Replace current `== IDENTITY ==` preamble with shared block + Back-specific role:

```
== IDENTITY ==
{shared_identity}

Your specific role: You are the Worker — the task execution engine...
[existing "What you ARE / What you are NOT / What you produce" content preserved]
```

**3c. Add to Planner prompts (5 locations):**
Prepend shared identity before each Planner stage-specific role. Each stage keeps its specific instruction ("planning engine", "EXPAND stage", "VALIDATE stage arbiter").

**Total P2.3: ~20 lines** (extract constant, add to Back, add to 5 Planner locations).

---

### Epic P2.4: Accessibility Audit

**Design:** `conversation_continuity_and_hitl.md` §13.8
**Files:** `ui/web/static/`
**Lines:** ~5

---

#### Current State

**Existing accessibility infrastructure:**

- `aria-live="polite"` on `#messages` — already exists
- `aria-label` on 44 elements — established pattern (L1882, L2717, L2800, L2957, L2981, L3667, L3696, L3708)
- `:focus-visible` global rule confirmed in styles.css
- `<button>` elements for decision options (P1.2) — native keyboard navigation via Tab + Enter
- `<details>` element for FSM badge — native expand/collapse

---

#### Verification Checklist (no new code, just verify)

| # | Check | Where |
|---|---|---|
| 1 | `.decision-option` buttons have `aria-label` attributes | P1.2 code — add `aria-label="Select: {option.label}"` |
| 2 | Planning pane toggle uses `aria-expanded` | P3.1 code — add to toggle button |
| 3 | Dark mode renders correctly | All tokens auto-remap via `html[data-theme="dark"]` L12585+ — verified |
| 4 | Keyboard navigation: Tab → Enter on decision options | Native `<button>` behavior — verified |
| 5 | Decision card states use `data-decision-state` attribute | P1.2 CSS — use attribute selectors, not color alone |
| 6 | `aria-live="polite"` on `#messages` | Already exists — new decision cards announce naturally |

**Total P2.4: ~5 lines** (mostly verifying existing code + 2 aria-label additions in P1.2 code).

---

## MILESTONE P3 — Future (~153 lines)

### Epic P3.1: Planning Pane

**Design:** `conversation_continuity_and_hitl.md` §13.2.2, §17.4
**Files:** `ui/web/static/app.js`, `ui/web/static/styles.css`, `ui/web/static/index.html`
**Lines:** ~88

---

#### Current State

**No planning pane exists.** The chat is a single `#messages` stream inside `#chat-area` (index.html L324). `#chat-area` is a flex column: welcome → messages → streaming → toast.

**Existing collapsible pattern: `#activity-rail`** (index.html L566-586) — fixed right-side panel with:

- `<aside>` with `id`, base class, collapsed modifier
- Toggle `<button>` with dot + text + status badge
- Panel with header (kicker + h2 + close) + empty state + list

**CSS pattern (styles.css L580-807):** `.activity-rail` uses `position:fixed; right:0; transform:translateX()` for slide-in/out. `.activity-rail__toggle` is a vertical tab with rotated text. **THIS IS THE PRIMARY PATTERN TO CLONE for the planning pane.**

**Existing modal pattern:** `.modal` + `.modal-dialog` (index.html L596-614) — backdrop + dialog. On mobile, adapt to bottom sheet with `border-radius` only on top + `max-height:90vh`.

**Mobile breakpoint:** `@media (max-width: 900px)` exists in styles.css. Sidebar → icon-only, activity rail → full-width bottom sheet.

**handleMessage() switch (app.js L1777):** New WS cases insert in the existing switch. Current case order: `hil_presented` (L1796), `task_failed` (L1797), Slice 8 (L1798).

---

#### Changes

**1. Add `#planning-pane` DOM (index.html, after `#chat-area` before `#input-form`):**

```html
<section id="planning-pane" class="planning-pane planning-pane--collapsed" aria-label="Planning conversation">
    <div class="planning-pane__toggle">
        <button id="planning-pane-toggle" aria-expanded="false" type="button">
            <span class="planning-pane__dot" aria-hidden="true"></span>
            <span>Planning</span>
            <span id="planning-pane-badge" class="planning-pane__badge hidden">0</span>
        </button>
    </div>
    <div id="planning-pane-body" class="planning-pane__body">
        <div id="planning-messages" class="planning-messages"></div>
    </div>
</section>
```

~10 lines. Clones the activity-rail toggle pattern but as an inline collapsible (not fixed).

**2. CSS (styles.css, new block ~35 lines):**

Adapt from `.activity-rail` pattern but simpler — inline below chat, not fixed right panel:

```css
.planning-pane {
    border-top: 1px solid var(--border-light);
    background: var(--bg-subtle);
    transition: max-height var(--t-slow);
    overflow: hidden;
}
.planning-pane--collapsed { max-height: 44px; }
.planning-pane--expanded  { max-height: 320px; }
.planning-pane__toggle {
    display: flex; align-items: center;
    padding: var(--sp-2) var(--sp-4); cursor: pointer;
}
.planning-pane__dot {
    width: 8px; height: 8px; border-radius: var(--r-full);
    background: var(--color-teal);
    box-shadow: 0 0 6px var(--color-teal);
    margin-right: var(--sp-2);
}
.planning-pane__badge {
    background: var(--color-teal); color: #fff;
    border-radius: var(--r-full); padding: 0 6px;
    font-size: 11px; font-weight: 600; margin-left: auto;
}
.planning-pane__body {
    overflow-y: auto; max-height: 276px;
    padding: var(--sp-3) var(--sp-4);
}
```

**Mobile bottom sheet (@media max-width:900px):**

```css
@media (max-width: 900px) {
    .planning-pane--expanded {
        position: fixed; bottom: 0; left: 0; right: 0;
        max-height: 50vh; z-index: 100;
        border-radius: var(--r-xl) var(--r-xl) 0 0;
        box-shadow: var(--shadow-xl);
    }
}
```

Adapts existing `.modal-dialog` pattern (index.html L596-614).

**3. JS handlers (app.js, after P1.2 decision card handlers):**

`handlePlanningPaneOpen(msg)` — expand pane, clear previous messages, add initial plan summary as `.planning-message--assistant`.

`handlePlanningPaneUpdate(msg)` — append lightweight `.planning-message` to `#planning-messages`.

`handlePlanningPaneClose(msg)` — collapse pane, preserve messages for re-open.

`_addPlanningMessage(kind, text, opts)` — lightweight inline message (not full `.message-row`).

**4. Add 3 WS message types to handleMessage() (app.js ~L1797 area):**

```js
        case "planning_pane_open":    handlePlanningPaneOpen(msg); break;    // P3.1
        case "planning_pane_update":  handlePlanningPaneUpdate(msg); break;  // P3.1
        case "planning_pane_close":   handlePlanningPaneClose(msg); break;   // P3.1
```

**5. Planner degraded inline-first mode (planner files):**

Add exchange counter in Planner. After >3 sustained planning exchanges:

```python
# In PlannerAgent or PipelineController:
if self._planning_exchange_count > 3:
    self._suggest_pane_upgrade()  # emits control event: "I can move this to a planning pane"
```

**Total P3.1: ~88 lines.**

---

### Epic P3.2: Planner Integration

**Design:** `conversation_continuity_and_hitl.md` §5 Layer 5
**Files:** `k1/planner/`, `k1/orchestrator/`
**Lines:** ~65

---

#### Current State

**PlannerAgent** at `planner_agent.py:86` — single-threaded async actor with 7 injected ports. Uses a **sequential 4-stage pipeline** (no react_loop): SKETCH → EXPAND → VALIDATE → COMMIT.

**Two inbound paths:**

- Event bus: subscribes to `k1.planner.plan.request.v1` (L606-615)
- Direct mailbox: Orchestrator's `PlannerAdapter` calls `mailbox.enqueue(request)` directly

**Planner reads SessionState** via `IStateReadPort.read_sections()` (read_only_port.py). Currently only reads `["beliefs_active", "control", "history_recent"]` — called by `ToolCallRouter` for `query_planning_context` tool.

**Planner does NOT read:** `task_state`, `task_artifacts`, `persona`, `scoreboard`, `affective_now`. Planner does NOT write to SessionState at all (PLAN-01 enforced at interface level — write methods don't exist on `IStateReadPort`).

**Planner HITL:** Planner has `IHILPort` injected (hil_port). Uses it for clarification gates during planning. Does NOT write pending decisions to TaskStateEntry — all HITL is in-process via the HIL port.

**Correlation:** Uses `request_id` (uuid4) for plan correlation. No `correlation_id` field. Orchestrator stores `PendingPlanContext` keyed by `request_id`.

**7 ports wired via `PlannerFactory._wire()` (factory.py L485):**

1. `ILLMPort` → LLMGatewayAdapter
2. `IFabricRetrievalPort` → FabricRetrievalAdapter
3. `IFabricRegistryPort` → FabricRegistryAdapter
4. `IStateReadPort` → PlannerStateAdapter (read-only, session_id threaded per call)
5. `IPlannerBridgePort` → PlannerBridgeAdapter
6. `IDeltaEmitPort` → PlannerDeltaBusAdapter
7. `IEventPort` → PlannerEventBusAdapter (publish `plan.ready.v1`, subscribe `plan.request.v1`)

**Kernel wiring (service.py L2257-2335):** S6 constructs all adapters → S6b cross-wires orchestrator → S7 launches `asyncio.create_task(self._planner.start(), name="planner-agent")`.

---

#### Changes

**1. `_read_ss_snapshot(ss)` for Planner (new method, ~30 lines):**

Add snapshot-at-start pattern (same as Back's `_read_ss_snapshot()` in back.py:600-748):

```python
# In PlannerAgent or new planner_ss.py:
async def _read_planner_ss_snapshot(self, ss, session_id: str) -> dict:
    return {
        "beliefs_prompt": await self._state_port.read_sections(
            ["beliefs_active"], session_id=session_id
        ),
        "task_state_prompt": await self._state_port.read_sections(
            ["task_state"], session_id=session_id
        ),
        "persona_prefs": await self._state_port.read_sections(
            ["persona"], session_id=session_id
        ),
        "history_active": await self._state_port.read_sections(
            ["history_active"], session_id=session_id
        ),
    }
```

Extends current 3-section read to 4 sections. Adds `task_state` awareness so Planner knows about in-flight Back tasks.

**2. Planner HITL → TaskStateEntry enrichment (~20 lines):**

When Planner needs user input (clarification during planning):

```python
# In SketchService or ValidateService, after hil_port.clarify():
if response.timed_out:
    # Create pending_decision on TaskStateEntry (same pattern as Back's P0.3)
    await self._state_port.write_sections([{
        "section": "task_state",
        "operation": "set_pending_decision",
        "task_id": task_id,
        "decision_id": f"plan-{request_id}-clarify",
        "question": question,
        "options": options,
        "status": "awaiting_user",
    }])
```

Requires extending `IStateReadPort` to `IStatePort` with write capability, OR using the FSM's TaskBridge.

**3. Orchestrator correlation_id routing (~15 lines):**

Add `correlation_id` field to `PlanRequest` and `CommittedPlan`. Use it to scope planning pane messages on session bus:

```python
# In orchestrator_service.py _dispatch_high():
plan_request.correlation_id = f"plan_{request_id}"

# When routing planning pane messages:
topic = f"k1.session.{session_id}.planning.{correlation_id}.v1"
```

All planning messages carry `correlation_id`. FrontSessionActor (P1.4) routes them to planning pane via control events.

**Total P3.2: ~65 lines.**

---

## Line Budget (Final)

| Milestone | Epics | Lines |
|---|---|---|
| P0 | 6 epics | ~465 |
| P1 | 4 epics | ~776 |
| P2 | 4 epics | ~81 |
| P3 | 2 epics | ~153 |
| **Total** | **16** | **~1,475** |

---

## Files Created (NEW)

| File | Epic |
|---|---|
| `k1/concierge/hitl/gc.py` | P0.6 |
| `k1/concierge/session/actor.py` | P1.4a |
| `k1/concierge/session/episode.py` | P1.4b |
| `k1/concierge/session/frame.py` | P1.4c |
| `k1/concierge/session/events.py` | P1.4d |
| `k1/sessionstate/sections/obligations.py` | P1.4e |
| `k1/concierge/session/control_templates.py` | P1.4g |
| `k1/concierge/session/compaction.py` | P1.4h |

## Files Modified

| File | Epics |
|---|---|
| `k1/concierge/react/checkpoint.py` | P0.1 |
| `k1/concierge/react/loop.py` | P0.2, P0.4, P1.4b |
| `k1/concierge/react/control.py` | P1.4g |
| `k1/concierge/actors/back.py` | P0.1, P0.2, P0.3, P0.4 |
| `k1/concierge/tools/schemas_back.py` | P0.3, P1.3 |
| `k1/concierge/tools/implementations.py` | P0.3 |
| `k1/sessionstate/sections/task_state.py` | P0.3, P1.4f |
| `k1/hil/suspension.py` | P0.3 |
| `k1/concierge/prompt/builder.py` | P0.3, P1.1, P1.3, P2.3 |
| `k1/concierge/prompt/back_prompt.py` | P1.3, P2.3 |
| `k1/concierge/prompt/mode.py` | P1.1 |
| `k1/concierge/fsm/states.py` | P1.1 |
| `k1/concierge/fsm/transition_table.py` | P1.1 |
| `k1/concierge/fsm/response_final_table.py` | P1.1 |
| `k1/concierge/fsm/controller.py` | P0.3, P1.1 |
| `k1/concierge/actors/front.py` | P1.1 |
| `k1/concierge/section_update/prompt.py` | P0.5 |
| `k1/concierge/section_update/plan_compiler.py` | P0.5 |
| `k1/concierge/config/kernel.py` | P0.6 |
| `k1/kernel/service.py` | P0.6 |
| `k1/planner/stages/sketch_service.py` | P2.3 |
| `k1/planner/stages/expand_service.py` | P2.3 |
| `k1/planner/stages/validate_service.py` | P2.3 |
| `ui/web/static/app.js` | P1.2, P2.1, P2.2, P2.4 |
| `ui/web/static/styles.css` | P1.2, P2.1, P2.2 |
| `ui/web/static/index.html` | P3.1 |
| `k1/planner/planner_agent.py` | P3.2 |
| `k1/orchestrator/orchestration/orchestrator_service.py` | P3.2 |

## Test Suite

```bash
# P0
pytest tests/k1/concierge/react/test_checkpoint.py -v
pytest tests/k1/concierge/actors/test_back_hitl.py -v
pytest tests/k1/concierge/tools/test_submit_result.py -v
pytest tests/k1/concierge/hitl/test_pending_decision.py -v
pytest tests/k1/concierge/fsm/test_fsm_hitl.py -v
pytest tests/k1/concierge/hitl/test_gc.py -v
pytest tests/k1/sessionstate/test_beliefs.py -v

# P1
pytest tests/k1/concierge/fsm/test_fsm_hitl.py -v
pytest tests/k1/concierge/session/ -v
pytest tests/k1/concierge/hitl/test_continuity_properties.py -v
pytest tests/ui/test_decision_cards.py -v
pytest tests/k1/concierge/tools/test_submit_result.py -v

# P2 (visual validation — manual + contract tests)
# FSM_VISUAL_MAP completeness: verify every ConciergeState enum has entry
# Actor labels: verify addMessageRow renders correct source class
# Dark mode: verify no hardcoded colors outside --var() system

# P3
pytest tests/ui/test_planning_pane.py -v

# Required new tests (add to suite)
# test_snapshot_survives_timeout_and_resumes
# test_free_text_non_answer_keeps_decision_pending
# test_duplicate_decision_response_resumes_once
# test_card_click_and_free_text_race_has_one_winner
# test_resume_keeps_original_task_id
# test_restart_restores_front_frame_and_obligations
# test_replayed_pending_event_does_not_resurface_card
# test_concurrent_task_artifacts_correlate_by_task_id
# test_stale_side_effect_rejected_until_refresh
# test_action_receipt_sourced_from_dispatcher_not_llm
# test_gc_transitions_decision_without_deleting_task
# test_mixed_turn_creates_obligation_for_every_intent
# test_ui_resolution_rolls_back_on_backend_rejection
```
