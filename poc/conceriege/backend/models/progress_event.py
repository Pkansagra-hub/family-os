"""
Progress Event Model

Represents progress milestones from background specialist work.

Research basis:
- Progressive Disclosure (Norman 1988)
- SEDA - Staged Event-Driven Architecture (Welsh 2001)
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProgressEvent:
    """
    Progress event emitted by specialist agents during execution.

    NO LLM generation - agents define milestones in code for speed and cost.

    Fields:
        task_id: Unique task identifier
        milestone: Milestone number (1-5 typically)
        percent: Progress percentage (0-100)
        message: Human-readable progress message
        timestamp: When this event was emitted

    Examples:
        >>> event = ProgressEvent(
        ...     task_id="task_nut_123",
        ...     milestone=2,
        ...     percent=40,
        ...     message="🧠 Analyzing patterns..."
        ... )
        >>> event.is_complete()
        False
    """

    task_id: str
    milestone: int
    percent: int  # 0-100
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of ProgressEvent
        """
        return {
            "task_id": self.task_id,
            "milestone": self.milestone,
            "percent": self.percent,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }

    def is_complete(self) -> bool:
        """
        Check if this event represents completion.

        Returns:
            True if percent is 100
        """
        return self.percent >= 100
