"""
k1.concierge.protocols.suspension_events -- Suspension bus event dataclasses.

V2 Design Ref: Section 3 (Event Taxonomy: task.suspended.v1, task.resume.v1)
V2 Design Ref: Section 4 (CLARIFYING_WORKER state transitions)

Bus events for the suspension protocol:
    TaskSuspendedEvent: Back -> FSM -> Front (task needs human input)
    TaskResumeEvent:    Front -> FSM -> Back (user answered)

Topic constants are imported from task.topics (defined in M10).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Reuse existing topic constants (defined in M10 task/topics.py)


@dataclass
class TaskSuspendedEvent:
    """Emitted by Back when it suspends for user input.

    V2 Design Ref: Section 4, CLARIFYING_WORKER entry.
    V2 Design Ref: Section 5, TaskStateEntry.pending_hil.

    The FSM uses this event to:
        1. Update task_state to SUSPENDED.
        2. Store pending_hil in TaskStateEntry.
        3. Transition to CLARIFYING_WORKER.
        4. Invoke Front in HITL_RELAY mode.

    Attributes:
        task_id:           The suspended task.
        suspension_type:   Why it is suspended.
        question:          The question for the user.
        options:           Structured options for selection.
        suspension_count:  How many times this task has been suspended.
    """

    task_id: str
    suspension_type: str
    question: str
    options: list[dict[str, Any]]
    suspension_count: int = 1

    def to_payload(self) -> dict[str, Any]:
        """Serialize to bus envelope payload."""
        return {
            "task_id": self.task_id,
            "suspension_type": self.suspension_type,
            "question": self.question,
            "options": self.options,
            "suspension_count": self.suspension_count,
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskSuspendedEvent:
        """Deserialize from bus envelope payload."""
        return cls(
            task_id=data["task_id"],
            suspension_type=data["suspension_type"],
            question=data["question"],
            options=data.get("options", []),
            suspension_count=data.get("suspension_count", 1),
        )


@dataclass
class TaskResumeEvent:
    """Emitted by Front after user answers suspension question.

    V2 Design Ref: Section 4, CLARIFYING_WORKER exit -> Back resumes.
    V2 Design Ref: Section 5, Resume Context.

    The FSM uses this event to:
        1. Retrieve the stored SuspensionRequest (with ReAct history).
        2. Build the resume context payload.
        3. Re-dispatch to Back with resume_instruction.

    Attributes:
        task_id:         The suspended task to resume.
        resolution:      User's answer.
        resolution_type: What type of answer (selection/approval/text).
    """

    task_id: str
    resolution: Any = None
    resolution_type: str = "selection"

    def to_payload(self) -> dict[str, Any]:
        """Serialize to bus envelope payload."""
        return {
            "task_id": self.task_id,
            "resolution": self.resolution,
            "resolution_type": self.resolution_type,
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskResumeEvent:
        """Deserialize from bus envelope payload."""
        return cls(
            task_id=data["task_id"],
            resolution=data.get("resolution"),
            resolution_type=data.get("resolution_type", "selection"),
        )
