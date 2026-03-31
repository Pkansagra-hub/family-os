"""
k1.concierge.protocols.cancellation -- Cooperative cancellation for Back tasks.

V2 Design Ref: Section 4 (FSM state: CANCELLING)
V2 Design Ref: Section 5 (FSMTurnState: cancellation_requested, cancelled_tasks)

Cancellation is cooperative, not preemptive.  Back checks the token at
tool boundaries (between tool calls in the ReAct loop).  If the token
is set, Back aborts the current ReAct loop and emits task.failed with
reason=cancelled.

Key contract (V2 Section 4, CANCELLING state):
    1. Front emits k1.orchestration.task.cancel.v1 (URGENT priority).
    2. FSM sets the cancellation_requested flag in FSMTurnState.
    3. Back checks token.is_cancelled before each tool call.
    4. If cancelled: Back raises TaskCancelledError, emits task.failed.
    5. If task completed before cancel is checked:
       completed_before_cancel=True (FSM presents "it went through").
    6. FSM deduplicates: if task.complete arrives after cancel, it checks
       cancelled_tasks set and presents "it actually went through" message.

Cancel reasons (V2 Section 4):
    USER_REQUESTED: User explicitly said "cancel that"
    TIMEOUT:        Task exceeded its time budget
    SUPERSEDED:     New task replaces this one ("do Marriott instead")
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CancelReason(str, Enum):
    """Why a task was cancelled.

    V2 Design Ref: Section 4, CANCELLING state.

    USER_REQUESTED: User explicitly cancelled ("cancel that").
    TIMEOUT:        Task exceeded its time budget.
    SUPERSEDED:     New task replaces this one.
    """

    USER_REQUESTED = "user_requested"
    TIMEOUT = "timeout"
    SUPERSEDED = "superseded"


@dataclass
class CancellationToken:
    """Cooperative cancellation token for a single task.

    The FSM creates a token when a task is dispatched and passes it
    to Back.  Back calls token.check() between tool invocations.
    Front triggers cancellation by calling token.cancel() via the
    CancellationHandler.

    V2 Design Ref: Section 5, FSMTurnState.cancellation_requested.

    Attributes:
        task_id:                The task this token governs.
        _cancelled:             Whether cancellation was requested.
        _cancel_reason:         Why the task was cancelled.
        _cancel_time_ns:        When cancellation was requested (monotonic).
        completed_before_cancel: True if task.complete arrived before
                                 Back checked the token.
        _event:                 asyncio.Event for wait_for_cancel().
    """

    task_id: str
    _cancelled: bool = field(default=False, init=False, repr=False)
    _cancel_reason: CancelReason | None = field(default=None, init=False)
    _cancel_time_ns: int = field(default=0, init=False)
    completed_before_cancel: bool = field(default=False, init=False)
    _event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        return self._cancelled

    @property
    def cancel_reason(self) -> CancelReason | None:
        """The reason for cancellation, or None if not cancelled."""
        return self._cancel_reason

    @property
    def cancel_time_ns(self) -> int:
        """Monotonic timestamp of when cancel was requested."""
        return self._cancel_time_ns

    def cancel(self, reason: CancelReason = CancelReason.USER_REQUESTED) -> None:
        """Request cancellation.

        Safe to call multiple times -- only the first cancel takes
        effect (idempotent).  Subsequent calls are no-ops.

        Args:
            reason: Why the task is being cancelled.
        """
        if not self._cancelled:
            self._cancelled = True
            self._cancel_reason = reason
            self._cancel_time_ns = time.monotonic_ns()
            self._event.set()
            logger.info(
                "CancellationToken: task=%s cancelled reason=%s",
                self.task_id,
                reason.value,
            )

    def check(self) -> None:
        """Check cancellation at a tool boundary.

        Back should call this between each tool invocation in the
        ReAct loop.  If cancelled, raises TaskCancelledError which
        the ReAct loop catches to abort cleanly.

        Raises:
            TaskCancelledError: If cancellation has been requested.
        """
        if self._cancelled:
            raise TaskCancelledError(self.task_id, self._cancel_reason)

    async def wait_for_cancel(self, timeout: float | None = None) -> bool:
        """Wait for cancellation to be requested.

        Useful for background watchers that need to react to cancel.

        Args:
            timeout: Max seconds to wait.  None = wait forever.

        Returns:
            True if cancelled, False if timed out.
        """
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False


class TaskCancelledError(Exception):
    """Raised when a task is cancelled via its CancellationToken.

    Back catches this in the ReAct loop to abort cleanly and emit
    task.failed with reason=cancelled.
    """

    def __init__(
        self,
        task_id: str,
        reason: CancelReason | None = None,
    ) -> None:
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"Task {task_id} cancelled: {reason}")
