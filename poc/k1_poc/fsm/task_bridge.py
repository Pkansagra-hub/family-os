"""
poc.k1_poc.fsm.task_bridge -- FSM bridge to TaskState and TaskArtifacts sections.

V2 Design Ref: Section 5 (task_state, task_artifacts HOT sections)

The FSM is the Single Writer for both task_state and task_artifacts
in SessionState (V2 Section 5 Authoritative Read/Write Matrix).

Back LLM NEVER writes directly. It emits deltas to the bus:
  - k1.session.artifact.created.v1 -> DeltaAggregator -> FSM -> task_artifacts
  - k1.orchestration.task.complete.v1 -> FSM handler -> task_state

This bridge provides clean APIs for the FSM to:
  1. Track task lifecycle in task_state (dispatch, progress, suspend, complete, fail, cancel)
  2. Store durable artifacts in task_artifacts (confirmations, bookings)
  3. Prune completed tasks and evict presented artifacts

Why a bridge instead of direct SS calls:
  - Encapsulates status validation and transition rules
  - Provides unified API for FSM (no need to import SS internals)
  - Tracks presented_at_turn for pruning lifecycle
  - Handles the HITL persistence fields (pending_hil, hil_suspensions_count)
"""

from __future__ import annotations

import logging
from typing import Any

from poc.k1_poc.sessionstate.sections.task_artifacts import (
    ArtifactType,
    TaskArtifactEntry,
    TaskArtifactsSection,
)
from poc.k1_poc.sessionstate.sections.task_state import (
    TaskStateEntry,
    TaskStateSection,
    TaskStatus,
)

logger = logging.getLogger(__name__)

# Pruning constants (backward-compat; runtime reads from config)
PRUNE_COMPLETED_AFTER_TURNS = 10
EVICT_ARTIFACTS_AFTER_TURNS = 10


