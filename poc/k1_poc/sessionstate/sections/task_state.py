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
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

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
        """Serialize to JSON bytes (POC -- no FlatBuffer schema for task_state)."""
        payload = {
            "section": self.SECTION_NAME,
            "last_updated_ms": self._last_updated_ms,
            "tasks": [asdict(t) for t in self._tasks.values()],
        }
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._cached_bytes = data
        self._cache_valid = True
        return data

    def from_flatbuffer(self, data: bytes) -> None:
        """Deserialize from JSON bytes."""
        payload = json.loads(data)
        self._last_updated_ms = payload.get("last_updated_ms", int(time.time() * 1000))
        self._tasks.clear()
        for t in payload.get("tasks", []):
            entry = TaskStateEntry(
                task_id=t["task_id"],
                action=t["action"],
                status=t["status"],
                dispatched_at_ms=t.get("dispatched_at_ms", 0),
                completed_at_ms=t.get("completed_at_ms", 0),
                depends_on=t.get("depends_on", []),
                progress_pct=t.get("progress_pct", 0),
                pending_hil=t.get("pending_hil", False),
                hil_suspensions_count=t.get("hil_suspensions_count", 0),
                presented_at_turn=t.get("presented_at_turn", 0),
            )
            self._tasks[entry.task_id] = entry
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
