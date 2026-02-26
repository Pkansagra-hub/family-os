"""
poc.k1_poc.protocols.suspension_manager -- FSM-side suspension lifecycle.

V2 Design Ref: Section 4 (CLARIFYING_WORKER state management)
V2 Design Ref: Section 5 (TaskStateEntry.hil_suspensions_count, pending_hil)

The SuspensionManager coordinates between:
    1. Back emitting task.suspended (needs human input).
    2. FSM updating task_state to SUSPENDED.
    3. Front translating HITL to natural language (HITL_RELAY).
    4. User responding.
    5. Front emitting task.resume with resolution (HITL_RESOLVE).
    6. Back resuming from saved ReAct history.

Limits enforced (V2 Section 5):
    - Max 2 suspensions per task (hil_suspensions_count).
    - Max 1 concurrent suspension per task.
    - Timeout per type: clarification=60s, approval=120s, selection=90s.
    - FSM auto-cancels on timeout.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from poc.k1_poc.protocols.suspension import (
    SuspensionLimitExceeded,
    SuspensionRequest,
    SuspensionResolution,
    _get_max_suspensions_per_task,
)

logger = logging.getLogger(__name__)


class SuspensionManager:
    """Manages active suspensions and enforces limits.

    The FSM creates a SuspensionManager at session start.  When Back
    emits task.suspended, the FSM calls manager.suspend() which
    validates limits and starts a timeout watcher.  When Front emits
    task.resume, the FSM calls manager.resolve() which returns the
    original request (with ReAct history) for Back resume.

    Attributes:
        _active:            Currently suspended tasks (task_id -> request).
        _suspension_counts: How many times each task has been suspended.
        _timeout_tasks:     Active timeout watcher asyncio.Tasks.
        _on_timeout_fn:     Callback when suspension times out.
        _on_resume_fn:      Callback when suspension is resolved.
    """

    __slots__ = (
        "_active",
        "_contexts",
        "_suspension_counts",
        "_timeout_tasks",
        "_on_timeout_fn",
        "_on_resume_fn",
    )

    def __init__(
        self,
        on_timeout_fn: Callable[[str], Awaitable[None]] | None = None,
        on_resume_fn: Callable[[str, SuspensionResolution], Awaitable[None]] | None = None,
    ) -> None:
        self._active: dict[str, SuspensionRequest] = {}
        self._contexts: dict[str, dict] = {}
        self._suspension_counts: dict[str, int] = {}
        self._timeout_tasks: dict[str, asyncio.Task[None]] = {}
        self._on_timeout_fn = on_timeout_fn
        self._on_resume_fn = on_resume_fn
        logger.info(
            "SuspensionManager initialised  has_timeout_fn=%s has_resume_fn=%s",
            on_timeout_fn is not None,
            on_resume_fn is not None,
        )

    async def suspend(self, request: SuspensionRequest) -> None:
        """Register a suspension request from Back.

        Validates limits (max 2 per task, 1 concurrent per task)
        and starts the timeout watcher.

        Args:
            request: The suspension request from Back.

        Raises:
            SuspensionLimitExceeded: If task has exceeded max suspensions.
            ValueError: If task already has an active suspension.
        """
        task_id = request.task_id

        # Check concurrent suspension limit (max 1 per task)
        if task_id in self._active:
            raise ValueError(
                f"Task {task_id} already has an active suspension. "
                f"Max 1 concurrent suspension per task."
            )

        # Check total suspension limit (from config, V3 E0.2.2)
        count = self._suspension_counts.get(task_id, 0) + 1
        max_suspensions = _get_max_suspensions_per_task()
        if count > max_suspensions:
            raise SuspensionLimitExceeded(task_id, count)

        self._suspension_counts[task_id] = count
        request.suspension_count = count
        self._active[task_id] = request

        # Start timeout watcher
        timeout = request.timeout_seconds
        self._timeout_tasks[task_id] = asyncio.create_task(self._watch_timeout(task_id, timeout))

        logger.info(
            "Task %s suspended (%s): %s [count=%d, timeout=%.0fs]",
            task_id,
            request.suspension_type.value,
            request.question,
            count,
            timeout,
        )

    async def resolve(self, resolution: SuspensionResolution) -> SuspensionRequest | None:
        """Resolve a suspension with user's answer.

        Cancels the timeout watcher and returns the original request
        (which contains the ReAct history for Back resume).

        Args:
            resolution: The user's answer from Front.

        Returns:
            The original SuspensionRequest, or None if task not suspended.
        """
        task_id = resolution.task_id
        request = self._active.pop(task_id, None)

        if request is None:
            logger.warning("Resolution for non-suspended task: %s", task_id)
            return None

        # Cancel timeout watcher
        timer = self._timeout_tasks.pop(task_id, None)
        if timer is not None and not timer.done():
            timer.cancel()

        if self._on_resume_fn is not None:
            await self._on_resume_fn(task_id, resolution)

        logger.info("Task %s resumed with: %s", task_id, resolution.resolution)
        return request

    async def _watch_timeout(self, task_id: str, timeout: float) -> None:
        """Watch for suspension timeout.

        If user does not respond within timeout, FSM auto-cancels
        the task (V2 Section 4, CLARIFYING_WORKER timeout).

        Args:
            task_id: The suspended task.
            timeout: Seconds to wait before triggering timeout.
        """
        try:
            await asyncio.sleep(timeout)
        except asyncio.CancelledError:
            return

        if task_id in self._active:
            logger.warning(
                "Suspension timeout for task %s after %.0fs",
                task_id,
                timeout,
            )
            self._active.pop(task_id, None)
            self._timeout_tasks.pop(task_id, None)
            if self._on_timeout_fn is not None:
                await self._on_timeout_fn(task_id)

    def is_suspended(self, task_id: str) -> bool:
        """Check if a task is currently suspended."""
        return task_id in self._active

    def get_request(self, task_id: str) -> SuspensionRequest | None:
        """Get the active suspension request for a task."""
        return self._active.get(task_id)

    @property
    def active_count(self) -> int:
        """Number of currently suspended tasks."""
        return len(self._active)

    def cleanup_task(self, task_id: str) -> None:
        """Clean up all suspension state for a task.

        Called by FSM after the task is fully resolved (completed,
        failed, or cancelled after timeout).

        Args:
            task_id: The task to clean up.
        """
        self._active.pop(task_id, None)
        self._contexts.pop(task_id, None)
        timer = self._timeout_tasks.pop(task_id, None)
        if timer is not None and not timer.done():
            timer.cancel()
        self._suspension_counts.pop(task_id, None)

    # ------------------------------------------------------------------
    # Sync context management (for FSM controller, Epic 2.2)
    # ------------------------------------------------------------------

    def store_context(self, task_id: str, context: dict) -> None:
        """Store suspension context (sync, for FSM controller).

        The FSM controller is synchronous. This stores the raw payload
        context for later retrieval on task.resume without starting
        an async timeout watcher.

        Args:
            task_id: The suspended task's ID.
            context: The raw payload dict from the suspension envelope.
        """
        self._contexts[task_id] = context
        logger.debug("SuspensionManager: stored context for task %s", task_id)

    def pop_context(self, task_id: str) -> dict | None:
        """Pop and return stored context for a task (sync).

        Returns None if no context was stored.

        Args:
            task_id: The task whose context to retrieve.
        """
        ctx = self._contexts.pop(task_id, None)
        if ctx is not None:
            logger.debug("SuspensionManager: popped context for task %s", task_id)
        return ctx

    def get_context(self, task_id: str) -> dict | None:
        """Non-destructive read of stored context for a task.

        Unlike pop_context, this does NOT remove the context.
        Safe to call when the context may still be needed (e.g. if
        front delivery might fail and we need to retry).

        Args:
            task_id: The task whose context to peek at.
        """
        return self._contexts.get(task_id)

    def has_context(self, task_id: str) -> bool:
        """Check if context exists for a task."""
        return task_id in self._contexts or task_id in self._active

    def reset(self) -> None:
        """Reset all state. Called at session end or test teardown."""
        self._active.clear()
        self._contexts.clear()
        for timer in self._timeout_tasks.values():
            if not timer.done():
                timer.cancel()
        self._timeout_tasks.clear()
        self._suspension_counts.clear()