class TaskBridge:
    """FSM bridge to TaskState and TaskArtifacts SessionState sections.

    Provides the FSM with clean lifecycle management for tasks and artifacts.
    All writes go through this bridge to maintain the Single Writer invariant.

    Lifecycle (happy path):
      1. dispatch_task() -> task_state: DISPATCHED
      2. activate_task() -> task_state: ACTIVE (on tool.started)
      3. complete_task() -> task_state: COMPLETED
      4. mark_presented() -> task_state: presented_at_turn = N
      5. prune(current_turn) -> remove if current_turn - presented_at_turn > 10

    Lifecycle (HITL):
      1. dispatch_task() -> DISPATCHED
      2. activate_task() -> ACTIVE
      3. suspend_task() -> SUSPENDED, pending_hil=True
      4. resume_task() -> ACTIVE, pending_hil=False
      5. complete_task() -> COMPLETED

    Lifecycle (cancel):
      1. dispatch_task() -> DISPATCHED
      2. cancel_task() -> CANCELLED
    """

    def __init__(
        self,
        task_state: TaskStateSection | None = None,
        task_artifacts: TaskArtifactsSection | None = None,
    ) -> None:
        self._task_state = task_state or TaskStateSection()
        self._task_artifacts = task_artifacts or TaskArtifactsSection()
        self._total_dispatched: int = 0
        self._total_completed: int = 0
        self._total_failed: int = 0
        self._total_cancelled: int = 0
        logger.info(
            "TaskBridge initialized (task_state=%s, task_artifacts=%s)",
            type(self._task_state).__name__,
            type(self._task_artifacts).__name__,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def task_state(self) -> TaskStateSection:
        """Underlying TaskStateSection."""
        return self._task_state

    @property
    def task_artifacts(self) -> TaskArtifactsSection:
        """Underlying TaskArtifactsSection."""
        return self._task_artifacts

    @property
    def total_dispatched(self) -> int:
        """Total tasks dispatched across session."""
        return self._total_dispatched

    @property
    def total_completed(self) -> int:
        """Total tasks completed across session."""
        return self._total_completed

    @property
    def total_failed(self) -> int:
        """Total tasks failed across session."""
        return self._total_failed

    @property
    def total_cancelled(self) -> int:
        """Total tasks cancelled across session."""
        return self._total_cancelled

    # ------------------------------------------------------------------
    # Task lifecycle (write operations)
    # ------------------------------------------------------------------

    def dispatch_task(self, task_id: str, action: str) -> TaskStateEntry:
        """Register a newly dispatched task.

        Called by FSM on task.dispatch.v1.

        Args:
            task_id: Unique task identifier.
            action: Natural language task description.

        Returns:
            The created TaskStateEntry.
        """
        entry = self._task_state.add_task(
            task_id=task_id,
            action=action,
            status=TaskStatus.DISPATCHED,
        )
        self._total_dispatched += 1
        logger.debug("TaskBridge: dispatched task %s (%s)", task_id, action)
        return entry

    def activate_task(self, task_id: str) -> TaskStateEntry | None:
        """Mark task as actively executing.

        Called by FSM on tool.started.v1.

        Args:
            task_id: Task to activate.

        Returns:
            Updated entry, or None if task not found.
        """
        try:
            return self._task_state.update_status(task_id, TaskStatus.ACTIVE)
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: activate failed for %s: %s", task_id, exc)
            return None

    def suspend_task(self, task_id: str) -> TaskStateEntry | None:
        """Suspend task for HITL input.

        Called by FSM on task.suspended.v1. Sets pending_hil=True and
        increments hil_suspensions_count.

        Args:
            task_id: Task to suspend.

        Returns:
            Updated entry, or None if not found.
        """
        try:
            # Auto-activate if still DISPATCHED (mirrors complete_task pattern)
            current = self._task_state.get_by_id(task_id)
            if current and current.status == TaskStatus.DISPATCHED:
                self._task_state.update_status(task_id, TaskStatus.ACTIVE)
                logger.debug("TaskBridge: auto-activated task %s before suspending", task_id)
            return self._task_state.update_status(task_id, TaskStatus.SUSPENDED)
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: suspend failed for %s: %s", task_id, exc)
            return None

    def resume_task(self, task_id: str) -> TaskStateEntry | None:
        """Resume a suspended task after HITL response.

        Called by FSM on task.resume.v1.

        Args:
            task_id: Task to resume.

        Returns:
            Updated entry, or None if not found.
        """
        try:
            return self._task_state.update_status(task_id, TaskStatus.ACTIVE)
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: resume failed for %s: %s", task_id, exc)
            return None

    def complete_task(self, task_id: str) -> TaskStateEntry | None:
        """Mark task as completed.

        Called by FSM on task.complete.v1.
        Auto-activates the task first if still in DISPATCHED state
        (the back handler may complete without a separate activate step).

        Args:
            task_id: Task to complete.

        Returns:
            Updated entry, or None if not found.
        """
        try:
            # Auto-activate if still DISPATCHED (back may skip activate)
            current = self._task_state.get_by_id(task_id)
            if current and current.status == TaskStatus.DISPATCHED:
                self._task_state.update_status(task_id, TaskStatus.ACTIVE)
                logger.debug("TaskBridge: auto-activated task %s before completing", task_id)
            entry = self._task_state.update_status(task_id, TaskStatus.COMPLETED)
            self._total_completed += 1
            logger.debug("TaskBridge: completed task %s", task_id)
            return entry
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: complete failed for %s: %s", task_id, exc)
            return None

    def fail_task(self, task_id: str) -> TaskStateEntry | None:
        """Mark task as failed.

        Called by FSM on task.failed.v1 (reason=error or timeout).

        Args:
            task_id: Task to fail.

        Returns:
            Updated entry, or None if not found.
        """
        try:
            entry = self._task_state.update_status(task_id, TaskStatus.FAILED)
            self._total_failed += 1
            return entry
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: fail failed for %s: %s", task_id, exc)
            return None

    def cancel_task(self, task_id: str) -> TaskStateEntry | None:
        """Mark task as cancelled.

        Called by FSM on task.failed.v1 (reason=cancelled).

        Args:
            task_id: Task to cancel.

        Returns:
            Updated entry, or None if not found.
        """
        try:
            entry = self._task_state.update_status(task_id, TaskStatus.CANCELLED)
            self._total_cancelled += 1
            return entry
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: cancel failed for %s: %s", task_id, exc)
            return None

    def mark_presented(self, task_id: str, turn_number: int) -> None:
        """Mark task results as presented to user.

        Called by FSM after Front delivers response.final for this task.

        Args:
            task_id: Task whose results were presented.
            turn_number: Current turn number.
        """
        entry = self._task_state.get_by_id(task_id)
        if entry:
            entry.presented_at_turn = turn_number
            logger.debug("TaskBridge: marked %s as presented at turn %d", task_id, turn_number)

    def set_progress(self, task_id: str, progress_pct: int) -> None:
        """Update task progress percentage.

        Args:
            task_id: Task to update.
            progress_pct: 0-100.
        """
        try:
            self._task_state.set_progress(task_id, progress_pct)
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: set_progress failed for %s: %s", task_id, exc)

    # ------------------------------------------------------------------
    # Artifact operations
    # ------------------------------------------------------------------

    def add_artifact(
        self,
        task_id: str,
        content: str = "",
        artifact_type: ArtifactType = ArtifactType.TEXT,
        metadata: dict[str, Any] | None = None,
    ) -> TaskArtifactEntry:
        """Store a durable artifact from a completed task.

        Called by FSM via DeltaAggregator when artifact.created arrives.

        Args:
            task_id: Producing task ID.
            content: Artifact payload text.
            artifact_type: ArtifactType enum value.
            metadata: Optional key-value pairs.

        Returns:
            The created TaskArtifactEntry.
        """
        return self._task_artifacts.add_artifact(
            task_id=task_id,
            content=content,
            artifact_type=artifact_type,
            metadata=metadata or {},
        )

    def get_artifacts_for_task(self, task_id: str) -> list[TaskArtifactEntry]:
        """Get all artifacts produced by a task."""
        return [a for a in self._task_artifacts.get_all() if a.task_id == task_id]

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_active_tasks(self) -> list[TaskStateEntry]:
        """Get all active (non-terminal) tasks."""
        return self._task_state.get_active()

    def get_task(self, task_id: str) -> TaskStateEntry | None:
        """Get a single task by ID."""
        return self._task_state.get_by_id(task_id)

    def get_suspended_tasks(self) -> list[TaskStateEntry]:
        """Get tasks awaiting HITL input."""
        return self._task_state.get_suspended()

    def task_count_by_status(self) -> dict[str, int]:
        """Count tasks grouped by status."""
        return self._task_state.count_by_status()

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def prune(self, current_turn: int) -> int:
        """Prune completed tasks and evict old artifacts.

        Called periodically (e.g., at turn boundaries).
        Uses the SS section's own prune/evict methods.

        Args:
            current_turn: Current turn number.

        Returns:
            Number of items pruned.
        """
        pruned = 0

        # Prune completed tasks presented > 10 turns ago
        pruned_task_ids = self._task_state.prune_completed(current_turn)
        pruned += len(pruned_task_ids)

        # Evict artifacts presented > 10 turns ago
        evicted_artifacts = self._task_artifacts.evict_to_warm(current_turn)
        pruned += len(evicted_artifacts)

        if pruned:
            logger.info("TaskBridge: pruned %d items at turn %d", pruned, current_turn)
        return pruned

    # ------------------------------------------------------------------
    # Snapshot / observability
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a summary snapshot for observability."""
        return {
            "total_dispatched": self._total_dispatched,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "total_cancelled": self._total_cancelled,
            "active_tasks": len(self._task_state.get_active()),
            "task_state_size": self._task_state.get_size_bytes(),
            "artifact_count": len(self._task_artifacts.get_all()),
            "artifact_size": self._task_artifacts.get_size_bytes(),
        }

    def reset(self) -> None:
        """Reset all state. Called on teardown."""
        self._task_state.clear()
        self._task_artifacts.clear()
        self._total_dispatched = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_cancelled = 0
