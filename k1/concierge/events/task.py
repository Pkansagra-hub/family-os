"""
k1.concierge.events.task -- V3 canonical task lifecycle events.

M1 E1.1.3: Six task lifecycle event schemas.

Events:
    TaskCreated    -- Task created by arbiter/dispatcher.
    TaskLeased     -- Task claimed by a Back worker (schema only; M5 BackPool).
    TaskProgressed -- Incremental progress update from Back.
    TaskCompleted  -- Task finished successfully.
    TaskFailed     -- Task failed (error, timeout, cancel-reason).
    TaskCancelled  -- Task explicitly cancelled.

Topic mapping (V3 reuses existing topic strings):
    TaskCreated    -> k1.orchestration.task.dispatch.v1
    TaskLeased     -> (future: k1.orchestration.task.leased.v1, M7)
    TaskProgressed -> (future: k1.orchestration.task.progressed.v1)
    TaskCompleted  -> k1.orchestration.task.complete.v1
    TaskFailed     -> k1.orchestration.task.failed.v1
    TaskCancelled  -> k1.orchestration.task.cancel.v1

Deprecates: poc/k1_poc/protocols/cancel_events.py (TaskCancelEvent, TaskFailedCancelledEvent).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from k1.concierge.events.base import CanonicalEventMeta


@dataclass
class TaskCreated(CanonicalEventMeta):
    """Task dispatched from arbiter/FSM to Back.

    Attributes:
        action:           The action/capability to execute.
        depends_on:       Task IDs this task depends on (DAG ordering).
        dispatch_context: Additional context for the Back worker.
    """

    event_type: str = field(default="task.created", init=False)
    action: str = ""
    depends_on: list[str] = field(default_factory=list)
    dispatch_context: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["action"] = self.action
        d["depends_on"] = self.depends_on
        d["dispatch_context"] = self.dispatch_context
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskCreated:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            action=data.get("action", ""),
            depends_on=data.get("depends_on", []),
            dispatch_context=data.get("dispatch_context", {}),
        )


@dataclass
class TaskLeased(CanonicalEventMeta):
    """Task claimed by a Back worker (BackPool lease model).

    Schema defined in M1; implementation in M7 (BackPool).

    Attributes:
        worker_id:        ID of the Back worker that claimed the task.
        lease_expires_at: ISO 8601 UTC timestamp when the lease expires.
    """

    event_type: str = field(default="task.leased", init=False)
    worker_id: str = ""
    lease_expires_at: str = ""

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["worker_id"] = self.worker_id
        d["lease_expires_at"] = self.lease_expires_at
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskLeased:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            worker_id=data.get("worker_id", ""),
            lease_expires_at=data.get("lease_expires_at", ""),
        )


@dataclass
class TaskProgressed(CanonicalEventMeta):
    """Incremental progress update from Back.

    Attributes:
        progress_pct:    Completion percentage [0, 100].
        status_message:  Human-readable progress message.
        findings_so_far: Partial results discovered so far.
    """

    event_type: str = field(default="task.progressed", init=False)
    progress_pct: int = 0
    status_message: str = ""
    findings_so_far: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["progress_pct"] = self.progress_pct
        d["status_message"] = self.status_message
        d["findings_so_far"] = self.findings_so_far
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskProgressed:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            progress_pct=data.get("progress_pct", 0),
            status_message=data.get("status_message", ""),
            findings_so_far=data.get("findings_so_far", {}),
        )


@dataclass
class TaskCompleted(CanonicalEventMeta):
    """Task finished successfully.

    Attributes:
        result_data:       Structured results from Back.
        action:            The action/capability that was executed.
        tool_calls_count:  Number of tool calls made during execution.
        elapsed_ms:        Total execution time in milliseconds.
    """

    event_type: str = field(default="task.completed", init=False)
    result_data: dict[str, Any] = field(default_factory=dict)
    action: str = ""
    tool_calls_count: int = 0
    elapsed_ms: int = 0

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["result_data"] = self.result_data
        d["action"] = self.action
        d["tool_calls_count"] = self.tool_calls_count
        d["elapsed_ms"] = self.elapsed_ms
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskCompleted:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            result_data=data.get("result_data", {}),
            action=data.get("action", ""),
            tool_calls_count=data.get("tool_calls_count", 0),
            elapsed_ms=data.get("elapsed_ms", 0),
        )


@dataclass
class TaskFailed(CanonicalEventMeta):
    """Task failed (error, timeout, or cancel-reason).

    Replaces TaskFailedCancelledEvent from cancel_events.py.

    Attributes:
        reason:                 Failure reason description.
        error_code:             Machine-readable error code.
        completed_before_cancel: True if task finished before cancel was processed.
        tool_calls_completed:   How many tool calls finished before failure.
    """

    event_type: str = field(default="task.failed", init=False)
    reason: str = ""
    error_code: str = ""
    completed_before_cancel: bool = False
    tool_calls_completed: int = 0

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["reason"] = self.reason
        d["error_code"] = self.error_code
        d["completed_before_cancel"] = self.completed_before_cancel
        d["tool_calls_completed"] = self.tool_calls_completed
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskFailed:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            reason=data.get("reason", ""),
            error_code=data.get("error_code", ""),
            completed_before_cancel=data.get("completed_before_cancel", False),
            tool_calls_completed=data.get("tool_calls_completed", 0),
        )


@dataclass
class TaskCancelled(CanonicalEventMeta):
    """Task explicitly cancelled by user or system.

    Replaces TaskCancelEvent from cancel_events.py.

    Attributes:
        reason:                 Why the task was cancelled.
        new_task_id:            Replacement task ID if user requested a substitute.
        cancel_reason:          Structured cancel reason (user_requested, timeout, superseded).
        had_token:              Whether a CancellationToken existed for this task.
        completed_before_cancel: True if task completed before cancel was processed.
    """

    event_type: str = field(default="task.cancelled", init=False)
    reason: str = "user_requested"
    new_task_id: str = ""
    cancel_reason: str = ""
    had_token: bool = False
    completed_before_cancel: bool = False

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["reason"] = self.reason
        d["new_task_id"] = self.new_task_id
        d["cancel_reason"] = self.cancel_reason
        d["had_token"] = self.had_token
        d["completed_before_cancel"] = self.completed_before_cancel
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskCancelled:
        return cls(
            event_id=data.get("event_id", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", ""),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
            reason=data.get("reason", "user_requested"),
            new_task_id=data.get("new_task_id", ""),
            cancel_reason=data.get("cancel_reason", ""),
            had_token=data.get("had_token", False),
            completed_before_cancel=data.get("completed_before_cancel", False),
        )


__all__ = [
    "TaskCreated",
    "TaskLeased",
    "TaskProgressed",
    "TaskCompleted",
    "TaskFailed",
    "TaskCancelled",
]
