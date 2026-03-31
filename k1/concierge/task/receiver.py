"""
k1.concierge.task.receiver -- Back actor task receiver and dependency router.

V2 Design Ref: Section 6.2 (Back handler task.dispatch processing)
V2 Design Ref: Section 8.1 (task state machine: DISPATCHED -> IN_PROGRESS -> COMPLETED/FAILED)
V2 Design Ref: Section 8.5 (TaskDependencyQueue, chained task routing)

Subscribes to k1.orchestration.task.dispatch.v1.  For each incoming
dispatch:
    - If depends_on is None:  execute immediately
    - If depends_on is set:   enqueue in TaskDependencyQueue
    - If dependency already complete:  hydrate and execute immediately

The receiver owns the dependency queue and wires up the execute callback
to the Back's ReAct loop entry point.  It does NOT own the ReAct loop
itself -- that is the Back actor's responsibility.

Task state transitions managed here:
    DISPATCHED -> IN_PROGRESS  (when _execute_and_complete begins)
    IN_PROGRESS -> COMPLETED   (when execute_fn returns TaskComplete)
    IN_PROGRESS -> FAILED      (when execute_fn raises or returns TaskFailed)

The receiver is stateful and persists across turns because chained
task #2 may complete turns after task #1 dispatches.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from k1.concierge.task.dependency_queue import TaskDependencyQueue
from k1.concierge.task.dispatch import TaskComplete, TaskDispatch, TaskFailed

logger = logging.getLogger(__name__)


class TaskReceiver:
    """Receives task dispatches and routes them through dependency resolution.

    Lifecycle:
        1. Back actor creates TaskReceiver at startup.
        2. Sets execute_fn to its ReAct loop entry point.
        3. Subscribes to TASK_DISPATCH topic via the bus.
        4. For each dispatch: handle() routes to immediate exec or dep queue.

    Attributes:
        dependency_queue:  Holds chained tasks waiting for parents.
        execute_fn:        Async callback to execute a dispatch in the ReAct loop.
                           Signature: (TaskDispatch) -> TaskComplete
                           Must raise on failure (receiver wraps in TaskFailed).
        _active_tasks:     Set of task_ids currently executing.
        _completed_count:  Total tasks completed since receiver creation.
        _failed_count:     Total tasks failed since receiver creation.
        _results:          Map of task_id -> TaskComplete for completed tasks.
    """

    __slots__ = (
        "dependency_queue",
        "execute_fn",
        "_active_tasks",
        "_completed_count",
        "_failed_count",
        "_results",
    )

    def __init__(self) -> None:
        self.dependency_queue = TaskDependencyQueue()
        self.execute_fn: Callable[[TaskDispatch], Awaitable[TaskComplete]] | None = None
        self._active_tasks: set[str] = set()
        self._completed_count: int = 0
        self._failed_count: int = 0
        self._results: dict[str, TaskComplete | TaskFailed] = {}

    def set_execute_fn(self, fn: Callable[[TaskDispatch], Awaitable[TaskComplete]]) -> None:
        """Set the async function that executes a task in the ReAct loop.

        Args:
            fn: Async callable (TaskDispatch) -> TaskComplete.
                Must return TaskComplete on success.
                May raise on failure (receiver wraps in TaskFailed).
        """
        self.execute_fn = fn

    async def handle(self, dispatch: TaskDispatch) -> None:
        """Handle an incoming TaskDispatch from the bus.

        Routing logic:
            - depends_on is None:               execute immediately
            - depends_on is set, dep complete:   hydrate and execute immediately
            - depends_on is set, dep pending:    buffer in dependency queue

        Args:
            dispatch: The incoming TaskDispatch (deserialized from envelope payload).
        """
        logger.info(
            "TaskReceiver.handle: task=%s intents=%d tier=%s depends_on=%s",
            dispatch.task_id,
            len(dispatch.intents),
            dispatch.tier.value,
            dispatch.depends_on,
        )

        if dispatch.is_chained:
            was_buffered = self.dependency_queue.enqueue(dispatch)
            if was_buffered:
                logger.info(
                    "TaskReceiver: task %s buffered (waiting for %s)",
                    dispatch.task_id,
                    dispatch.depends_on,
                )
                return  # Waiting for dependency
            # Dependency already complete; dispatch was hydrated in-place.
            # Fall through to execute.

        await self._execute_and_complete(dispatch)

    async def _execute_and_complete(self, dispatch: TaskDispatch) -> None:
        """Execute a task and handle its completion or failure.

        On success: stores TaskComplete, notifies dependency queue.
        On failure: stores TaskFailed, notifies dependency queue with
                    a synthetic TaskComplete so chained waiters can
                    detect parent failure.

        Args:
            dispatch: The TaskDispatch to execute.
        """
        if self.execute_fn is None:
            logger.error(
                "TaskReceiver: no execute_fn set, dropping task %s",
                dispatch.task_id,
            )
            return

        self._active_tasks.add(dispatch.task_id)
        logger.info(
            "TaskReceiver: executing task %s (%d intents, tier=%s)",
            dispatch.task_id,
            len(dispatch.intents),
            dispatch.tier.value,
        )

        result: TaskComplete | TaskFailed
        try:
            complete = await self.execute_fn(dispatch)
            self._completed_count += 1
            self._results[dispatch.task_id] = complete
            result = complete
            logger.info(
                "TaskReceiver: task %s completed (tool_calls=%d)",
                dispatch.task_id,
                complete.tool_calls,
            )
        except Exception as exc:
            failed = TaskFailed(
                task_id=dispatch.task_id,
                reason="internal_error",
                last_error_detail=str(exc),
            )
            self._failed_count += 1
            self._results[dispatch.task_id] = failed
            result = failed
            logger.exception(
                "TaskReceiver: task %s failed with %s",
                dispatch.task_id,
                type(exc).__name__,
            )
        finally:
            self._active_tasks.discard(dispatch.task_id)

        # Notify dependency queue -- may release chained waiters.
        # We always notify with a TaskComplete (even on failure, using
        # a synthetic one) so chained tasks can detect and handle failure.
        if isinstance(result, TaskComplete):
            released = self.dependency_queue.on_task_complete(result)
        else:
            # Synthetic completion for dep queue notification.
            # Chained tasks will see empty results and fail gracefully.
            synthetic = TaskComplete(
                task_id=dispatch.task_id,
                final_answer=f"Parent task failed: {result.reason}",
                results=[{"_parent_failed": True, "reason": result.reason}],
            )
            released = self.dependency_queue.on_task_complete(synthetic)

        # Execute released chained tasks recursively
        for chained_dispatch in released:
            await self._execute_and_complete(chained_dispatch)

    @property
    def active_count(self) -> int:
        """Number of tasks currently executing."""
        return len(self._active_tasks)

    @property
    def waiting_count(self) -> int:
        """Number of tasks waiting for dependencies."""
        return self.dependency_queue.waiting_count

    @property
    def completed_count(self) -> int:
        """Total tasks completed successfully since receiver creation."""
        return self._completed_count

    @property
    def failed_count(self) -> int:
        """Total tasks failed since receiver creation."""
        return self._failed_count

    def get_result(self, task_id: str) -> TaskComplete | TaskFailed | None:
        """Retrieve the result of a completed task.

        Args:
            task_id: The task ID to look up.

        Returns:
            TaskComplete or TaskFailed, or None if task not yet completed.
        """
        return self._results.get(task_id)

    def clear(self) -> None:
        """Reset all state. Used for testing and session boundaries."""
        self.dependency_queue.clear()
        self._active_tasks.clear()
        self._completed_count = 0
        self._failed_count = 0
        self._results.clear()
