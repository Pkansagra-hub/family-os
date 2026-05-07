"""
k1.concierge.task.dependency_queue -- Holds chained tasks until dependencies resolve.

V2 Design Ref: Section 8.5 (Chained Tasks, TaskDependencyQueue)

Lives in the orchestrator/FSM layer -- NOT in Back. Back is a stateless
ReAct actor that receives pre-hydrated dispatches. The queue persists
across turns because chained task #2 may complete turns after task #1
dispatches.

Lifecycle:
    1. Front dispatches task-A (independent) and task-B (depends_on=task-A)
    2. task-B is enqueued in the dependency queue
    3. Back executes task-A, emits task.complete with results
    4. on_task_complete("task-A", result) hydrates task-B's $ref params
    5. Hydrated task-B is released for execution

Parameter reference syntax (V2 Section 8.5):
    "$prev.result.field"           -> parent.results[0]["field"]
    "$prev.result.field.subfield"  -> parent.results[0]["field"]["subfield"]
    "$task-XXX.result.field"       -> parent.results[0]["field"] (explicit ID form)

Hydration failure handling (V2 Section 8.5):
    If _resolve_path returns None (field not found), the raw $ref string is
    left in params. When Back reads this un-hydrated reference, it will call
    submit_result(needs_human, clarification) to ask for the missing value.
    This is graceful degradation, not a crash.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from k1.concierge.task.dispatch import TaskComplete, TaskDispatch

logger = logging.getLogger(__name__)

# Pattern matches both forms:
#   $prev.result.field.subfield
#   $task-XXX.result.field.subfield
_REF_PATTERN = re.compile(r"^\$(?:prev|[a-zA-Z0-9_-]+)\.result\.(.+)$")


@dataclass
class TaskDependencyQueue:
    """Holds tasks waiting for their dependency to complete.

    When a chained TaskDispatch arrives (depends_on is set), it is
    queued here. When the parent task completes, waiting tasks are
    hydrated and released via the execute callback.

    Attributes:
        pending:            depends_on task_id -> list of waiting dispatches.
        completed_results:  task_id -> TaskComplete (for $ref resolution).
        _execute:           Callback to execute a released task.
    """

    pending: dict[str, list[TaskDispatch]] = field(default_factory=dict)
    completed_results: dict[str, TaskComplete] = field(default_factory=dict)
    _execute: Callable[[TaskDispatch], None] | None = field(default=None, repr=False)

    def set_execute_callback(self, fn: Callable[[TaskDispatch], None]) -> None:
        """Set the callback invoked when a waiting task is released."""
        self._execute = fn

    def enqueue(self, dispatch: TaskDispatch) -> bool:
        """Attempt to enqueue a chained task.

        If the dependency has already completed, hydrate immediately
        and return False (caller should execute directly).

        If the dependency has NOT completed, buffer the task and
        return True (task is waiting).

        Args:
            dispatch: A TaskDispatch with depends_on set.

        Returns:
            True if the task was buffered (waiting for dependency).
            False if the dependency already completed (task was hydrated
            and should be executed immediately by caller).

        Raises:
            ValueError: If dispatch.depends_on is None.
        """
        if dispatch.depends_on is None:
            raise ValueError(f"Cannot enqueue task {dispatch.task_id}: depends_on is None")

        # Check if dependency already completed
        if dispatch.depends_on in self.completed_results:
            parent_result = self.completed_results[dispatch.depends_on]
            self._hydrate_dispatch(dispatch, parent_result)
            logger.info(
                "Task %s dependency %s already complete, hydrated immediately",
                dispatch.task_id,
                dispatch.depends_on,
            )
            return False

        # Buffer: dependency not yet complete
        waiters = self.pending.setdefault(dispatch.depends_on, [])
        waiters.append(dispatch)
        logger.info(
            "Task %s queued waiting for dependency %s (queue depth: %d)",
            dispatch.task_id,
            dispatch.depends_on,
            len(waiters),
        )
        return True

    def on_task_complete(self, complete: TaskComplete) -> list[TaskDispatch]:
        """Handle a task completion event.

        Stores the result, then checks if any tasks were waiting for
        this task_id. Waiting tasks are hydrated with $ref values
        from the result and returned for execution.

        Args:
            complete: The completed task result.

        Returns:
            List of hydrated TaskDispatches ready for execution.
        """
        self.completed_results[complete.task_id] = complete

        waiters = self.pending.pop(complete.task_id, [])
        released: list[TaskDispatch] = []

        for waiting in waiters:
            self._hydrate_dispatch(waiting, complete)
            released.append(waiting)
            logger.info(
                "Task %s released (dependency %s complete), hydrated params",
                waiting.task_id,
                complete.task_id,
            )

        # If execute callback is set, fire it for each released task
        if self._execute is not None:
            for task in released:
                self._execute(task)

        return released

    def _hydrate_dispatch(self, dispatch: TaskDispatch, parent: TaskComplete) -> None:
        """Replace $ref placeholders in all intent params with actual values.

        Mutates dispatch.intents[].params in place.
        TaskIntent is frozen but params dict is mutable (dict mutation
        on a frozen dataclass field is allowed).

        Pattern: $prev.result.field -> parent.results[0]["field"]
        Nested:  $prev.result.field.sub -> parent.results[0]["field"]["sub"]
        Also:    $task-XXX.result.field -> parent.results[0]["field"]
        """
        for intent in dispatch.intents:
            for key, value in list(intent.params.items()):
                if isinstance(value, str) and value.startswith("$"):
                    resolved = self._resolve_ref(value, parent)
                    if resolved is not value:  # identity check: changed
                        intent.params[key] = resolved

    def _resolve_ref(self, ref: str, parent: TaskComplete) -> Any:
        """Resolve a $ref string against a parent TaskComplete.

        Uses results[0] as the primary result object per V2 Section 8.5:
        "TaskComplete.results[0] is the primary result for $ref resolution."

        Returns the resolved value, or the original ref string if the
        pattern doesn't match (graceful degradation per design doc).
        Raises KeyError if the path exists in pattern but not in results.
        """
        match = _REF_PATTERN.match(ref)
        if not match:
            logger.warning("Invalid $ref pattern: %s (returning as-is)", ref)
            return ref

        path = match.group(1)
        parts = path.split(".")

        # Access results[0] as the primary result object
        if not parent.results:
            raise KeyError(
                f"$ref resolution failed: '{ref}' -- "
                f"parent task {parent.task_id} has no results"
            )

        current: Any = parent.results[0]

        for part in parts:
            if isinstance(current, dict):
                if part not in current:
                    raise KeyError(
                        f"$ref resolution failed: '{ref}' -- "
                        f"key '{part}' not found in {current}"
                    )
                current = current[part]
            else:
                raise KeyError(
                    f"$ref resolution failed: '{ref}' -- "
                    f"cannot traverse '{part}' on non-dict {type(current)}"
                )

        return current

    @property
    def waiting_count(self) -> int:
        """Total number of tasks waiting for dependencies."""
        return sum(len(v) for v in self.pending.values())

    @property
    def completed_count(self) -> int:
        """Number of completed task results stored."""
        return len(self.completed_results)

    def clear(self) -> None:
        """Clear all pending tasks and completed results."""
        self.pending.clear()
        self.completed_results.clear()
