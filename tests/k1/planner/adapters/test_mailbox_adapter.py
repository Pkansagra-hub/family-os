"""TestMailboxAdapter -- in-memory IMailboxPort implementation (SS16.2.1).

Implements the IMailboxPort Protocol (SS15.2) with:
- Constructor injection of preset PlanRequests
- Capture-mode recording of all enqueue/cancel/micro_replan calls
- Zero I/O, purely in-memory FIFO queue
- Protocol-structural compliance with IMailboxPort

File location: tests/k1/planner/adapters/ (SS30.3)
Never importable from production code.
"""

from __future__ import annotations

from typing import List, Optional

from k1.orchestrator.types import CommittedPlan, MicroReplanRequest, PlanRequest
from k1.planner.types import MailboxFullError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAILBOX_MAX_DEPTH = 5


class TestMailboxAdapter:
    """In-memory IMailboxPort for deterministic testing (SS16.2.1).

    Constructor
    -----------
    preset_requests : List[PlanRequest]
        Requests pre-loaded into the FIFO queue at construction time.

    Internal state
    --------------
    _queue : List[PlanRequest]
        FIFO queue, pre-loaded from preset_requests.
    _enqueue_log : List[PlanRequest]
        Capture list of all enqueue() calls.
    _cancel_log : List[str]
        Capture list of all send_cancel() request_id arguments.
    _micro_replan_log : List[MicroReplanRequest]
        Capture list of all micro_replan() calls.
    _micro_replan_result : Optional[CommittedPlan]
        Injectable return value for micro_replan(). If None and
        _micro_replan_error is None, raises RuntimeError.
    _micro_replan_error : Optional[Exception]
        If set, micro_replan() raises this instead of returning.
    """

    def __init__(
        self,
        preset_requests: Optional[List[PlanRequest]] = None,
    ) -> None:
        self._queue: List[PlanRequest] = list(preset_requests or [])
        self._enqueue_log: List[PlanRequest] = []
        self._cancel_log: List[str] = []
        self._micro_replan_log: List[MicroReplanRequest] = []
        self._micro_replan_result: Optional[CommittedPlan] = None
        self._micro_replan_error: Optional[Exception] = None
        self._drain_log: List[bool] = []

    # ------------------------------------------------------------------
    # Configuration helpers (test-only)
    # ------------------------------------------------------------------

    def set_micro_replan_result(self, plan: CommittedPlan) -> None:
        """Set the return value for micro_replan()."""
        self._micro_replan_result = plan
        self._micro_replan_error = None

    def set_micro_replan_error(self, error: Exception) -> None:
        """Configure micro_replan() to raise an error."""
        self._micro_replan_error = error
        self._micro_replan_result = None

    # ------------------------------------------------------------------
    # IMailboxPort Protocol methods
    # ------------------------------------------------------------------

    async def dequeue(self) -> PlanRequest:
        """Pop the first request from the FIFO queue.

        Raises IndexError if the queue is empty (test does not need to
        block -- callers should pre-load requests).
        """
        if not self._queue:
            raise IndexError("TestMailboxAdapter: queue is empty")
        return self._queue.pop(0)

    async def enqueue(self, request: PlanRequest) -> None:
        """Enqueue a plan request. Raises MailboxFullError at depth >= 5."""
        self._enqueue_log.append(request)
        if len(self._queue) >= MAILBOX_MAX_DEPTH:
            raise MailboxFullError(f"Mailbox full: depth {len(self._queue)} >= {MAILBOX_MAX_DEPTH}")
        self._queue.append(request)

    async def send_cancel(self, request_id: str) -> None:
        """Record cancellation request."""
        self._cancel_log.append(request_id)

    def drain(self) -> List[PlanRequest]:
        """Non-blocking drain of all queued requests."""
        self._drain_log.append(True)
        drained = list(self._queue)
        self._queue.clear()
        return drained

    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
        """Return injectable result or raise injectable error."""
        self._micro_replan_log.append(request)
        if self._micro_replan_error is not None:
            raise self._micro_replan_error
        if self._micro_replan_result is not None:
            return self._micro_replan_result
        raise RuntimeError("TestMailboxAdapter.micro_replan: no result or error configured")

    # ------------------------------------------------------------------
    # Assertion helpers (test-only)
    # ------------------------------------------------------------------

    def assert_enqueue_count(self, n: int) -> None:
        """Assert that enqueue() was called exactly n times."""
        actual = len(self._enqueue_log)
        assert actual == n, f"Expected {n} enqueue calls, got {actual}"

    def assert_cancel_ids(self, ids: List[str]) -> None:
        """Assert the exact sequence of cancel request_ids."""
        assert self._cancel_log == ids, f"Expected cancel_ids {ids}, got {self._cancel_log}"

    def get_dequeue_order(self) -> List[str]:
        """Return request_ids in the order they would be dequeued (FIFO)."""
        return [r.request_id for r in self._queue]

    @property
    def enqueue_log(self) -> List[PlanRequest]:
        """Read-only access to enqueue call log."""
        return list(self._enqueue_log)

    @property
    def cancel_log(self) -> List[str]:
        """Read-only access to cancel call log."""
        return list(self._cancel_log)

    @property
    def micro_replan_log(self) -> List[MicroReplanRequest]:
        """Read-only access to micro_replan call log."""
        return list(self._micro_replan_log)

    @property
    def queue_depth(self) -> int:
        """Current number of items in the queue."""
        return len(self._queue)
