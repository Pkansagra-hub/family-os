"""
k1.orchestrator.adapters.mailbox_adapter -- MailboxAdapter (6.1.1).

Production adapter for IMailboxPort.

Design:
  - In-process priority mailbox with WFQ (Weighted Fair Queuing).
  - Three priority classes: REALTIME (60%), INTERACTIVE (30%), BACKGROUND (10%).
  - WFQ credits refill on each ``dequeue()`` call -- ensures fair scheduling.
  - ``deque`` for O(1) append/popleft.
  - Sync-only (no I/O per IMailboxPort contract).
  - Raises ``MailboxFullError`` when depth >= ``max_depth`` (default 100).

WFQ Algorithm:
  On each ``dequeue()``:
    1. Refill credits: add weight (0.6/0.3/0.1) per class.
    2. Select highest-credit class that has messages.
    3. Deduct 1.0 credit, popleft from that class's queue.
    4. Guarantees: REALTIME ~60% of slots, INTERACTIVE ~30%,
       BACKGROUND ~10%.

Thread Safety:
  Supports concurrent ``enqueue()`` from multiple threads/tasks via
  ``threading.Lock``. ``dequeue()`` is called from a single mailbox
  loop task.

References:
  - Issue 6.1.1 in orchestrator-implementation-plan.md
  - ORCH-001 (actor-based single-mailbox architecture)
  - docs/whiteboard/schema_whiteboard.md SS9 (mailbox durability)

Exports:
  MailboxAdapter
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Deque, Dict, List, Optional

from k1.orchestrator.ports.mailbox_port import MailboxFullError, MailboxMessage

# ---------------------------------------------------------------------------
# Valid priority classes
# ---------------------------------------------------------------------------

_VALID_PRIORITIES = frozenset({"REALTIME", "INTERACTIVE", "BACKGROUND"})

_DEFAULT_WEIGHTS: Dict[str, float] = {
    "REALTIME": 0.6,
    "INTERACTIVE": 0.3,
    "BACKGROUND": 0.1,
}


# ---------------------------------------------------------------------------
# 6.1.1 -- MailboxAdapter
# ---------------------------------------------------------------------------


class MailboxAdapter:
    """
    Production IMailboxPort adapter with WFQ scheduling.

    Three internal queues (one per priority class) with weighted
    fair queuing across ``dequeue()`` calls.  REALTIME gets ~60%
    of service, INTERACTIVE ~30%, BACKGROUND ~10%.

    Constructor Args:
        max_depth: Maximum total messages across all queues.
            When reached, ``enqueue()`` raises ``MailboxFullError``.
        wfq_weights: Per-class WFQ weights.  Keys must be
            ``"REALTIME"``, ``"INTERACTIVE"``, ``"BACKGROUND"``.
            Values are credit-refill amounts per ``dequeue()``.

    Thread Safety:
        All public methods are protected by a ``threading.Lock``.
        ``enqueue()`` is called from event handlers (possibly
        concurrent).  ``dequeue()`` is called from the single
        Orchestrator mailbox loop.
    """

    __slots__ = (
        "_max_depth",
        "_queues",
        "_total_depth",
        "_wfq_credits",
        "_weights",
        "_lock",
        "_priority_order",
    )

    def __init__(
        self,
        max_depth: int = 100,
        wfq_weights: Optional[Dict[str, float]] = None,
    ) -> None:
        self._max_depth = max_depth

        weights = wfq_weights if wfq_weights is not None else dict(_DEFAULT_WEIGHTS)
        self._weights: Dict[str, float] = weights

        self._queues: Dict[str, Deque[MailboxMessage]] = {
            "REALTIME": deque(),
            "INTERACTIVE": deque(),
            "BACKGROUND": deque(),
        }
        self._total_depth: int = 0

        # WFQ credits -- start at 0; first dequeue refills
        self._wfq_credits: Dict[str, float] = {p: 0.0 for p in _VALID_PRIORITIES}

        # Priority evaluation order (highest weight first)
        self._priority_order: List[str] = sorted(
            weights.keys(),
            key=lambda p: weights.get(p, 0.0),
            reverse=True,
        )

        self._lock = threading.Lock()

    # ==================================================================
    # IMailboxPort implementation
    # ==================================================================

    def enqueue(
        self,
        message: MailboxMessage,
        priority: str = "INTERACTIVE",
    ) -> int:
        """
        Enqueue a message at the given priority level.

        Args:
            message: One of the MailboxMessage union types.
            priority: ``"REALTIME"``, ``"INTERACTIVE"``, or ``"BACKGROUND"``.

        Returns:
            Queue position within the priority class (0 = front).

        Raises:
            MailboxFullError: If depth >= max_depth.
            ValueError: If priority is invalid.
        """
        if priority not in _VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{priority}'; " f"must be one of {sorted(_VALID_PRIORITIES)}"
            )

        with self._lock:
            if self._total_depth >= self._max_depth:
                raise MailboxFullError(f"Mailbox at capacity: {self._max_depth}")

            q = self._queues[priority]
            q.append(message)
            self._total_depth += 1
            return len(q) - 1

    def dequeue(self) -> Optional[MailboxMessage]:
        """
        Dequeue the highest-priority message using WFQ.

        WFQ algorithm:
          1. Refill credits: for each class, add its weight.
          2. Select the class with highest credits that has messages.
          3. Deduct 1.0 credit, popleft, return message.

        Returns:
            The next message, or ``None`` if all queues are empty.
        """
        with self._lock:
            if self._total_depth == 0:
                return None

            # Step 1: refill credits
            for p in _VALID_PRIORITIES:
                self._wfq_credits[p] += self._weights.get(p, 0.0)

            # Step 2: select highest-credit class with messages
            best_class: Optional[str] = None
            best_credit: float = float("-inf")

            for p in self._priority_order:
                if self._queues[p] and self._wfq_credits[p] > best_credit:
                    best_class = p
                    best_credit = self._wfq_credits[p]

            if best_class is None:
                return None

            # Step 3: deduct credit, popleft
            self._wfq_credits[best_class] -= 1.0
            message = self._queues[best_class].popleft()
            self._total_depth -= 1
            return message

    def depth(self) -> int:
        """Return current total queue size across all priority classes."""
        with self._lock:
            return self._total_depth

    def peek_priority(self) -> Optional[str]:
        """
        Return priority class of the next message (by WFQ logic)
        without removing it.

        Simulates a WFQ selection step without mutating state.

        Returns:
            Priority class string or ``None`` if mailbox is empty.
        """
        with self._lock:
            if self._total_depth == 0:
                return None

            # Simulate credit refill
            sim_credits = {
                p: self._wfq_credits[p] + self._weights.get(p, 0.0) for p in _VALID_PRIORITIES
            }

            best_class: Optional[str] = None
            best_credit: float = -1.0

            for p in self._priority_order:
                if self._queues[p] and sim_credits[p] > best_credit:
                    best_class = p
                    best_credit = sim_credits[p]

            return best_class

    # ==================================================================
    # Diagnostics
    # ==================================================================

    def queue_depths(self) -> Dict[str, int]:
        """Return per-priority queue depths."""
        with self._lock:
            return {p: len(q) for p, q in self._queues.items()}

    def credits_snapshot(self) -> Dict[str, float]:
        """Return current WFQ credit state (for diagnostics/testing)."""
        with self._lock:
            return dict(self._wfq_credits)
