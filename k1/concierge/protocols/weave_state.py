"""
k1.concierge.protocols.weave_state -- FSM weave decision table and pending
results queue.

V2 Design Ref: Section 4 (WEAVING state -- pending_results lifecycle)
V2 Design Ref: Section 4 (FSMTurnState: pending_results deque)
V2 Design Ref: Section 4 (State Diagram: pending_results empty? -> WEAVING)

The FSM decides how to handle a task.complete event based on its current
state.  The decision table maps ConciergeState -> WeaveAction:

    | FSM State          | Action on task.complete           |
    |--------------------|-----------------------------------|
    | LISTENING          | IMMEDIATE -- Front idle, invoke   |
    | COMPANIONING       | QUEUE_WEAVE -- queue then weave   |
    | DISPATCHING        | QUEUE -- Front busy dispatching   |
    | DELIVERING         | CHAIN -- append to current        |
    | WEAVING            | QUEUE -- already weaving          |
    | CANCELLING         | QUEUE -- cancel in progress       |
    | CLARIFYING_USER    | QUEUE -- awaiting user answer     |
    | CLARIFYING_WORKER  | QUEUE -- HITL in progress         |
    | INTERRUPT_HANDLING | QUEUE -- processing interrupt     |
    | PROGRESSING        | QUEUE -- Back still working       |
    | PROACTIVE_WAKE     | IMMEDIATE -- proactive delivery   |

pending_results lifecycle (V2 Section 4 FSMTurnState):
    1. task.complete arrives.
    2. FSM checks current state via get_weave_action().
    3. If not IMMEDIATE: push to PendingResultsQueue.
    4. When state transitions to LISTENING: drain queue.
    5. Invoke WeaveBatcher with all pending results.
    6. WeaveBatcher invokes Front LLM with [ASYNC RESULT ARRIVED] blocks.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from k1.concierge.fsm.states import ConciergeState

logger = logging.getLogger(__name__)


class WeaveAction(str, Enum):
    """What the FSM does when a task completes in a given state.

    V2 Design Ref: Section 4 (WEAVING state)

    IMMEDIATE:   Front is idle, invoke weave now.
    QUEUE_WEAVE: Queue the result, weave after current Front finishes.
    QUEUE:       Just queue, drain later when opportunity arises.
    CHAIN:       Append to current delivery (Front already presenting).
    DEAD_LETTER: Explicit rejection -- queue at capacity (M2 E2.2.5).
    """

    IMMEDIATE = "immediate"
    QUEUE_WEAVE = "queue_weave"
    QUEUE = "queue"
    CHAIN = "chain"
    DEAD_LETTER = "dead_letter"


# V2 Section 4: FSM state table for weave decisions
STATE_ACTION_TABLE: dict[ConciergeState, WeaveAction] = {
    ConciergeState.LISTENING: WeaveAction.IMMEDIATE,
    ConciergeState.COMPANIONING: WeaveAction.QUEUE_WEAVE,
    ConciergeState.DISPATCHING: WeaveAction.QUEUE,
    ConciergeState.DELIVERING: WeaveAction.CHAIN,
    ConciergeState.WEAVING: WeaveAction.QUEUE,
    ConciergeState.CANCELLING: WeaveAction.QUEUE,
    ConciergeState.CLARIFYING_USER: WeaveAction.QUEUE,
    ConciergeState.CLARIFYING_WORKER: WeaveAction.QUEUE,
    ConciergeState.INTERRUPT_HANDLING: WeaveAction.QUEUE,
    ConciergeState.PROGRESSING: WeaveAction.QUEUE,
    ConciergeState.PROACTIVE_WAKE: WeaveAction.IMMEDIATE,
}


def get_weave_action(fsm_state: ConciergeState) -> WeaveAction:
    """Determine the weave action for a given FSM state.

    V2 Design Ref: Section 4 (WEAVING state -- decision logic)

    Args:
        fsm_state: Current FSM state.

    Returns:
        The WeaveAction to take.  Defaults to QUEUE for unknown states.
    """
    action = STATE_ACTION_TABLE.get(fsm_state, WeaveAction.QUEUE)
    logger.debug(
        "get_weave_action  state=%s -> %s",
        fsm_state.name,
        action.value,
    )
    return action


@dataclass
class PendingResult:
    """A queued task result waiting for weave opportunity.

    V2 Design Ref: Section 4 (FSMTurnState: pending_results deque)

    Fields:
        task_id:          Unique task identifier.
        task_description: Human-readable task name.
        result_data:      Structured results from Back.
        queued_at_ns:     Monotonic timestamp when queued.
    """

    task_id: str
    task_description: str
    result_data: dict[str, Any]
    queued_at_ns: int = field(default_factory=time.monotonic_ns)

    def to_payload(self) -> dict[str, Any]:
        """Serialize for inspection/debug."""
        return {
            "task_id": self.task_id,
            "task_description": self.task_description,
            "result_data": self.result_data,
            "queued_at_ns": self.queued_at_ns,
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> PendingResult:
        """Deserialize from payload."""
        return cls(
            task_id=data["task_id"],
            task_description=data["task_description"],
            result_data=data.get("result_data", {}),
            queued_at_ns=data.get("queued_at_ns", 0),
        )


class PendingResultsQueue:
    """FIFO queue for pending results awaiting weave.

    V2 Design Ref: Section 4 (FSMTurnState -- pending_results lifecycle)
    M2 E2.2.5: Bounded depth with overflow eviction.

    Lifecycle:
        1. FSM pushes results via push().
        2. On transition to WEAVING, FSM calls drain().
        3. Drained results are handed to WeaveBatcher.
        4. After WEAVE response, cycle repeats if more results arrived.
    """

    __slots__ = ("_queue", "_max_depth")

    def __init__(self, max_depth: int = 16) -> None:
        self._queue: list[PendingResult] = []
        self._max_depth = max_depth

    def push(self, result: PendingResult) -> PendingResult | None:
        """Add a result to the queue.

        M2 E2.2.5: If the queue is at max_depth, the oldest result is
        evicted and returned so the caller can dead-letter it.

        Returns:
            The evicted PendingResult if overflow occurred, else None.
        """
        evicted: PendingResult | None = None
        if len(self._queue) >= self._max_depth:
            evicted = self._queue.pop(0)
            logger.warning(
                "PendingResultsQueue: overflow at max_depth=%d, " "evicting task=%s",
                self._max_depth,
                evicted.task_id,
            )
        self._queue.append(result)
        return evicted

    def drain(self) -> list[PendingResult]:
        """Drain all pending results.

        Returns:
            The list of results.  Queue is cleared.
        """
        results = list(self._queue)
        self._queue.clear()
        return results

    def peek(self) -> list[PendingResult]:
        """Peek at pending results without draining."""
        return list(self._queue)

    @property
    def count(self) -> int:
        """Number of pending results."""
        return len(self._queue)

    @property
    def is_empty(self) -> bool:
        """Whether the queue is empty."""
        return len(self._queue) == 0
