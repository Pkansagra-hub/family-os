"""
TaskStateSection - Active Task Tracking (HOT CORE)
=====================================================

MILESTONE: M02 -- Session State Extensions
EPIC: 2.1 TaskState Section

Tracks active, pending, suspended, and recently-completed tasks.
Task state is NEVER demoted to WARM -- critical for HITL recovery.
Completed entries are pruned (deleted) after 10 turns post-presentation.

Budget: 4KB (4096 bytes)
Tier: HOT CORE
Eviction: NEVER (task state must survive full session)

Single Writer: Back LLM (dispatches tasks, updates status)
Readers: Front LLM (progress display), Orchestrator (dependency checks)
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

import flatbuffers

from k1.sessionstate.generated.flatbuffers.K1.SessionState.SectionHeader import (
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.TaskStateEntry import (
    TaskStateEntry as _FBTaskStateEntryClass,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.TaskStateEntry import (
    TaskStateEntryAddAction,
    TaskStateEntryAddCompletedAtMs,
    TaskStateEntryAddDependsOn,
    TaskStateEntryAddDispatchedAtMs,
    TaskStateEntryAddHilSuspensionsCount,
    TaskStateEntryAddPendingHil,
    TaskStateEntryAddPendingHilData,
    TaskStateEntryAddPresentedAtTurn,
    TaskStateEntryAddProgressPct,
    TaskStateEntryAddStatus,
    TaskStateEntryAddTaskId,
    TaskStateEntryEnd,
    TaskStateEntryStart,
    TaskStateEntryStartDependsOnVector,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.TaskStateSection import (
    TaskStateSection as _FBTaskStateSectionClass,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.TaskStateSection import (
    TaskStateSectionAddHeader,
    TaskStateSectionAddLastUpdatedMs,
    TaskStateSectionAddNeverEvict,
    TaskStateSectionAddTasks,
    TaskStateSectionEnd,
    TaskStateSectionStart,
    TaskStateSectionStartTasksVector,
)

# =============================================================================
# TaskStatus Constants
# =============================================================================


class TaskStatus:
    """Task lifecycle statuses with group membership."""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL: FrozenSet[str] = frozenset(
        {"pending", "dispatched", "active", "suspended", "completed", "failed", "cancelled"}
    )
    ACTIVE_GROUP: FrozenSet[str] = frozenset({"dispatched", "active", "suspended"})
    TERMINAL: FrozenSet[str] = frozenset({"completed", "failed", "cancelled"})


# Valid status transitions
_VALID_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.DISPATCHED, TaskStatus.CANCELLED}),
    TaskStatus.DISPATCHED: frozenset(
        {TaskStatus.ACTIVE, TaskStatus.SUSPENDED, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.ACTIVE: frozenset(
        {TaskStatus.SUSPENDED, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.SUSPENDED: frozenset({TaskStatus.ACTIVE, TaskStatus.CANCELLED, TaskStatus.FAILED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


# =============================================================================
# TaskStateEntry Dataclass
# =============================================================================


@dataclass
class TaskStateEntry:
    """
    Single task entry tracked in HOT tier.

    Fields per V2 design Section 5 Schema Extensions:
        task_id: UUID
        action: capability name (e.g. "order_food", "book_ride")
        status: one of TaskStatus values
        dispatched_at_ms: epoch ms when dispatched (0 if not yet)
        completed_at_ms: epoch ms when terminal (0 if not yet)
        depends_on: list of task_ids this task depends on
        progress_pct: 0-100 integer
        pending_hil: True if awaiting human-in-the-loop input
        hil_suspensions_count: number of times suspended for HIL
        presented_at_turn: turn number when result was shown to user (0 = not yet)
        pending_hil_data: M6 E6.1.2 -- serialized HILSubTask dict for crash
                         recovery (None when no HITL pending).
    """

    task_id: str = ""
    action: str = ""
    status: str = TaskStatus.PENDING
    dispatched_at_ms: int = 0
    completed_at_ms: int = 0
    depends_on: List[str] = field(default_factory=list)
    progress_pct: int = 0
    pending_hil: bool = False
    hil_suspensions_count: int = 0
    presented_at_turn: int = 0
    pending_hil_data: Optional[Dict[str, Any]] = None


# Status string → int8 ordinal (must match FlatBuffer schema ordering)
_STATUS_TO_INT8: Dict[str, int] = {
    TaskStatus.PENDING: 0,
    TaskStatus.DISPATCHED: 1,
    TaskStatus.ACTIVE: 2,
    TaskStatus.SUSPENDED: 3,
    TaskStatus.COMPLETED: 4,
    TaskStatus.FAILED: 5,
    TaskStatus.CANCELLED: 6,
}
_INT8_TO_STATUS: Dict[int, str] = {v: k for k, v in _STATUS_TO_INT8.items()}

# Pruning threshold: remove completed tasks N turns after presentation
_PRUNE_AFTER_TURNS: int = 10

# Stale dispatched threshold: 5 minutes default
_STALE_DISPATCHED_MS: int = 300_000


# =============================================================================
# TaskStateSection Implementation
# =============================================================================


class TaskStateSection:
    """
    Task State Section -- HOT CORE, 4KB budget, NEVER EVICT.

    Tracks all active and recently-completed tasks. Single writer is Back LLM.
    Tasks are pruned (not demoted) after completion + presentation + 10 turns.

    ISection protocol:
        name = "task_state"
        tier = "hot"
        budget_bytes = 4096
        can_evict = False
    """

    BUDGET_BYTES: int = 4096  # 4KB
    TIER: str = "hot"
    CAN_EVICT: bool = False
    SECTION_NAME: str = "task_state"
    MAX_TASKS: int = 20  # Safety cap

    __slots__ = ("_tasks", "_last_updated_ms", "_cached_bytes", "_cache_valid")

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskStateEntry] = {}
        self._last_updated_ms: int = int(time.time() * 1000)
        self._cached_bytes: Optional[bytes] = None
        self._cache_valid: bool = False

    # =========================================================================
    # ISection Protocol
    # =========================================================================

    @property
    def name(self) -> str:
        return self.SECTION_NAME

    @property
    def tier(self) -> str:
        return self.TIER

    @property
    def budget_bytes(self) -> int:
        return self.BUDGET_BYTES

    @property
    def can_evict(self) -> bool:
        return self.CAN_EVICT

    def get_size_bytes(self) -> int:
        """Estimate current size. Uses cached serialization if valid."""
        if self._cache_valid and self._cached_bytes is not None:
            return len(self._cached_bytes)
        # Rough estimate: ~120 bytes per task + 50 overhead
        return 50 + len(self._tasks) * 120

    def to_flatbuffer(self) -> bytes:
        builder = flatbuffers.Builder(512)

        tasks = list(self._tasks.values())

        # Pre-create all offsets (must be done before any StartObject)
        entry_offsets: List[int] = []
        for t in tasks:
            task_id_off = builder.CreateString(t.task_id or "")
            action_off = builder.CreateString(t.action or "")
            # pending_hil_data: dict → JSON string (FB schema types it as string)
            hil_data_off = None
            if t.pending_hil_data is not None:
                hil_data_off = builder.CreateString(json.dumps(t.pending_hil_data))
            # depends_on: vector of string offsets
            dep_offsets = [builder.CreateString(d) for d in (t.depends_on or [])]
            TaskStateEntryStartDependsOnVector(builder, len(dep_offsets))
            for off in reversed(dep_offsets):
                builder.PrependUOffsetTRelative(off)
            depends_on_vec = builder.EndVector(len(dep_offsets))

            TaskStateEntryStart(builder)
            TaskStateEntryAddTaskId(builder, task_id_off)
            TaskStateEntryAddAction(builder, action_off)
            TaskStateEntryAddStatus(builder, _STATUS_TO_INT8.get(t.status, 0))
            TaskStateEntryAddDispatchedAtMs(builder, t.dispatched_at_ms)
            TaskStateEntryAddCompletedAtMs(builder, t.completed_at_ms)
            TaskStateEntryAddDependsOn(builder, depends_on_vec)
            TaskStateEntryAddProgressPct(builder, t.progress_pct)
            TaskStateEntryAddPendingHil(builder, t.pending_hil)
            TaskStateEntryAddHilSuspensionsCount(builder, t.hil_suspensions_count)
            TaskStateEntryAddPresentedAtTurn(builder, t.presented_at_turn)
            if hil_data_off is not None:
                TaskStateEntryAddPendingHilData(builder, hil_data_off)
            entry_offsets.append(TaskStateEntryEnd(builder))

        # Tasks vector
        TaskStateSectionStartTasksVector(builder, len(entry_offsets))
        for off in reversed(entry_offsets):
            builder.PrependUOffsetTRelative(off)
        tasks_vec = builder.EndVector(len(entry_offsets))

        # Header
        section_name_off = builder.CreateString(self.SECTION_NAME)
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, section_name_off)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        header_off = SectionHeaderEnd(builder)

        # Root table
        TaskStateSectionStart(builder)
        TaskStateSectionAddHeader(builder, header_off)
        TaskStateSectionAddTasks(builder, tasks_vec)
        TaskStateSectionAddLastUpdatedMs(builder, self._last_updated_ms)
        TaskStateSectionAddNeverEvict(builder, True)
        root = TaskStateSectionEnd(builder)

        builder.Finish(root)
        data = bytes(builder.Output())
        self._cached_bytes = data
        self._cache_valid = True
        return data

    def from_flatbuffer(self, data: bytes) -> None:
        buf = bytearray(data)
        section = _FBTaskStateSectionClass.GetRootAsTaskStateSection(buf, 0)
        self._last_updated_ms = section.LastUpdatedMs() or int(time.time() * 1000)
        self._tasks.clear()
        for i in range(section.TasksLength()):
            fb_entry = section.Tasks(i)
            if fb_entry is None:
                continue
            task_id = (fb_entry.TaskId() or b"").decode("utf-8")
            action = (fb_entry.Action() or b"").decode("utf-8")
            status = _INT8_TO_STATUS.get(fb_entry.Status(), TaskStatus.PENDING)
            depends_on = [
                (fb_entry.DependsOn(j) or b"").decode("utf-8")
                for j in range(fb_entry.DependsOnLength())
            ]
            raw_hil = fb_entry.PendingHilData()
            if raw_hil is not None:
                pending_hil_data: Optional[Dict[str, Any]] = json.loads(raw_hil.decode("utf-8"))
            else:
                pending_hil_data = None
            entry = TaskStateEntry(
                task_id=task_id,
                action=action,
                status=status,
                dispatched_at_ms=fb_entry.DispatchedAtMs(),
                completed_at_ms=fb_entry.CompletedAtMs(),
                depends_on=depends_on,
                progress_pct=fb_entry.ProgressPct(),
                pending_hil=fb_entry.PendingHil(),
                hil_suspensions_count=fb_entry.HilSuspensionsCount(),
                presented_at_turn=fb_entry.PresentedAtTurn(),
                pending_hil_data=pending_hil_data,
            )
            self._tasks[task_id] = entry
        self._cache_valid = False

    def clear(self) -> None:
        """Clear all task state."""
        self._tasks.clear()
        self._last_updated_ms = int(time.time() * 1000)
        self._cache_valid = False

    def get_metadata(self) -> Dict[str, Any]:
        """Section metadata for telemetry."""
        return {
            "section": self.SECTION_NAME,
            "tier": self.TIER,
            "budget_bytes": self.BUDGET_BYTES,
            "current_size_bytes": self.get_size_bytes(),
            "task_count": len(self._tasks),
            "active_count": len(self.get_active()),
            "last_updated_ms": self._last_updated_ms,
        }

    # =========================================================================
    # Write Operations (Single Writer: Back LLM)
    # =========================================================================

    def add_task(
        self,
        action: str,
        task_id: str = "",
        status: str = TaskStatus.PENDING,
        depends_on: Optional[List[str]] = None,
    ) -> TaskStateEntry:
        """Add a new task.

        Args:
            action: Capability name (e.g. "order_food").
            task_id: UUID. Auto-generated if empty.
            status: Initial status (default PENDING).
            depends_on: Task IDs this task depends on.

        Returns:
            The created TaskStateEntry.

        Raises:
            ValueError: If status is invalid or MAX_TASKS reached.
        """
        if status not in TaskStatus.ALL:
            raise ValueError(f"Invalid status: {status}")
        if len(self._tasks) >= self.MAX_TASKS:
            raise ValueError(f"Max tasks ({self.MAX_TASKS}) reached")

        tid = task_id or str(uuid.uuid4())
        now_ms = int(time.time() * 1000)

        entry = TaskStateEntry(
            task_id=tid,
            action=action,
            status=status,
            dispatched_at_ms=now_ms if status == TaskStatus.DISPATCHED else 0,
            depends_on=depends_on or [],
        )
        self._tasks[tid] = entry
        self._last_updated_ms = now_ms
        self._cache_valid = False
        return entry

    def update_status(self, task_id: str, new_status: str) -> TaskStateEntry:
        """Transition a task to a new status.

        Args:
            task_id: Task UUID.
            new_status: Target status.

        Returns:
            Updated TaskStateEntry.

        Raises:
            KeyError: If task_id not found.
            ValueError: If transition is invalid.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        if new_status not in TaskStatus.ALL:
            raise ValueError(f"Invalid status: {new_status}")

        entry = self._tasks[task_id]
        allowed = _VALID_TRANSITIONS.get(entry.status, frozenset())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {entry.status} -> {new_status} "
                f"(allowed: {sorted(allowed)})"
            )

        now_ms = int(time.time() * 1000)
        entry.status = new_status

        if new_status == TaskStatus.DISPATCHED and entry.dispatched_at_ms == 0:
            entry.dispatched_at_ms = now_ms
        if new_status in TaskStatus.TERMINAL:
            entry.completed_at_ms = now_ms
        if new_status == TaskStatus.SUSPENDED:
            entry.pending_hil = True
            entry.hil_suspensions_count += 1
        if new_status == TaskStatus.ACTIVE and entry.pending_hil:
            entry.pending_hil = False
            entry.pending_hil_data = None  # M6 E6.1.2: clear HILSubTask on resume

        self._last_updated_ms = now_ms
        self._cache_valid = False
        return entry

    def set_progress(self, task_id: str, progress_pct: int) -> None:
        """Update task progress percentage.

        Args:
            task_id: Task UUID.
            progress_pct: 0-100.

        Raises:
            KeyError: If task_id not found.
            ValueError: If progress_pct out of range.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        if not 0 <= progress_pct <= 100:
            raise ValueError(f"progress_pct must be 0-100, got {progress_pct}")
        self._tasks[task_id].progress_pct = progress_pct
        self._last_updated_ms = int(time.time() * 1000)
        self._cache_valid = False

    def set_pending_hil_data(self, task_id: str, data: Optional[Dict[str, Any]]) -> None:
        """Store serialized HILSubTask on a task entry for crash recovery.

        M6 E6.1.2 / E6.4.1: Persists the full HILSubTask dict alongside
        the boolean pending_hil flag so scan_for_recovery() can
        reconstruct HITL state after a crash.

        Args:
            task_id: Task UUID.
            data:    Serialized HILSubTask dict, or None to clear.

        Raises:
            KeyError: If task_id not found.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        self._tasks[task_id].pending_hil_data = data
        self._last_updated_ms = int(time.time() * 1000)
        self._cache_valid = False

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_active(self) -> List[TaskStateEntry]:
        """Return tasks with ACTIVE_GROUP status (dispatched, active, suspended)."""
        return [t for t in self._tasks.values() if t.status in TaskStatus.ACTIVE_GROUP]

    def get_all(self) -> List[TaskStateEntry]:
        """Return all tasks."""
        return list(self._tasks.values())

    def get_by_id(self, task_id: str) -> Optional[TaskStateEntry]:
        """Get single task by ID."""
        return self._tasks.get(task_id)

    def count_by_status(self) -> Dict[str, int]:
        """Count tasks grouped by status."""
        counts: Dict[str, int] = {}
        for t in self._tasks.values():
            counts[t.status] = counts.get(t.status, 0) + 1
        return counts

    def get_suspended(self) -> List[TaskStateEntry]:
        """Return tasks with SUSPENDED status (pending HIL)."""
        return [t for t in self._tasks.values() if t.status == TaskStatus.SUSPENDED]

    def has_active_tasks(self) -> bool:
        """True if any task is in ACTIVE_GROUP."""
        return any(t.status in TaskStatus.ACTIVE_GROUP for t in self._tasks.values())

    @property
    def task_count(self) -> int:
        """Total number of tracked tasks."""
        return len(self._tasks)

    # =========================================================================
    # Prompt Generation
    # =========================================================================

    def to_prompt(self) -> str:
        """Full prompt representation for Front LLM context window.

        Format:
            [TASKS]
            - order_food: active (60%) [dispatched 2m ago]
            - book_ride: suspended (HIL pending, 1 suspension)
        """
        if not self._tasks:
            return "[TASKS]\nNo active tasks."

        lines = ["[TASKS]"]
        for t in self._tasks.values():
            parts = [f"- {t.action}: {t.status}"]
            if t.progress_pct > 0:
                parts.append(f"({t.progress_pct}%)")
            if t.pending_hil:
                parts.append(f"[HIL pending, {t.hil_suspensions_count} suspension(s)]")
            if t.depends_on:
                parts.append(f"[depends: {', '.join(t.depends_on[:3])}]")
            lines.append(" ".join(parts))
        return "\n".join(lines)

    def to_slim_prompt(self) -> str:
        """Slim prompt for Back LLM (active tasks only, minimal detail)."""
        active = self.get_active()
        if not active:
            return ""
        parts = []
        for t in active:
            s = f"{t.action}:{t.status}"
            if t.progress_pct > 0:
                s += f"({t.progress_pct}%)"
            parts.append(s)
        return "tasks=" + ",".join(parts)

    # =========================================================================
    # Pruning Lifecycle (Epic 2.6)
    # =========================================================================

    def mark_presented(self, task_id: str, turn_number: int) -> None:
        """Mark a task result as presented to the user at a given turn.

        Args:
            task_id: Task UUID.
            turn_number: Current turn number when result was shown.

        Raises:
            KeyError: If task_id not found.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        self._tasks[task_id].presented_at_turn = turn_number
        self._last_updated_ms = int(time.time() * 1000)
        self._cache_valid = False

    def prune_completed(self, current_turn: int) -> List[str]:
        """Remove completed tasks that have been presented for 10+ turns.

        Rule: task.status in TERMINAL AND task.presented_at_turn > 0
              AND (current_turn - task.presented_at_turn) >= 10

        Args:
            current_turn: Current turn number.

        Returns:
            List of pruned task_ids.
        """
        to_prune: List[str] = []
        for tid, t in self._tasks.items():
            if (
                t.status in TaskStatus.TERMINAL
                and t.presented_at_turn > 0
                and (current_turn - t.presented_at_turn) >= _PRUNE_AFTER_TURNS
            ):
                to_prune.append(tid)

        for tid in to_prune:
            del self._tasks[tid]

        if to_prune:
            self._last_updated_ms = int(time.time() * 1000)
            self._cache_valid = False

        return to_prune

    def prune_stale_dispatched(
        self, now_ms: int = 0, stale_threshold_ms: int = _STALE_DISPATCHED_MS
    ) -> List[str]:
        """Mark stale dispatched tasks as FAILED.

        Rule: task.status == DISPATCHED AND
              (now_ms - task.dispatched_at_ms) > stale_threshold_ms

        Args:
            now_ms: Current epoch ms. Auto-computed if 0.
            stale_threshold_ms: How long before a dispatched task is stale.

        Returns:
            List of task_ids marked as failed.
        """
        if now_ms == 0:
            now_ms = int(time.time() * 1000)

        stale: List[str] = []
        for tid, t in self._tasks.items():
            if (
                t.status == TaskStatus.DISPATCHED
                and t.dispatched_at_ms > 0
                and (now_ms - t.dispatched_at_ms) > stale_threshold_ms
            ):
                stale.append(tid)

        for tid in stale:
            entry = self._tasks[tid]
            entry.status = TaskStatus.FAILED
            entry.completed_at_ms = now_ms

        if stale:
            self._last_updated_ms = now_ms
            self._cache_valid = False

        return stale
