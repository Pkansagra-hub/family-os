"""IMailboxPort -- Planner inbound mailbox protocol [F12].

The mailbox port is the Planner's sole inbound entry point.  The protocol
is consumer-driven: structurally identical to ``IPlannerMailbox`` defined on
the Orchestrator side (SS4.2).  The Planner exposes an object satisfying it.

Design decisions (SS15.2)
-------------------------
- ``enqueue()`` returns ``None``, not ``PlanAck``.  ``PlannerAdapter`` on the
  Orchestrator side constructs PlanAck(ACCEPTED/REJECTED).
- ``micro_replan()`` returns ``CommittedPlan`` **directly** -- synchronous
  request-response, no event bus, no mailbox queuing.
- ``send_cancel()`` is best-effort.  No effect post-COMMIT.

Mailbox properties (SS4.1)
--------------------------
- Type: MPSC + FIFO (single priority class: INTERACTIVE)
- Max depth: 5 (rejects beyond with MailboxFullError)
- Consumer: PlannerAgent (single, sequential -- V1 one plan at a time)

Callers
-------
- PlannerAgent (dequeue side)
- Orchestrator's PlannerAdapter (enqueue side)

Adapter: MailboxAdapter [F28]

Import graph (Layer 1)
----------------------
k1.planner.ports.mailbox_port
  -> k1.orchestrator.types  (PlanRequest, MicroReplanRequest, CommittedPlan)
  -> typing, typing_extensions
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from k1.orchestrator.types import CommittedPlan, MicroReplanRequest, PlanRequest


@runtime_checkable
class IMailboxPort(Protocol):
    """Planner inbound mailbox -- enqueue, cancel, and micro-replan.

    This is a structural protocol (``typing.Protocol``).  Any object with
    matching method signatures satisfies it via structural subtyping.

    Thread / task safety
    --------------------
    ``enqueue()`` is safe for concurrent callers (``asyncio.Queue`` is
    task-safe in the production adapter).  ``send_cancel()`` is likewise
    task-safe.  ``micro_replan()`` acquires the plan lock and serialises
    with in-flight plans.
    """

    async def dequeue(self) -> PlanRequest:
        """Block until a plan request is available and return it.

        Called by PlannerAgent in the dequeue loop (SS24.1.2).  Blocks
        until a PlanRequest is available in the FIFO queue.

        Returns:
            The next PlanRequest in FIFO order.
        """
        ...  # pragma: no cover

    async def enqueue(self, request: PlanRequest) -> None:
        """Enqueue a plan request for asynchronous processing.

        Args:
            request: The plan request to enqueue.

        Raises:
            MailboxFullError: If mailbox depth >= 5.
        """
        ...  # pragma: no cover

    async def send_cancel(self, request_id: str) -> None:
        """Signal cancellation for an in-flight plan request.

        Best-effort: the plan may have already committed.  If the plan was
        already delivered via ``k1.planner.plan.ready.v1``, the cancel has
        no effect.

        Args:
            request_id: The ``request_id`` of the plan to cancel.
        """
        ...  # pragma: no cover

    def drain(self) -> List[PlanRequest]:
        """Non-blocking drain of all queued requests.

        Called by PlannerAgent during SHUTDOWN (SS23.5 step 2) to
        remove all pending requests from the mailbox.  Returns them
        so the caller can emit ``plan.cancelled.v1`` for each.

        This is a **synchronous** method -- it must not block.

        Returns:
            List of PlanRequests that were in the queue.  Empty list
            if queue was already empty.
        """
        ...  # pragma: no cover

    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
        """Synchronous micro-replan -- Planner responds inline.

        Bypasses the mailbox queue.  The caller (PlannerAdapter) wraps this
        with ``asyncio.wait_for(timeout=10.0)`` on its side.

        Args:
            request: The micro-replan request with completed results,
                remaining steps, and optional discoveries / failure context.

        Returns:
            A new ``CommittedPlan`` covering the remaining steps.
        """
        ...  # pragma: no cover


__all__ = ["IMailboxPort"]
