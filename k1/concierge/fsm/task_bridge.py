"""
k1.concierge.fsm.task_bridge -- FSM bridge to TaskState and TaskArtifacts sections.

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
from typing import TYPE_CHECKING, Any

from k1.sessionstate.public_types import (
    ArtifactType,
    TaskArtifactEntry,
    TaskArtifactsSection,
    TaskStateEntry,
    TaskStateSection,
    TaskStatus,
)

if TYPE_CHECKING:
    from k1.concierge.ledger.writer import LedgerWriter

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
        ledger: LedgerWriter | None = None,
    ) -> None:
        self._task_state = task_state or TaskStateSection()
        self._task_artifacts = task_artifacts or TaskArtifactsSection()
        self._ledger: LedgerWriter | None = ledger
        self._total_dispatched: int = 0
        self._total_completed: int = 0
        self._total_failed: int = 0
        self._total_cancelled: int = 0
        self._rebound: bool = False
        logger.info(
            "TaskBridge initialized (task_state=%s, task_artifacts=%s, ledger=%s)",
            type(self._task_state).__name__,
            type(self._task_artifacts).__name__,
            "yes" if ledger else "no",
        )

    # ------------------------------------------------------------------
    # Rebind (M4 E4.1.1)
    # ------------------------------------------------------------------

    def rebind(
        self,
        task_state: TaskStateSection,
        task_artifacts: TaskArtifactsSection,
    ) -> None:
        """Rebind to real SessionState sections, replacing local fallbacks.

        Called by ``ConciergeController.set_session_state()`` after the
        SessionStateManager is attached so that FSM lifecycle writes land
        in the sections that Front/Back actors read.

        Any tasks dispatched before rebind (defensive -- in practice
        bootstrap wires before first user input) are copied into the new
        sections.  Raises if called while tasks are in ACTIVE state to
        prevent mid-flight data loss.

        Args:
            task_state:     Real TaskStateSection from SS manager.
            task_artifacts: Real TaskArtifactsSection from SS manager.

        Raises:
            RuntimeError: If any task is currently ACTIVE (mid-flight).
        """
        # Guard: reject mid-flight rebind
        active = [t for t in self._task_state.get_active() if t.status == TaskStatus.ACTIVE]
        if active:
            raise RuntimeError(
                f"Cannot rebind TaskBridge while {len(active)} task(s) are ACTIVE: "
                f"{[t.task_id for t in active]}"
            )

        old_state = self._task_state
        old_artifacts = self._task_artifacts

        # Copy any pre-rebind tasks into the new sections
        for entry in old_state.get_all():
            if task_state.get_by_id(entry.task_id) is None:
                task_state.add_task(
                    task_id=entry.task_id,
                    action=entry.action,
                    status=entry.status,
                )

        for artifact in old_artifacts.get_all():
            existing = [
                a for a in task_artifacts.get_all() if a.artifact_id == artifact.artifact_id
            ]
            if not existing:
                task_artifacts.add_artifact(
                    task_id=artifact.task_id,
                    content=artifact.content,
                    artifact_type=artifact.artifact_type,
                    metadata=artifact.metadata or {},
                )

        self._task_state = task_state
        self._task_artifacts = task_artifacts
        self._rebound = True
        logger.info(
            "TaskBridge rebound to real SS sections " "(copied %d tasks, %d artifacts)",
            len(old_state.get_all()),
            len(old_artifacts.get_all()),
        )

    @property
    def is_rebound(self) -> bool:
        """Whether rebind() has been called with real SS sections."""
        return self._rebound

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

    def set_ledger(self, ledger: LedgerWriter) -> None:
        """Wire the ledger writer after construction.

        M9 E9.4.1: Allows bootstrap to attach the ledger after
        the TaskBridge is created but before the first mutation.
        """
        self._ledger = ledger
        logger.info("TaskBridge: ledger wired (session=%s)", ledger.session_id)

    def dispatch_task(self, task_id: str, action: str) -> TaskStateEntry:
        """Register a newly dispatched task.

        Called by FSM on task.dispatch.v1.
        M9 E9.4.1: Ledger write BEFORE in-memory mutation.

        Args:
            task_id: Unique task identifier.
            action: Natural language task description.

        Returns:
            The created TaskStateEntry.
        """
        if self._ledger is not None:
            from k1.concierge.events.task import TaskCreated

            self._ledger.append_sync(
                TaskCreated(
                    session_id=self._ledger.session_id,
                    task_id=task_id,
                    action=action,
                    actor="fsm",
                )
            )
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
        M9 E9.4.1: Ledger write BEFORE in-memory mutation.

        Args:
            task_id: Task to activate.

        Returns:
            Updated entry, or None if task not found.
        """
        try:
            if self._ledger is not None:
                from k1.concierge.events.task import TaskProgressed

                self._ledger.append_sync(
                    TaskProgressed(
                        session_id=self._ledger.session_id,
                        task_id=task_id,
                        status_message="activated",
                        actor="back",
                    )
                )
            return self._task_state.update_status(task_id, TaskStatus.ACTIVE)
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: activate failed for %s: %s", task_id, exc)
            return None

    def suspend_task(self, task_id: str) -> TaskStateEntry | None:
        """Suspend task for HITL input.

        Called by FSM on task.suspended.v1. Sets pending_hil=True and
        increments hil_suspensions_count.
        M9 E9.4.1: Ledger write BEFORE in-memory mutation.

        Args:
            task_id: Task to suspend.

        Returns:
            Updated entry, or None if not found.
        """
        try:
            if self._ledger is not None:
                from k1.concierge.events.hitl import TaskSuspended as TaskSuspendedEvent

                current = self._task_state.get_by_id(task_id)
                count = (current.hil_suspensions_count + 1) if current else 1
                self._ledger.append_sync(
                    TaskSuspendedEvent(
                        session_id=self._ledger.session_id,
                        task_id=task_id,
                        suspension_type="hil",
                        suspension_count=count,
                        actor="back",
                    )
                )
            # Auto-activate if still DISPATCHED (mirrors complete_task pattern)
            current = self._task_state.get_by_id(task_id)
            if current and current.status == TaskStatus.DISPATCHED:
                self._task_state.update_status(task_id, TaskStatus.ACTIVE)
                logger.debug("TaskBridge: auto-activated task %s before suspending", task_id)
            return self._task_state.update_status(task_id, TaskStatus.SUSPENDED)
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: suspend failed for %s: %s", task_id, exc)
            return None

    def set_pending_hil_data(self, task_id: str, data: dict | None) -> None:
        """Store serialized HILSubTask on a task entry for crash recovery.

        M6 E6.1.2 / E6.4.1: Persists the full HILSubTask dict alongside
        the boolean pending_hil flag so scan_for_recovery() can
        reconstruct HITL state after a crash.

        Args:
            task_id: Task UUID.
            data:    Serialized HILSubTask dict, or None to clear.
        """
        try:
            self._task_state.set_pending_hil_data(task_id, data)
        except KeyError:
            logger.warning(
                "TaskBridge: set_pending_hil_data failed for %s (not found)",
                task_id,
            )

    def resume_task(self, task_id: str) -> TaskStateEntry | None:
        """Resume a suspended task after HITL response.

        Called by FSM on task.resume.v1.
        M9 E9.4.1: Ledger write BEFORE in-memory mutation.

        Args:
            task_id: Task to resume.

        Returns:
            Updated entry, or None if not found.
        """
        try:
            if self._ledger is not None:
                from k1.concierge.events.hitl import TaskResumed as TaskResumedEvent

                self._ledger.append_sync(
                    TaskResumedEvent(
                        session_id=self._ledger.session_id,
                        task_id=task_id,
                        actor="fsm",
                    )
                )
            return self._task_state.update_status(task_id, TaskStatus.ACTIVE)
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: resume failed for %s: %s", task_id, exc)
            return None

    def complete_task(
        self, task_id: str, result_data: dict[str, Any] | None = None
    ) -> TaskStateEntry | None:
        """Mark task as completed.

        Called by FSM on task.complete.v1.
        Auto-activates the task first if still in DISPATCHED state
        (the back handler may complete without a separate activate step).
        M9 E9.4.1: Ledger write BEFORE in-memory mutation.

        Args:
            task_id: Task to complete.
            result_data: Optional structured result payload.

        Returns:
            Updated entry, or None if not found.
        """
        try:
            if self._ledger is not None:
                from k1.concierge.events.task import TaskCompleted as TaskCompletedEvent

                self._ledger.append_sync(
                    TaskCompletedEvent(
                        session_id=self._ledger.session_id,
                        task_id=task_id,
                        result_data=result_data or {},
                        actor="back",
                    )
                )
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

    def fail_task(self, task_id: str, reason: str = "error") -> TaskStateEntry | None:
        """Mark task as failed.

        Called by FSM on task.failed.v1 (reason=error or timeout).
        M9 E9.4.1: Ledger write BEFORE in-memory mutation.

        Args:
            task_id: Task to fail.
            reason: Failure reason string.

        Returns:
            Updated entry, or None if not found.
        """
        try:
            if self._ledger is not None:
                from k1.concierge.events.task import TaskFailed as TaskFailedEvent

                self._ledger.append_sync(
                    TaskFailedEvent(
                        session_id=self._ledger.session_id,
                        task_id=task_id,
                        reason=reason,
                        actor="back",
                    )
                )
            entry = self._task_state.update_status(task_id, TaskStatus.FAILED)
            self._total_failed += 1
            return entry
        except (KeyError, ValueError) as exc:
            logger.warning("TaskBridge: fail failed for %s: %s", task_id, exc)
            return None

    def cancel_task(self, task_id: str, reason: str = "user_requested") -> TaskStateEntry | None:
        """Mark task as cancelled.

        Called by FSM on task.failed.v1 (reason=cancelled).
        M9 E9.4.1: Ledger write BEFORE in-memory mutation.

        Args:
            task_id: Task to cancel.
            reason: Cancellation reason string.

        Returns:
            Updated entry, or None if not found.
        """
        try:
            if self._ledger is not None:
                from k1.concierge.events.task import TaskCancelled as TaskCancelledEvent

                self._ledger.append_sync(
                    TaskCancelledEvent(
                        session_id=self._ledger.session_id,
                        task_id=task_id,
                        reason=reason,
                        actor="fsm",
                    )
                )
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

    # ------------------------------------------------------------------
    # M9 E9.4.1: Rebuild from ledger projection
    # ------------------------------------------------------------------

    def rebuild_from_projection(
        self,
        projected: dict[str, Any],
    ) -> int:
        """Rebuild in-memory task state from a ledger projection.

        M9 E9.4.1: Called by CrashRecoveryOrchestrator during startup.
        Replaces the current TaskStateSection contents with the
        projected state derived from ledger events.

        The projection produces hitl_persistence.TaskStateEntry objects
        which use uppercase enum statuses (DISPATCHED, IN_PROGRESS, etc.).
        This method maps them to the SS lowercase strings (dispatched, active).

        Args:
            projected: Dict of task_id -> hitl_persistence.TaskStateEntry
                       from ``project_task_states(entries)``.

        Returns:
            Number of tasks restored.
        """
        # Map hitl_persistence TaskStatus (uppercase) to SS TaskStatus (lowercase)
        _STATUS_MAP = {
            "DISPATCHED": TaskStatus.DISPATCHED,
            "IN_PROGRESS": TaskStatus.ACTIVE,
            "SUSPENDED": TaskStatus.SUSPENDED,
            "COMPLETED": TaskStatus.COMPLETED,
            "FAILED": TaskStatus.FAILED,
            "CANCELLED": TaskStatus.CANCELLED,
        }

        self._task_state.clear()
        counts = {"dispatched": 0, "completed": 0, "failed": 0, "cancelled": 0}

        for task_id, entry in projected.items():
            # Convert status from hitl_persistence enum to SS string
            raw_status = (
                str(entry.status.value) if hasattr(entry.status, "value") else str(entry.status)
            )
            ss_status = _STATUS_MAP.get(raw_status, TaskStatus.DISPATCHED)

            self._task_state.add_task(
                task_id=entry.task_id,
                action=entry.action,
                status=ss_status,
            )
            counts["dispatched"] += 1
            if ss_status == TaskStatus.COMPLETED:
                counts["completed"] += 1
            elif ss_status == TaskStatus.FAILED:
                counts["failed"] += 1
            elif ss_status == TaskStatus.CANCELLED:
                counts["cancelled"] += 1

            # Restore HITL persistence fields on the SS entry
            restored = self._task_state.get_by_id(task_id)
            if restored is not None:
                if entry.pending_hil:
                    restored.pending_hil = True
                restored.hil_suspensions_count = getattr(entry, "hil_suspensions_count", 0)

        self._total_dispatched = counts["dispatched"]
        self._total_completed = counts["completed"]
        self._total_failed = counts["failed"]
        self._total_cancelled = counts["cancelled"]

        logger.info(
            "TaskBridge: rebuilt from projection "
            "(tasks=%d, completed=%d, failed=%d, cancelled=%d)",
            counts["dispatched"],
            counts["completed"],
            counts["failed"],
            counts["cancelled"],
        )
        return len(projected)

    def reset(self) -> None:
        """Reset all state. Called on teardown."""
        self._task_state.clear()
        self._task_artifacts.clear()
        self._total_dispatched = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_cancelled = 0
