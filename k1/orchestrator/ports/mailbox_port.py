"""
k1.orchestrator.ports.mailbox_port -- IMailboxPort port (1.4.1).

In-process priority mailbox for Orchestrator message ingestion.

Design:
  - All methods SYNC (mailbox is in-process, no I/O).
  - WFQ (Weighted Fair Queuing) across 3 priority classes:
    REALTIME (60%) > INTERACTIVE (30%) > BACKGROUND (10%).
  - dequeue() must be O(1) or O(log n).
  - max_depth: 100 messages. enqueue() raises MailboxFullError when full.

Message types accepted (MailboxMessage union):
  - TaskEnvelope     -- inbound task from Concierge
  - CommittedPlan    -- plan ready from Planner (via event bus routing)
  - WorkflowRunRequest -- scheduled workflow trigger
  - WorkflowSaveRequest -- user saves a workflow
  - InterruptRequest -- cancel/pause from external source

Consumers:
  - OrchestratorService._mailbox_loop() (6.2.5) dequeues messages.
  - OrchestratorService.process() routes by isinstance dispatch.
  - Event handlers enqueue plan/interrupt events from IEventSubscriptionPort.

Production adapter: MailboxAdapter (6.1.1) in adapters/mailbox_adapter.py
Test adapter: TestMailboxAdapter (6.1.8) in adapters/test_mailbox_adapter.py

References:
  - ORCH-001 (actor-based single-mailbox architecture)
  - docs/whiteboard/schema_whiteboard.md (S9 -- mailbox durability)

Exports:
  IMailboxPort
  MailboxMessage (type alias)
  MailboxFullError
"""

from __future__ import annotations

from typing import Optional, Protocol, Union, runtime_checkable

from k1.orchestrator.types import (
    CommittedPlan,
    InterruptRequest,
    TaskEnvelope,
    WorkflowRunRequest,
    WorkflowSaveRequest,
)

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------

MailboxMessage = Union[
    TaskEnvelope,
    CommittedPlan,
    WorkflowRunRequest,
    WorkflowSaveRequest,
    InterruptRequest,
]
"""Union of all message types accepted by the Orchestrator mailbox.

PlanFailedEvent and PlanCancelledEvent are routed through this mailbox
by IEventSubscriptionPort handlers, but they are Dict[str, Any] payloads
deserialized into these types by the handler -- not separate dataclasses
enqueued directly. The handler converts them before enqueue.
"""


class MailboxFullError(Exception):
    """Raised when mailbox depth >= max_depth (100) and enqueue is attempted.

    Concierge-side CB_ORCHESTRATOR should catch this (or the TaskAck
    REJECTED_FULL status) and degrade gracefully.
    """


# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IMailboxPort(Protocol):
    """
    In-process priority mailbox for the Orchestrator actor.

    This is the single entry point for all messages into the Orchestrator.
    Messages are prioritised via WFQ across three priority classes:
      - REALTIME    (60% of dequeue slots) -- interrupts, safety band changes
      - INTERACTIVE (30% of dequeue slots) -- user tasks, plan results
      - BACKGROUND  (10% of dequeue slots) -- workflow triggers, gap scans

    All methods are synchronous (no I/O). The mailbox is in-process
    and does not require network or disk access.

    Thread safety:
      Implementations MUST support concurrent enqueue() calls from
      multiple threads/tasks. dequeue() is called from a single
      mailbox loop task.
    """

    def enqueue(
        self,
        message: MailboxMessage,
        priority: str = "INTERACTIVE",
    ) -> int:
        """
        Enqueue a message at the given priority level.

        Args:
            message: The message to enqueue. Must be one of the
                MailboxMessage union types.
            priority: Priority class. One of ``"REALTIME"``,
                ``"INTERACTIVE"``, ``"BACKGROUND"``. Defaults to
                ``"INTERACTIVE"``.

        Returns:
            Queue position (0 = front of its priority queue).

        Raises:
            MailboxFullError: If current depth >= max_depth (100).
            ValueError: If priority is not a valid priority class.
        """
        ...  # pragma: no cover

    def dequeue(self) -> Optional[MailboxMessage]:
        """
        Dequeue the highest-priority message.

        Uses Weighted Fair Queuing: REALTIME gets 60% of dequeue
        slots, INTERACTIVE 30%, BACKGROUND 10%. Within a priority
        class, messages are FIFO.

        Returns:
            The next message, or ``None`` if the mailbox is empty.
        """
        ...  # pragma: no cover

    def depth(self) -> int:
        """
        Return the current total queue size across all priority classes.

        Returns:
            Number of messages currently enqueued.
        """
        ...  # pragma: no cover

    def peek_priority(self) -> Optional[str]:
        """
        Return the priority class of the next message without removing it.

        Returns:
            Priority class string (``"REALTIME"``, ``"INTERACTIVE"``,
            or ``"BACKGROUND"``), or ``None`` if the mailbox is empty.
        """
        ...  # pragma: no cover
