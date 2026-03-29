"""
poc.k1_poc.events.hitl -- V3 canonical HITL (human-in-the-loop) events.

M1 E1.1.4: Four HITL event schemas.

Events:
    HILRequested   -- Back requests human input.
    HILResolved    -- User provided response.
    TaskSuspended  -- Task suspended pending HITL.
    TaskResumed    -- Task resumed after HITL resolution.

Causation chain:
    Back needs HITL -> hil.requested (causation) -> task.suspended
    User answers    -> hil.resolved  (causation) -> task.resumed

Topic mapping (V3 reuses existing topic strings):
    HILRequested  -> k1.hil.request.v1
    HILResolved   -> k1.hil.response.v1
    TaskSuspended -> k1.orchestration.task.suspended.v1
    TaskResumed   -> k1.orchestration.task.resume.v1

Deprecates:
    poc/k1_poc/protocols/suspension_events.py (TaskSuspendedEvent, TaskResumeEvent)
    poc/k1_poc/protocols/hitl.py (HILRequest, HILResponse dataclasses -- not the SafetyBand)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from poc.k1_poc.events.base import CanonicalEventMeta


@dataclass
class HILRequested(CanonicalEventMeta):
    """Back requests human input.

    Carries the full HITL request payload. Maps fields from
    the existing HILRequest dataclass in protocols/hitl.py.

    Attributes:
        hil_type:     One of: clarification, approval, selection.
        question:     The question for the user.
        options:      Structured options (approval/selection).
        context:      Additional context (capability, params_so_far).
        side_effects: Explicit side effects for approval type.
        safety_band:  Effective safety band after escalation (GREEN/AMBER/RED).
        timeout_s:    Timeout for user response in seconds.
        max_rounds:   Max HITL rounds allowed per task.
    """

    event_type: str = field(default="hil.requested", init=False)
    hil_type: str = ""
    question: str = ""
    options: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)
    safety_band: str = "GREEN"
    timeout_s: float = 60.0
    max_rounds: int = 2

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["hil_type"] = self.hil_type
        d["question"] = self.question
        d["options"] = self.options
        d["context"] = self.context
        d["side_effects"] = self.side_effects
        d["safety_band"] = self.safety_band
        d["timeout_s"] = self.timeout_s
        d["max_rounds"] = self.max_rounds
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> HILRequested:
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
            hil_type=data.get("hil_type", ""),
            question=data.get("question", ""),
            options=data.get("options", []),
            context=data.get("context", {}),
            side_effects=data.get("side_effects", []),
            safety_band=data.get("safety_band", "GREEN"),
            timeout_s=data.get("timeout_s", 60.0),
            max_rounds=data.get("max_rounds", 2),
        )


@dataclass
class HILResolved(CanonicalEventMeta):
    """User provided HITL response.

    Maps fields from the existing HILResponse dataclass in protocols/hitl.py.

    Attributes:
        resolution:      Structured resolution payload (type-specific).
        resolution_type: What type of answer (selection, approval, text, timeout).
        elapsed_s:       Time from request to resolution in seconds.
        raw_user_text:   Original user text for audit trail.
    """

    event_type: str = field(default="hil.resolved", init=False)
    resolution: dict[str, Any] = field(default_factory=dict)
    resolution_type: str = "selection"
    elapsed_s: float = 0.0
    raw_user_text: str = ""

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["resolution"] = self.resolution
        d["resolution_type"] = self.resolution_type
        d["elapsed_s"] = self.elapsed_s
        d["raw_user_text"] = self.raw_user_text
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> HILResolved:
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
            resolution=data.get("resolution", {}),
            resolution_type=data.get("resolution_type", "selection"),
            elapsed_s=data.get("elapsed_s", 0.0),
            raw_user_text=data.get("raw_user_text", ""),
        )


@dataclass
class TaskSuspended(CanonicalEventMeta):
    """Task suspended pending HITL.

    This is the FSM lifecycle event. The causation link to the HITL
    request is via hil_request_event_id.

    Attributes:
        suspension_type:       Why the task is suspended (clarification, approval, selection).
        hil_request_event_id:  event_id of the HILRequested event that caused this suspension.
        suspension_count:      How many times this task has been suspended.
        has_react_history:     Whether react history was available at suspension.
        react_history_len:     Number of react history entries at suspension.
    """

    event_type: str = field(default="task.suspended", init=False)
    suspension_type: str = ""
    hil_request_event_id: str = ""
    suspension_count: int = 1
    has_react_history: bool = False
    react_history_len: int = 0

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["suspension_type"] = self.suspension_type
        d["hil_request_event_id"] = self.hil_request_event_id
        d["suspension_count"] = self.suspension_count
        d["has_react_history"] = self.has_react_history
        d["react_history_len"] = self.react_history_len
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskSuspended:
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
            suspension_type=data.get("suspension_type", ""),
            hil_request_event_id=data.get("hil_request_event_id", ""),
            suspension_count=data.get("suspension_count", 1),
            has_react_history=data.get("has_react_history", False),
            react_history_len=data.get("react_history_len", 0),
        )


@dataclass
class TaskResumed(CanonicalEventMeta):
    """Task resumed after HITL resolution.

    This is the FSM lifecycle event. The causation link to the HITL
    resolution is via hil_resolved_event_id.

    Attributes:
        hil_resolved_event_id: event_id of the HILResolved event that caused this resumption.
        resume_instruction:    Instruction for Back on how to resume (parsed from user answer).
    """

    event_type: str = field(default="task.resumed", init=False)
    hil_resolved_event_id: str = ""
    resume_instruction: str = ""
    has_resume_context: bool = False

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["hil_resolved_event_id"] = self.hil_resolved_event_id
        d["resume_instruction"] = self.resume_instruction
        d["has_resume_context"] = self.has_resume_context
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskResumed:
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
            hil_resolved_event_id=data.get("hil_resolved_event_id", ""),
            resume_instruction=data.get("resume_instruction", ""),
            has_resume_context=data.get("has_resume_context", False),
        )


__all__ = [
    "HILRequested",
    "HILResolved",
    "TaskSuspended",
    "TaskResumed",
    # M6 E6.3 lifecycle events
    "HITLRequestedEvent",
    "HITLResolvedEvent",
    "HITLTimedOutEvent",
    "HITLBlockedRedEvent",
]


# =========================================================================
# M6 E6.3 -- HITL Lifecycle Events (distinct from M1 HIL request/response)
#
# These are observability/audit events emitted at lifecycle boundaries.
# They use the new k1.hitl.* topics (note the T in HITL).
# The M1 events (HILRequested/HILResolved) map to the old k1.hil.* topics
# which are Back<->Front relay topics. These M6 events are for downstream
# consumers: ledger, audit, metrics.
# =========================================================================


@dataclass
class HITLRequestedEvent(CanonicalEventMeta):
    """M6 E6.3.1: HITL sub-task created (observability).

    Emitted when HILSubTask is created in _on_task_suspended, after
    persistence but before Front HITL_RELAY invocation.

    Attributes:
        pending_hil_id: UUID of the HILSubTask.
        hil_type:       clarification / approval / selection.
        parent_task_id: The task that is being suspended.
        safety_band:    Effective safety band after escalation.
        hil_deadline_ms: Deadline in ms from epoch.
        resume_token:   UUID4 token for resume validation.
        device_id:      M5 device context (if available).
    """

    event_type: str = field(default="hitl.lifecycle.requested", init=False)
    pending_hil_id: str = ""
    hil_type: str = ""
    parent_task_id: str = ""
    safety_band: str = "GREEN"
    hil_deadline_ms: int = 0
    resume_token: str = ""
    device_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["pending_hil_id"] = self.pending_hil_id
        d["hil_type"] = self.hil_type
        d["parent_task_id"] = self.parent_task_id
        d["safety_band"] = self.safety_band
        d["hil_deadline_ms"] = self.hil_deadline_ms
        d["resume_token"] = self.resume_token
        d["device_id"] = self.device_id
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> HITLRequestedEvent:
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
            pending_hil_id=data.get("pending_hil_id", ""),
            hil_type=data.get("hil_type", ""),
            parent_task_id=data.get("parent_task_id", ""),
            safety_band=data.get("safety_band", "GREEN"),
            hil_deadline_ms=data.get("hil_deadline_ms", 0),
            resume_token=data.get("resume_token", ""),
            device_id=data.get("device_id", ""),
        )


@dataclass
class HITLResolvedEvent(CanonicalEventMeta):
    """M6 E6.3.2: HITL sub-task resolved (observability).

    Emitted when HILSubTask.status is set to RESOLVED, after the
    user's answer is processed but before Back resume dispatch.

    Attributes:
        pending_hil_id:   UUID of the HILSubTask.
        hil_type:         clarification / approval / selection.
        parent_task_id:   The task being resumed.
        decision_branch:  clarified / approved / approved_with_mods / cancelled / selected.
        has_merged_params: True for approved_with_mods flows.
        device_id:        M5 device context.
    """

    event_type: str = field(default="hitl.lifecycle.resolved", init=False)
    pending_hil_id: str = ""
    hil_type: str = ""
    parent_task_id: str = ""
    decision_branch: str = "clarified"
    has_merged_params: bool = False
    device_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["pending_hil_id"] = self.pending_hil_id
        d["hil_type"] = self.hil_type
        d["parent_task_id"] = self.parent_task_id
        d["decision_branch"] = self.decision_branch
        d["has_merged_params"] = self.has_merged_params
        d["device_id"] = self.device_id
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> HITLResolvedEvent:
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
            pending_hil_id=data.get("pending_hil_id", ""),
            hil_type=data.get("hil_type", ""),
            parent_task_id=data.get("parent_task_id", ""),
            decision_branch=data.get("decision_branch", "clarified"),
            has_merged_params=data.get("has_merged_params", False),
            device_id=data.get("device_id", ""),
        )


@dataclass
class HITLTimedOutEvent(CanonicalEventMeta):
    """M6 E6.3.3: HITL sub-task timed out (observability).

    Emitted when the suspension timeout fires and HILSubTask is still
    PENDING. Triggers auto-cancel of the parent task.

    Attributes:
        pending_hil_id: UUID of the timed-out HILSubTask.
        hil_type:       clarification / approval / selection.
        parent_task_id: The task that was waiting for a response.
        timeout_ms:     Configured timeout in ms.
        elapsed_ms:     Actual elapsed time before timeout fired.
    """

    event_type: str = field(default="hitl.lifecycle.timed_out", init=False)
    pending_hil_id: str = ""
    hil_type: str = ""
    parent_task_id: str = ""
    timeout_ms: int = 0
    elapsed_ms: int = 0

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["pending_hil_id"] = self.pending_hil_id
        d["hil_type"] = self.hil_type
        d["parent_task_id"] = self.parent_task_id
        d["timeout_ms"] = self.timeout_ms
        d["elapsed_ms"] = self.elapsed_ms
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> HITLTimedOutEvent:
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
            pending_hil_id=data.get("pending_hil_id", ""),
            hil_type=data.get("hil_type", ""),
            parent_task_id=data.get("parent_task_id", ""),
            timeout_ms=data.get("timeout_ms", 0),
            elapsed_ms=data.get("elapsed_ms", 0),
        )


@dataclass
class HITLBlockedRedEvent(CanonicalEventMeta):
    """M6 E6.3.4: RED-band capability blocked (audit event).

    Emitted when HILCoordinator.handle_needs_human() encounters
    safety_band=RED. The system refuses to execute the capability
    entirely; no HILSubTask is created.

    Attributes:
        capability_name: The capability that was blocked.
        safety_band:     Always RED.
        reason:          Why the capability was blocked.
    """

    event_type: str = field(default="hitl.lifecycle.blocked_red", init=False)
    capability_name: str = ""
    safety_band: str = "RED"
    reason: str = "red_band_blocked"

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["capability_name"] = self.capability_name
        d["safety_band"] = self.safety_band
        d["reason"] = self.reason
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> HITLBlockedRedEvent:
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
            capability_name=data.get("capability_name", ""),
            safety_band=data.get("safety_band", "RED"),
            reason=data.get("reason", "red_band_blocked"),
        )
