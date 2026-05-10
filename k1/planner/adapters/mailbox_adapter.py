"""MailboxAdapter -- production mailbox implementation [F28].

Implements ``IMailboxPort`` (SS15.2) using an ``asyncio.Queue``-backed
in-memory MPSC FIFO queue with cancel-set tracking and a V1
single-plan lock.

Adapter wiring (SS16.1.1, SS16.3):
    IMailboxPort -> MailboxAdapter -> asyncio.Queue[PlanRequest]

Properties:
    - MPSC + FIFO (single priority class: INTERACTIVE)
    - Bounded at ``max_depth`` (default 5)
    - ``enqueue()`` is task-safe (``asyncio.Queue.put_nowait``)
    - ``dequeue()`` blocks until a request is available
    - ``micro_replan()`` acquires ``_micro_replan_lock`` -- serialises micro-replan calls
      against any in-flight micro_replan inside this adapter (NOT the same lock as
      ``PlannerAgent._plan_lock``, which serialises full pipeline runs)
    - Shutdown: rejects with ``ShutdownError`` after shutdown signal

Import graph (Layer 2)
----------------------
k1.planner.adapters.mailbox_adapter
  -> k1.planner.ports.mailbox_port  (IMailboxPort)
  -> k1.orchestrator.types          (PlanRequest, MicroReplanRequest, CommittedPlan)
  -> k1.planner.types               (MailboxFullError, ShutdownError)
  -> asyncio
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Set

from k1.orchestrator.types import CommittedPlan, MicroReplanRequest, PlanRequest
from k1.planner.types import MailboxFullError, ShutdownError

logger = logging.getLogger(__name__)


class MailboxAdapter:
    """Production mailbox adapter (SS16.1.1).

    Bounded async FIFO queue for inbound ``PlanRequest`` messages.
    Single priority class ``INTERACTIVE`` -- no WFQ weighting (SS4.1).
    """

    __slots__ = (
        "_queue",
        "_cancel_set",
        "_micro_replan_lock",
        "_max_depth",
        "_priority_class",
        "_shutdown",
        "_pipeline_controller",
    )

    def __init__(
        self,
        max_depth: int = 5,
        priority_class: str = "INTERACTIVE",
    ) -> None:
        self._queue: asyncio.Queue[PlanRequest] = asyncio.Queue(maxsize=max_depth)
        self._cancel_set: Set[str] = set()
        # NOTE: ``_micro_replan_lock`` is a *distinct* lock instance from
        # ``PlannerAgent._plan_lock``. They serialise different concerns:
        #   - PlannerAgent._plan_lock: one full pipeline run at a time per agent
        #   - MailboxAdapter._micro_replan_lock: one micro_replan() call at a time
        # Do not collapse or share these locks.
        self._micro_replan_lock: asyncio.Lock = asyncio.Lock()
        self._max_depth: int = max_depth
        self._priority_class: str = priority_class
        self._shutdown: bool = False
        self._pipeline_controller: Optional[object] = None

    # ------------------------------------------------------------------
    # IMailboxPort implementation
    # ------------------------------------------------------------------

    async def enqueue(self, request: PlanRequest) -> None:
        """Enqueue a plan request for async processing.

        Raises ``MailboxFullError`` if depth >= ``max_depth``.
        Raises ``ShutdownError`` if the adapter is shutting down.
        """
        if self._shutdown:
            raise ShutdownError(
                "Mailbox is shutting down, not accepting new requests",
                stage="ENQUEUE",
            )
        try:
            self._queue.put_nowait(request)
        except asyncio.QueueFull:
            raise MailboxFullError(
                f"Mailbox full (depth={self._max_depth})",
                stage="ENQUEUE",
                request_id=getattr(request, "request_id", ""),
            )
        logger.debug(
            "Enqueued plan request",
            extra={"request_id": getattr(request, "request_id", ""), "depth": self._queue.qsize()},
        )

    async def dequeue(self) -> PlanRequest:
        """Block until a plan request is available and return it (FIFO)."""
        return await self._queue.get()

    async def send_cancel(self, request_id: str) -> None:
        """Signal cancellation for an in-flight plan request.

        Best-effort: PlannerAgent checks ``_cancel_set`` between stages.
        """
        self._cancel_set.add(request_id)
        logger.debug("Cancel signal received", extra={"request_id": request_id})

    def drain(self) -> List[PlanRequest]:
        """Non-blocking drain of all queued requests (SHUTDOWN step 2)."""
        drained: List[PlanRequest] = []
        while not self._queue.empty():
            try:
                drained.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return drained

    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
        """Synchronous micro-replan bypassing the mailbox queue.

        Acquires ``_micro_replan_lock`` to serialise concurrent micro_replan
        calls inside this adapter,
        then delegates to ``PipelineController.micro_replan()``.

        The caller (PlannerAdapter) wraps this with
        ``asyncio.wait_for(timeout=10.0)`` on the Orchestrator side.
        """
        if self._shutdown:
            raise ShutdownError(
                "Mailbox is shutting down, not accepting micro-replan",
                stage="MICRO_REPLAN",
            )
        async with self._micro_replan_lock:
            if self._pipeline_controller is None:
                raise RuntimeError(
                    "PipelineController not set on MailboxAdapter -- "
                    "call set_pipeline_controller() before micro_replan()"
                )
            # PipelineController.micro_replan returns Optional[CommittedPlan]
            result = await self._pipeline_controller.micro_replan(request)  # type: ignore[attr-defined]
            if result is None:
                raise RuntimeError("micro_replan returned None (pipeline failure)")
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def set_pipeline_controller(self, controller: object) -> None:
        """Inject the PipelineController for micro-replan delegation.

        Called by PlannerFactory during the wiring sequence.
        """
        self._pipeline_controller = controller

    def is_cancel_requested(self, request_id: str) -> bool:
        """Check if cancellation was requested for the given plan."""
        return request_id in self._cancel_set

    def clear_cancel(self, request_id: str) -> None:
        """Remove a processed cancellation signal."""
        self._cancel_set.discard(request_id)

    def begin_shutdown(self) -> None:
        """Signal the mailbox to stop accepting new requests."""
        self._shutdown = True

    @property
    def depth(self) -> int:
        """Current queue depth."""
        return self._queue.qsize()

    @property
    def max_depth(self) -> int:
        """Maximum queue depth."""
        return self._max_depth

    @property
    def priority_class(self) -> str:
        """Priority class (always INTERACTIVE in V1)."""
        return self._priority_class


__all__ = ["MailboxAdapter"]
