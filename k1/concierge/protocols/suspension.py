"""
k1.concierge.protocols.suspension -- Suspension protocol for Back HITL flow.

V2 Design Ref: Section 4 (FSM state: CLARIFYING_WORKER, HITL_RELAY, HITL_RESOLVE)
V2 Design Ref: Section 5 (TaskStateEntry: status SUSPENDED, pending_hil,
                           hil_suspensions_count)
V2 Design Ref: Section 5 (Resume Context: findings_so_far, tool_history,
                           last_iteration, resolution)

When Back needs human input (approval, selection, clarification), it
suspends the task and emits k1.orchestration.task.suspended.v1.  The
FSM transitions to CLARIFYING_WORKER.  Front translates the structured
HITL request into natural conversation (HITL_RELAY mode, 0 tools).
On user response, Front emits task.resume.v1 (HITL_RESOLVE mode).
Back resumes from saved ReAct history.

Suspension types (V2 Section 4):
    CLARIFICATION: "Which Vineyard Inn did you mean?" (60s timeout)
    APPROVAL:      "This will charge $450, proceed?" (120s timeout)
    SELECTION:     "Pick from these 3 options" (90s timeout)

Limits (V2 Section 5, TaskStateEntry.hil_suspensions_count):
    Max suspensions per task: 2
    Concurrent suspensions: 1 per task
    FSM auto-cancels on timeout
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from k1.concierge.config import get_config


class SuspensionType(str, Enum):
    """Why the task is suspended.

    V2 Design Ref: Section 4, CLARIFYING_WORKER entry conditions.
    """

    CLARIFICATION = "clarification"
    APPROVAL = "approval"
    SELECTION = "selection"


# Timeout per suspension type: authoritative values live in
# config/defaults.yaml (protocols.suspension_timeouts).  Use
# _get_suspension_timeouts() to access them.  No module-level
# fallback dict -- the config is the single source of truth.
# (V3 E0.2.1: removed SUSPENSION_TIMEOUTS constant)

# Hard limits (V2 Section 5, TaskStateEntry.hil_suspensions_count)
# Authoritative value lives in config/defaults.yaml
# (protocols.max_suspensions_per_task).  Use _get_max_suspensions_per_task().
# (V3 E0.2.2: constant kept only for backward-compat re-export;
# production code must use the config accessor.)
MAX_SUSPENSIONS_PER_TASK: int = 2
MAX_CONCURRENT_SUSPENSIONS: int = 1  # Per task


def _get_suspension_timeouts() -> dict[SuspensionType, float]:
    """Return suspension timeouts from central config."""
    raw = get_config().protocols.suspension_timeouts
    return {SuspensionType(k): v for k, v in raw.items()}


def _get_max_suspensions_per_task() -> int:
    """Return max suspensions per task from central config."""
    return get_config().protocols.max_suspensions_per_task


def _get_max_concurrent_suspensions() -> int:
    """Return max concurrent suspensions from central config."""
    return get_config().protocols.max_concurrent_suspensions


@dataclass
class SuspensionRequest:
    """Emitted by Back when it needs human input to proceed.

    V2 Design Ref: Section 5, TaskStateEntry.pending_hil.
    V2 Design Ref: Section 5, Resume Context.

    The request carries the full ReAct history and tool state so
    Back can resume from exactly where it left off.  The FSM stores
    this in TaskStateEntry.pending_hil for crash recovery.

    Attributes:
        task_id:           The task being suspended.
        suspension_type:   Why the task is suspended.
        question:          The question for the user.
        options:           Structured options (selection/approval).
        react_history:     Serialized ReAct message history for resume.
        tool_state:        Serialized tool state for resume.
        suspension_count:  How many times this task has been suspended.
        created_at_ns:     When the suspension was created (monotonic).
    """

    task_id: str
    suspension_type: SuspensionType
    question: str
    options: list[dict[str, Any]] = field(default_factory=list)
    react_history: list[dict[str, Any]] = field(default_factory=list)
    tool_state: dict[str, Any] = field(default_factory=dict)
    suspension_count: int = 1
    created_at_ns: int = field(default_factory=time.monotonic_ns)

    @property
    def timeout_seconds(self) -> float:
        """Timeout for this suspension type."""
        timeouts = _get_suspension_timeouts()
        return timeouts.get(self.suspension_type, 60.0)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to bus envelope payload."""
        return {
            "task_id": self.task_id,
            "suspension_type": self.suspension_type.value,
            "question": self.question,
            "options": self.options,
            "react_history": self.react_history,
            "tool_state": self.tool_state,
            "suspension_count": self.suspension_count,
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> SuspensionRequest:
        """Deserialize from bus envelope payload."""
        return cls(
            task_id=data["task_id"],
            suspension_type=SuspensionType(data["suspension_type"]),
            question=data["question"],
            options=data.get("options", []),
            react_history=data.get("react_history", []),
            tool_state=data.get("tool_state", {}),
            suspension_count=data.get("suspension_count", 1),
        )


@dataclass
class SuspensionResolution:
    """Emitted by Front when user answers a suspension question.

    V2 Design Ref: Section 5, Resume Context.resolution.

    Attributes:
        task_id:         The suspended task.
        resolution:      User's answer (selected option, approval, text).
        resolution_type: What type of answer this is.
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
    def from_payload(cls, data: dict[str, Any]) -> SuspensionResolution:
        """Deserialize from bus envelope payload."""
        return cls(
            task_id=data["task_id"],
            resolution=data.get("resolution"),
            resolution_type=data.get("resolution_type", "selection"),
        )


class SuspensionLimitExceeded(Exception):
    """Raised when a task exceeds max suspension count.

    V2 Design Ref: Section 5, TaskStateEntry.hil_suspensions_count.
    """

    def __init__(self, task_id: str, count: int) -> None:
        self.task_id = task_id
        self.count = count
        max_allowed = _get_max_suspensions_per_task()
        super().__init__(f"Task {task_id} exceeded max suspensions: " f"{count}/{max_allowed}")


class SuspensionTimeoutError(Exception):
    """Raised when a suspension times out without user response.

    V2 Design Ref: Section 4, CLARIFYING_WORKER timeout behavior.
    FSM auto-cancels the task on timeout.
    """

    def __init__(self, task_id: str, timeout: float) -> None:
        self.task_id = task_id
        self.timeout = timeout
        super().__init__(f"Task {task_id} suspension timed out after {timeout}s")
