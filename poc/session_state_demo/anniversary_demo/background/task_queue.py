"""
Background Task Queue
======================

Async task queue for background processing that runs concurrently with
user conversation. Enables the "two-way concierge" - background monitors
and proactive notifications while user continues chatting.

Key Components:
- TaskQueue: Manages task lifecycle
- BackgroundTask: Individual task representation
- TaskRegistry: Tracks all active tasks
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Dict, List, Optional


class TaskStatus(Enum):
    """Status of a background task."""

    PENDING = auto()  # Waiting to start
    RUNNING = auto()  # Currently executing
    COMPLETED = auto()  # Finished successfully
    FAILED = auto()  # Finished with error
    CANCELLED = auto()  # Manually cancelled


class TaskPriority(Enum):
    """Priority level for task scheduling."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class BackgroundTask:
    """
    Represents a background task that runs independently of conversation.

    Examples:
    - Weather monitor (polls for changes)
    - Scheduled reminder (fires at time)
    - Price watch (alerts on change)
    """

    task_id: str
    name: str
    task_type: str
    handler: Callable[..., Coroutine[Any, Any, Any]]
    params: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # For recurring tasks
    is_recurring: bool = False
    interval_seconds: Optional[float] = None
    max_runs: Optional[int] = None
    run_count: int = 0

    @classmethod
    def create(
        cls,
        name: str,
        task_type: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        params: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        is_recurring: bool = False,
        interval_seconds: Optional[float] = None,
        max_runs: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "BackgroundTask":
        """Factory method to create a task."""
        return cls(
            task_id=str(uuid.uuid4())[:8],
            name=name,
            task_type=task_type,
            handler=handler,
            params=params or {},
            priority=priority,
            is_recurring=is_recurring,
            interval_seconds=interval_seconds,
            max_runs=max_runs,
            metadata=metadata or {},
        )

    @property
    def is_active(self) -> bool:
        """Check if task is still active (pending or running)."""
        return self.status in (TaskStatus.PENDING, TaskStatus.RUNNING)

    @property
    def is_done(self) -> bool:
        """Check if task has completed (success or failure)."""
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize task to dictionary."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "task_type": self.task_type,
            "status": self.status.name,
            "priority": self.priority.name,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "is_recurring": self.is_recurring,
            "run_count": self.run_count,
            "params": self.params,
            "metadata": self.metadata,
        }


class TaskQueue:
    """
    Async task queue for background processing.

    Features:
    - Priority-based scheduling
    - Concurrent execution limit
    - Recurring task support
    - Task cancellation
    - Notification callbacks
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        on_task_complete: Optional[Callable[[BackgroundTask], None]] = None,
        on_notification: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self.max_concurrent = max_concurrent
        self.on_task_complete = on_task_complete
        self.on_notification = on_notification

        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._all_tasks: Dict[str, BackgroundTask] = {}
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the task queue worker."""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """Stop the task queue and cancel all tasks."""
        self._running = False

        # Cancel all active tasks
        for task_id, asyncio_task in list(self._active_tasks.items()):
            asyncio_task.cancel()
            if task_id in self._all_tasks:
                self._all_tasks[task_id].status = TaskStatus.CANCELLED

        self._active_tasks.clear()

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def submit(self, task: BackgroundTask) -> str:
        """
        Submit a task to the queue.

        Returns the task_id for tracking.
        """
        self._all_tasks[task.task_id] = task

        # Priority queue uses (priority, timestamp, task_id) for ordering
        # Lower number = higher priority, so negate priority value
        priority_value = -task.priority.value
        await self._queue.put((priority_value, task.created_at.timestamp(), task.task_id))

        return task.task_id

    async def cancel(self, task_id: str) -> bool:
        """
        Cancel a task.

        Returns True if cancelled, False if not found or already done.
        """
        if task_id not in self._all_tasks:
            return False

        task = self._all_tasks[task_id]

        if task.is_done:
            return False

        # If running, cancel the asyncio task
        if task_id in self._active_tasks:
            self._active_tasks[task_id].cancel()
            del self._active_tasks[task_id]

        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now()

        return True

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get task by ID."""
        return self._all_tasks.get(task_id)

    def get_active_tasks(self) -> List[BackgroundTask]:
        """Get all active tasks."""
        return [t for t in self._all_tasks.values() if t.is_active]

    def get_all_tasks(self) -> List[BackgroundTask]:
        """Get all tasks."""
        return list(self._all_tasks.values())

    async def _worker(self) -> None:
        """Main worker loop that processes tasks."""
        while self._running:
            try:
                # Check if we can run more tasks
                if len(self._active_tasks) >= self.max_concurrent:
                    await asyncio.sleep(0.1)
                    continue

                # Get next task (with timeout to allow checking _running)
                try:
                    priority, timestamp, task_id = await asyncio.wait_for(
                        self._queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                task = self._all_tasks.get(task_id)
                if not task or task.status == TaskStatus.CANCELLED:
                    continue

                # Start task execution
                asyncio_task = asyncio.create_task(self._execute_task(task))
                self._active_tasks[task_id] = asyncio_task

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Task queue worker error: {e}")
                await asyncio.sleep(0.1)

    async def _execute_task(self, task: BackgroundTask) -> None:
        """Execute a single task."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()

        try:
            result = await task.handler(**task.params)
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.run_count += 1

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            raise

        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED

        finally:
            task.completed_at = datetime.now()

            # Remove from active
            if task.task_id in self._active_tasks:
                del self._active_tasks[task.task_id]

            # Callback
            if self.on_task_complete:
                self.on_task_complete(task)

            # Handle recurring
            if (
                task.is_recurring
                and task.status == TaskStatus.COMPLETED
                and (task.max_runs is None or task.run_count < task.max_runs)
            ):
                await self._schedule_recurring(task)

    async def _schedule_recurring(self, task: BackgroundTask) -> None:
        """Schedule the next run of a recurring task."""
        if task.interval_seconds:
            await asyncio.sleep(task.interval_seconds)

        # Reset for next run
        task.status = TaskStatus.PENDING
        task.started_at = None
        task.completed_at = None
        task.result = None
        task.error = None

        await self.submit(task)

    def emit_notification(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit a notification from a background task."""
        if self.on_notification:
            self.on_notification(message, data or {})


def create_task_queue(
    max_concurrent: int = 5,
    on_task_complete: Optional[Callable[[BackgroundTask], None]] = None,
    on_notification: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> TaskQueue:
    """Create a configured task queue."""
    return TaskQueue(
        max_concurrent=max_concurrent,
        on_task_complete=on_task_complete,
        on_notification=on_notification,
    )
