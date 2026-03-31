"""
k1.concierge.protocols.cancel_events -- Cancellation event dataclasses.

V2 Design Ref: Section 3 (Event Taxonomy: task.cancel.v1, task.failed.v1)
V2 Design Ref: Section 4 (CANCELLING state timeline)

Cancellation timeline (V2 Section 4, CANCELLING):
    T=0ms    User: "book Vineyard Inn for June 15-17"
    T=300ms  User: "Wait, cancel that, do Marriott instead"
    T=302ms  Front emits task.cancel (URGENT) + ack + new dispatch
    T=305ms  Back checks cancellation_token at next tool boundary, aborts
    T=310ms  Back emits task.failed(cancelled=True)
    T=312ms  FSM updates task_state -> CANCELLED, transitions to DELIVERING

These events carry structured payloads for the bus envelope system.
The topic constants are imported from task.topics to avoid duplication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Reuse existing topic constants (defined in M10 task/topics.py)
from k1.concierge.task.topics import TASK_FAILED

# Additional topic for the specific "failed due to cancellation" case
TASK_FAILED_CANCELLED = TASK_FAILED  # Same topic, payload carries reason


@dataclass
class TaskCancelEvent:
    """Emitted by Front when user requests task cancellation.

    V2 Design Ref: Section 4, CANCELLING state entry event.

    This event uses URGENT priority on the bus to ensure it arrives
    at Back's next tool boundary check as fast as possible.

    Attributes:
        task_id:     The task to cancel.
        reason:      Why it is being cancelled.
        priority:    Bus priority (always URGENT for cancels).
        new_task_id: If user immediately requested a replacement task
                     ("cancel that, do Marriott instead"), the new
                     task ID is included for FSM coordination.
    """

    task_id: str
    reason: str = "user_requested"
    priority: str = "URGENT"
    new_task_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Serialize to bus envelope payload."""
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "reason": self.reason,
            "priority": self.priority,
        }
        if self.new_task_id is not None:
            d["new_task_id"] = self.new_task_id
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskCancelEvent:
        """Deserialize from bus envelope payload."""
        return cls(
            task_id=data["task_id"],
            reason=data.get("reason", "user_requested"),
            priority=data.get("priority", "URGENT"),
            new_task_id=data.get("new_task_id"),
        )


@dataclass
class TaskFailedCancelledEvent:
    """Emitted by Back when it aborts due to cancellation.

    V2 Design Ref: Section 4, CANCELLING state exit event.
    V2 Design Ref: Section 5, FSMTurnState.cancelled_tasks dedup.

    If completed_before_cancel is True, the task actually finished
    before Back checked the token.  FSM presents "it actually went
    through" message instead of "cancelled".

    Attributes:
        task_id:                 The cancelled task.
        completed_before_cancel: True if task completed before cancel check.
        tool_calls_completed:    How many tool calls finished before abort.
        error_message:           Human-readable cancellation message.
    """

    task_id: str
    completed_before_cancel: bool = False
    tool_calls_completed: int = 0
    error_message: str = "Task cancelled by user"

    def to_payload(self) -> dict[str, Any]:
        """Serialize to bus envelope payload."""
        return {
            "task_id": self.task_id,
            "completed_before_cancel": self.completed_before_cancel,
            "tool_calls_completed": self.tool_calls_completed,
            "error_message": self.error_message,
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskFailedCancelledEvent:
        """Deserialize from bus envelope payload."""
        return cls(
            task_id=data["task_id"],
            completed_before_cancel=data.get("completed_before_cancel", False),
            tool_calls_completed=data.get("tool_calls_completed", 0),
            error_message=data.get("error_message", "Task cancelled by user"),
        )
