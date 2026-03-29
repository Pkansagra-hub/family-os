"""
Task Registry
==============

Central registry for tracking all background tasks.
Provides lookup, monitoring, and lifecycle management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from poc.session_state_demo.anniversary_demo.background.task_queue import (
    BackgroundTask,
    TaskPriority,
    TaskQueue,
    TaskStatus,
)


@dataclass
class TaskSummary:
    """Summary of task registry state."""

    total_tasks: int
    pending: int
    running: int
    completed: int
    failed: int
    cancelled: int
    by_type: Dict[str, int] = field(default_factory=dict)


class TaskRegistry:
    """
    Central registry for all background tasks.

    Features:
    - Task lookup by ID, type, or status
    - Task lifecycle tracking
    - Statistics and monitoring
    - Cleanup of old tasks
    """

    def __init__(self, task_queue: Optional[TaskQueue] = None):
        self._queue = task_queue
        self._tasks: Dict[str, BackgroundTask] = {}
        self._tasks_by_type: Dict[str, List[str]] = {}
        self._task_history: List[Dict[str, Any]] = []

    def set_queue(self, queue: TaskQueue) -> None:
        """Set the task queue (for late binding)."""
        self._queue = queue

    async def register_and_submit(self, task: BackgroundTask) -> str:
        """Register a task and submit to queue."""
        # Register
        self._tasks[task.task_id] = task

        # Track by type
        if task.task_type not in self._tasks_by_type:
            self._tasks_by_type[task.task_type] = []
        self._tasks_by_type[task.task_type].append(task.task_id)

        # Submit to queue
        if self._queue:
            await self._queue.submit(task)

        return task.task_id

    def register(self, task: BackgroundTask) -> str:
        """Register a task without submitting (for tracking only)."""
        self._tasks[task.task_id] = task

        if task.task_type not in self._tasks_by_type:
            self._tasks_by_type[task.task_type] = []
        self._tasks_by_type[task.task_type].append(task.task_id)

        return task.task_id

    def get(self, task_id: str) -> Optional[BackgroundTask]:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def get_by_type(self, task_type: str) -> List[BackgroundTask]:
        """Get all tasks of a specific type."""
        task_ids = self._tasks_by_type.get(task_type, [])
        return [self._tasks[tid] for tid in task_ids if tid in self._tasks]

    def get_active(self) -> List[BackgroundTask]:
        """Get all active tasks."""
        return [t for t in self._tasks.values() if t.is_active]

    def get_by_status(self, status: TaskStatus) -> List[BackgroundTask]:
        """Get tasks by status."""
        return [t for t in self._tasks.values() if t.status == status]

    async def cancel(self, task_id: str) -> bool:
        """Cancel a task."""
        if self._queue:
            return await self._queue.cancel(task_id)
        return False

    async def cancel_by_type(self, task_type: str) -> int:
        """Cancel all tasks of a type. Returns count cancelled."""
        count = 0
        for task in self.get_by_type(task_type):
            if task.is_active and await self.cancel(task.task_id):
                count += 1
        return count

    def get_summary(self) -> TaskSummary:
        """Get summary of all tasks."""
        by_status = {status: 0 for status in TaskStatus}
        by_type: Dict[str, int] = {}

        for task in self._tasks.values():
            by_status[task.status] += 1
            by_type[task.task_type] = by_type.get(task.task_type, 0) + 1

        return TaskSummary(
            total_tasks=len(self._tasks),
            pending=by_status[TaskStatus.PENDING],
            running=by_status[TaskStatus.RUNNING],
            completed=by_status[TaskStatus.COMPLETED],
            failed=by_status[TaskStatus.FAILED],
            cancelled=by_status[TaskStatus.CANCELLED],
            by_type=by_type,
        )

    def cleanup_completed(self, max_age_seconds: float = 3600) -> int:
        """Remove completed tasks older than max_age. Returns count removed."""
        now = datetime.now()
        to_remove = []

        for task_id, task in self._tasks.items():
            if task.is_done and task.completed_at:
                age = (now - task.completed_at).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(task_id)

        for task_id in to_remove:
            task = self._tasks.pop(task_id)
            # Record in history
            self._task_history.append(task.to_dict())
            # Remove from type index
            if task.task_type in self._tasks_by_type:
                self._tasks_by_type[task.task_type] = [
                    tid for tid in self._tasks_by_type[task.task_type] if tid != task_id
                ]

        return len(to_remove)

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get task history (completed and removed tasks)."""
        return self._task_history[-limit:]


# Singleton registry
_registry: Optional[TaskRegistry] = None


def get_registry() -> TaskRegistry:
    """Get the global task registry."""
    global _registry
    if _registry is None:
        _registry = TaskRegistry()
    return _registry


def create_task(
    name: str,
    task_type: str,
    handler: Callable,
    params: Optional[Dict[str, Any]] = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    is_recurring: bool = False,
    interval_seconds: Optional[float] = None,
    max_runs: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> BackgroundTask:
    """Convenience function to create a task."""
    return BackgroundTask.create(
        name=name,
        task_type=task_type,
        handler=handler,
        params=params,
        priority=priority,
        is_recurring=is_recurring,
        interval_seconds=interval_seconds,
        max_runs=max_runs,
        metadata=metadata,
    )
