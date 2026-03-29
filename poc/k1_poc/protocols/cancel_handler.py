"""
poc.k1_poc.protocols.cancel_handler -- FSM-side cancellation lifecycle.

V2 Design Ref: Section 4 (CANCELLING state)
V2 Design Ref: Section 5 (FSMTurnState: cancelled_tasks, cancellation_requested)

The CancellationHandler coordinates between:
    1. Front's cancel request (user said "cancel that").
    2. FSM setting the cancellation_requested flag.
    3. Back checking the token at tool boundaries.
    4. Deduplication when task.complete arrives after task.cancel.

Deduplication (V2 Section 5, FSMTurnState):
    If task.complete arrives for a task in cancelled_tasks, the FSM
    presents a "completed despite cancellation" message instead of
    a standard result.  The completed_before_cancel flag on the
    CancellationToken tracks this case.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from poc.k1_poc.protocols.cancellation import CancellationToken, CancelReason

if TYPE_CHECKING:
    from poc.k1_poc.ledger.store import LedgerEntry
    from poc.k1_poc.ledger.writer import LedgerWriter

logger = logging.getLogger(__name__)


class CancellationHandler:
    """Manages cancellation lifecycle for active tasks.

    The FSM creates a handler at session start and uses it to:
        - Register tokens when tasks are dispatched.
        - Cancel tokens when Front emits task.cancel.
        - Detect late completions (task.complete after cancel).
        - Clean up tokens when tasks are fully resolved.

    Attributes:
        _tokens:          Active cancellation tokens by task_id.
        _cancelled_tasks: Set of task_ids that were cancelled (for dedup).
        _on_cancel_fn:    Callback when cancel is processed.
    """

    __slots__ = ("_tokens", "_cancelled_tasks", "_on_cancel_fn", "_ledger")

    def __init__(
        self,
        on_cancel_fn: Callable[[str, str], Awaitable[None]] | None = None,
        ledger: LedgerWriter | None = None,
    ) -> None:
        self._tokens: dict[str, CancellationToken] = {}
        self._cancelled_tasks: set[str] = set()
        self._on_cancel_fn = on_cancel_fn
        self._ledger: LedgerWriter | None = ledger
        logger.info(
            "CancellationHandler initialised  has_callback=%s ledger=%s",
            on_cancel_fn is not None,
            "yes" if ledger else "no",
        )

    def set_ledger(self, ledger: LedgerWriter) -> None:
        """Wire the ledger writer after construction.

        M9 E9.1.1: Allows bootstrap to attach the ledger after
        the CancellationHandler is created.
        """
        self._ledger = ledger
        logger.info("CancellationHandler: ledger wired (session=%s)", ledger.session_id)

    def register_task(self, task_id: str) -> CancellationToken:
        """Create and register a cancellation token for a task.

        Called by FSM when a task is dispatched.  The token is passed
        to Back for cooperative cancellation checking.

        Args:
            task_id: The task to register.

        Returns:
            A fresh CancellationToken for the task.
        """
        token = CancellationToken(task_id=task_id)
        self._tokens[task_id] = token
        logger.info(
            "CancellationHandler: token created for task=%s (total_active=%d)",
            task_id,
            len(self._tokens),
        )
        return token

    async def cancel_task(
        self,
        task_id: str,
        reason: CancelReason = CancelReason.USER_REQUESTED,
        ledger: Any = None,
    ) -> bool:
        """Cancel a task (async version with callback).

        Called by FSM when Front emits task.cancel.  Sets the token
        so Back will see it at the next tool boundary check.
        V3 M1 E1.2.3: Optional ledger param for event sourcing.

        Args:
            task_id: The task to cancel.
            reason:  Why it is being cancelled.
            ledger:  Optional LedgerWriter for event sourcing.

        Returns:
            True if the task was active and cancelled.
            False if the task is unknown or already cancelled.
        """
        token = self._tokens.get(task_id)
        if token is None:
            logger.warning("Cancel requested for unknown task: %s", task_id)
            return False

        if token.is_cancelled:
            return False  # Already cancelled (idempotent)

        # M9 E9.1.1: Ledger write BEFORE in-memory mutation
        if self._ledger is not None:
            from poc.k1_poc.events.task import TaskCancelled as TaskCancelledEvent

            self._ledger.append_sync(
                TaskCancelledEvent(
                    session_id=self._ledger.session_id,
                    task_id=task_id,
                    reason=reason.value,
                    cancel_reason=reason.value,
                    had_token=True,
                    actor="fsm",
                )
            )

        token.cancel(reason)
        self._cancelled_tasks.add(task_id)

        if self._on_cancel_fn is not None:
            await self._on_cancel_fn(task_id, reason.value)

        logger.info("Task %s cancelled: %s", task_id, reason.value)
        return True

    def request_cancel(
        self,
        task_id: str,
        reason: CancelReason = CancelReason.USER_REQUESTED,
        ledger: Any = None,
    ) -> bool:
        """Cancel a task (sync version for FSM controller).

        Same as cancel_task but synchronous -- does NOT invoke the
        on_cancel_fn callback.  Used by the FSM event router which
        runs in a sync context.

        If the task has no registered token, one is created on the fly
        so the cancellation is still tracked for dedup.
        V3 M1 E1.2.3: Optional ledger param for event sourcing.

        Args:
            task_id: The task to cancel.
            reason:  Why it is being cancelled.
            ledger:  Optional LedgerWriter for event sourcing.

        Returns:
            True if cancellation was newly recorded.
            False if already cancelled (idempotent).
        """
        token = self._tokens.get(task_id)
        if token is None:
            token = self.register_task(task_id)

        if token.is_cancelled:
            return False

        # M9 E9.1.1: Ledger write BEFORE in-memory mutation
        if self._ledger is not None:
            from poc.k1_poc.events.task import TaskCancelled as TaskCancelledEvent

            self._ledger.append_sync(
                TaskCancelledEvent(
                    session_id=self._ledger.session_id,
                    task_id=task_id,
                    reason=reason.value,
                    cancel_reason=reason.value,
                    had_token=True,
                    actor="fsm",
                )
            )

        token.cancel(reason)
        self._cancelled_tasks.add(task_id)
        logger.info("Task %s cancel requested (sync): %s", task_id, reason.value)
        return True

    def confirm_cancel(self, task_id: str) -> bool:
        """Confirm a cancellation and clean up.

        Called by FSM when task.failed with reason=cancelled arrives.
        Returns whether the cancel was expected (task was in set).

        Args:
            task_id: The task whose cancellation is confirmed.

        Returns:
            True if task was in cancelled set (expected cancel).
            False if task was not in set (unexpected).
        """
        was_expected = task_id in self._cancelled_tasks
        self.cleanup_task(task_id)
        return was_expected

    def is_cancelled(self, task_id: str) -> bool:
        """Check if a task was cancelled.

        Used for deduplication: if task.complete arrives for a
        cancelled task, FSM presents "it went through" message.

        Args:
            task_id: The task to check.

        Returns:
            True if the task is in the cancelled_tasks set.
        """
        return task_id in self._cancelled_tasks

    def get_token(self, task_id: str) -> CancellationToken | None:
        """Get the cancellation token for a task.

        Args:
            task_id: The task to look up.

        Returns:
            The CancellationToken, or None if not registered.
        """
        return self._tokens.get(task_id)

    def handle_late_completion(self, task_id: str) -> bool:
        """Handle task.complete arriving after task.cancel.

        V2 Design Ref: Section 5, FSMTurnState dedup.

        If a task was cancelled but completed anyway (task.complete
        arrived after cancel was emitted but before Back checked the
        token), the FSM presents "it actually went through" message.

        Args:
            task_id: The task that completed.

        Returns:
            True if this was a late completion (task was cancelled).
            False if the task was not cancelled.
        """
        if task_id in self._cancelled_tasks:
            token = self._tokens.get(task_id)
            if token is not None:
                token.completed_before_cancel = True
            logger.info(
                "Late completion for cancelled task %s -- 'it went through'",
                task_id,
            )
            return True
        return False

    def cleanup_task(self, task_id: str) -> None:
        """Remove token after task is fully resolved.

        Called by FSM after the cancellation or completion flow is
        complete and Front has presented the result to the user.

        Args:
            task_id: The task to clean up.
        """
        self._tokens.pop(task_id, None)
        self._cancelled_tasks.discard(task_id)
        logger.debug("CancellationHandler: cleaned up task %s", task_id)

    # ------------------------------------------------------------------
    # M9 E9.1.3: Rebuild from ledger events
    # ------------------------------------------------------------------

    def rebuild_from_events(self, entries: list[LedgerEntry]) -> int:
        """Rebuild cancel state from ledger event replay.

        M9 E9.1.3: Called by CrashRecoveryOrchestrator during startup.
        Reconstructs _tokens and _cancelled_tasks from task lifecycle
        events in the ledger.

        Args:
            entries: Ordered ledger entries for the session.

        Returns:
            Number of tokens restored.
        """
        from poc.k1_poc.ledger.projections import project_cancel_state

        active_ids, cancelled_ids = project_cancel_state(entries)

        # Rebuild tokens for active (non-terminal) tasks
        for task_id in active_ids:
            if task_id not in self._tokens:
                self._tokens[task_id] = CancellationToken(task_id=task_id)

        # Rebuild cancelled set and mark tokens
        for task_id in cancelled_ids:
            self._cancelled_tasks.add(task_id)
            if task_id in self._tokens:
                if not self._tokens[task_id].is_cancelled:
                    self._tokens[task_id].cancel(CancelReason.USER_REQUESTED)
            else:
                # Token was cleaned up before crash -- recreate cancelled
                token = CancellationToken(task_id=task_id)
                token.cancel(CancelReason.USER_REQUESTED)
                self._tokens[task_id] = token

        logger.info(
            "CancellationHandler: rebuilt from events " "(active=%d, cancelled=%d)",
            len(active_ids),
            len(cancelled_ids),
        )
        return len(active_ids) + len(cancelled_ids)

    @property
    def active_count(self) -> int:
        """Number of active (registered) cancellation tokens."""
        return len(self._tokens)

    @property
    def cancelled_count(self) -> int:
        """Number of tasks in the cancelled set."""
        return len(self._cancelled_tasks)

    def reset(self) -> None:
        """Reset all state. Called at session end or test teardown."""
        self._tokens.clear()
        self._cancelled_tasks.clear()
