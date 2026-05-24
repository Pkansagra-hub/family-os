"""
k1.concierge.fsm.front_lock -- FrontLock concurrency gate.

V2 Design Ref: Section 4 (FrontLock: Concurrency Control)

The Front LLM is a single actor. It cannot process two events simultaneously.
When multiple events target Front at the same time, the FSM serializes them
through this lock.

Rules (V2 Section 4):
  1. If busy=False: Set busy=True, deliver event, wait for response, busy=False.
  2. If busy=True: Append event to event_queue.
  3. After Front finishes: drain event_queue in priority order (URGENT first).
  4. If event_queue exceeds max_queue_depth: reject lowest-priority event + log.

Queue Priority (V2 Section 4):
  P1 (URGENT)      user.input         -- user is ALWAYS first
  P2 (INTERACTIVE)  task.suspended     -- worker blocked, needs answer
  P3 (RESULT)       task.complete      -- result ready, user not waiting
  P4 (ERROR)        task.failed        -- error, user may not know about task
  P5 (INFO)         findings.ready     -- partial results, informational
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from k1.bus.envelope import Envelope
from k1.concierge.bus.topics import (
    TOPIC_FINDINGS_READY,
    TOPIC_HIL_REQUEST,
    TOPIC_PROACTIVE_FILL,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_SUSPENDED,
    TOPIC_USER_INPUT,
    TOPIC_WEAVE_BATCH,
)
from k1.concierge.config import get_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Priority levels (lower number = higher priority)
# ---------------------------------------------------------------------------
PRIORITY_URGENT = 1
PRIORITY_INTERACTIVE = 2
PRIORITY_RESULT = 3
PRIORITY_ERROR = 4
PRIORITY_INFO = 5

# Topic-to-priority mapping
# M2 E2.1.6: Use topic constants instead of hardcoded strings.
TOPIC_PRIORITY: dict[str, int] = {
    TOPIC_USER_INPUT: PRIORITY_URGENT,
    TOPIC_HIL_REQUEST: PRIORITY_INTERACTIVE,
    TOPIC_TASK_SUSPENDED: PRIORITY_INTERACTIVE,
    TOPIC_TASK_COMPLETE: PRIORITY_RESULT,
    TOPIC_TASK_FAILED: PRIORITY_ERROR,
    TOPIC_FINDINGS_READY: PRIORITY_INFO,
    TOPIC_WEAVE_BATCH: PRIORITY_RESULT,
    TOPIC_PROACTIVE_FILL: PRIORITY_INFO,
}

# Kept as module constant for backward compatibility; runtime reads from config
DEFAULT_MAX_QUEUE_DEPTH = 8


@dataclass
class FrontLock:
    """Concurrency gate for the Front LLM actor.

    Serializes events targeting the Front LLM. Maintains a bounded priority
    queue. When Front is busy, incoming events are queued and drained in
    priority order after each response.

    Why this matters (V2 Section 4 example):
      Without lock: user.input and task.complete arrive simultaneously ->
      two parallel Front LLM calls -> both read same SS -> one overwrites.
      With lock: user.input (URGENT) first -> response -> task.complete
      queued -> Front re-invoked -> two sequential coherent messages.
    """

    busy: bool = False
    event_queue: deque[tuple[int, Envelope]] = field(default_factory=deque)
    max_queue_depth: int = field(
        default_factory=lambda: get_config().fsm.front_lock_max_queue_depth
    )

    def __post_init__(self) -> None:
        logger.info(
            "FrontLock initialized (max_queue_depth=%d)",
            self.max_queue_depth,
        )

    # ------------------------------------------------------------------
    # Core API (Epic 8.4.2)
    # ------------------------------------------------------------------

    def try_deliver(self, envelope: Envelope) -> bool:
        """Attempt to deliver event to Front LLM.

        Returns True if delivered (Front was free), False if queued (busy).

        If delivered: Sets busy=True. Caller must call release() after
        Front finishes.
        If queued: Inserts into event_queue at correct priority position.
        May reject lowest-priority event if queue is full.
        """
        if not self.busy:
            self.busy = True
            return True
        self._enqueue(envelope)
        return False

    def _enqueue(self, envelope: Envelope) -> Envelope | None:
        """Insert event into priority queue.

        Returns the rejected envelope if backpressure triggered, else None.
        """
        priority = TOPIC_PRIORITY.get(envelope.topic, PRIORITY_INFO)
        # Insert maintaining priority order (lower number = earlier)
        inserted = False
        for i in range(len(self.event_queue)):
            if priority < self.event_queue[i][0]:
                self.event_queue.insert(i, (priority, envelope))
                inserted = True
                break
        if not inserted:
            self.event_queue.append((priority, envelope))

        # Backpressure: reject lowest-priority if over limit
        rejected: Envelope | None = None
        if len(self.event_queue) > self.max_queue_depth:
            _, rejected_env = self.event_queue.pop()
            rejected = rejected_env
            logger.warning(
                "FrontLock backpressure: rejected '%s' (envelope_id=%d, " "queue_depth=%d)",
                rejected_env.topic,
                rejected_env.envelope_id,
                len(self.event_queue),
            )
        return rejected

    # ------------------------------------------------------------------
    # Release and drain (Epic 8.4.3)
    # ------------------------------------------------------------------

    def release(self) -> Envelope | None:
        """Release the lock and return the next queued event (if any).

        Called by FSM after Front LLM finishes processing an event.

        Returns:
          - Next highest-priority envelope, or None if queue empty.
          - If returned, busy remains True (caller will deliver next).
          - If None, sets busy=False (Front is truly idle).
        """
        if self.event_queue:
            _, next_envelope = self.event_queue.popleft()
            return next_envelope
        self.busy = False
        return None

    async def drain_loop(
        self,
        deliver_fn: Callable[[Envelope], Awaitable[None]],
    ) -> None:
        """Drain the entire event queue in priority order.

        Args:
            deliver_fn: Async callable that processes each event.
                        This is the FSM's handler dispatch.

        After Front finishes one event:
          1. Call release() to get next queued event.
          2. If non-None: deliver it (Front processes).
          3. After processing: call release() again.
          4. Repeat until release() returns None.
        """
        while True:
            next_env = self.release()
            if next_env is None:
                break
            await deliver_fn(next_env)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def queue_depth(self) -> int:
        """Current number of events waiting in the queue."""
        return len(self.event_queue)

    @property
    def is_idle(self) -> bool:
        """True if Front is not busy and queue is empty."""
        return not self.busy and len(self.event_queue) == 0

    def is_accepting_context(self) -> bool:
        """Whether Front can accept mid-generation context injection.

        Current Front delivery is envelope-based, so live context chaining is
        not supported yet. The explicit capability check keeps same-turn
        result handling honest and lets future implementations opt in here.
        """
        return False

    def peek_priorities(self) -> list[int]:
        """Return the priority values of all queued events (for testing)."""
        return [p for p, _ in self.event_queue]

    def clear(self) -> None:
        """Clear the queue and reset busy flag. For testing/teardown."""
        self.event_queue.clear()
        self.busy = False
