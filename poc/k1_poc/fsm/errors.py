"""
poc.k1_poc.fsm.errors -- FSM-specific exceptions.

V2 Design Ref: Section 4 (FSM error handling, illegal transitions)
"""

from __future__ import annotations


class IllegalTransitionError(Exception):
    """Raised when the FSM attempts a state transition not in TRANSITION_TABLE.

    The FSM logs the illegal transition for debugging but does NOT crash.
    The event is either discarded with a warning or queued for retry
    depending on the handler context.
    """

    def __init__(self, from_state: str, trigger: str) -> None:
        self.from_state = from_state
        self.trigger = trigger
        super().__init__(f"Illegal FSM transition: {from_state} on trigger '{trigger}'")


class FrontLockOverflowError(Exception):
    """Raised when FrontLock event_queue exceeds max_queue_depth.

    This is a backpressure signal. The lowest-priority event is ejected
    and this error is logged as a warning. It does NOT propagate to callers.
    """

    def __init__(self, rejected_topic: str, queue_depth: int) -> None:
        self.rejected_topic = rejected_topic
        self.queue_depth = queue_depth
        super().__init__(
            f"FrontLock backpressure: rejected '{rejected_topic}' " f"(queue depth: {queue_depth})"
        )
