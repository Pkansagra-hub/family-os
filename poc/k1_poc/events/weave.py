"""
poc.k1_poc.events.weave -- V3 canonical weave events.

M1 E1.1.5: Three weave event schemas.

Events:
    WeaveCandidateArrived -- A task result is available for weaving.
    WeaveDecisionMade     -- Weave policy made a decision (immediate/batch/defer).
    WeaveEmitted          -- Weave content was delivered to user.

Topic mapping (V3 reuses existing topic strings):
    WeaveCandidateArrived -> k1.orchestration.task.complete.v1 (same topic as TaskCompleted)
    WeaveDecisionMade     -> k1.internal.weave.batch.v1
    WeaveEmitted          -> k1.response.final.v1

Note: WeaveResult and PendingResult in protocols/ continue to exist as
internal runtime structs populated FROM these canonical events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from poc.k1_poc.events.base import CanonicalEventMeta


@dataclass
class WeaveCandidateArrived(CanonicalEventMeta):
    """A task result is available for weaving into conversation.

    Maps fields from WeaveResult in protocols/weave_batcher.py.

    Attributes:
        task_description: Human-readable task name.
        result_data:      Structured results from Back.
        completed_at_ns:  Monotonic timestamp of task completion.
    """

    event_type: str = field(default="conversation.weave.candidate", init=False)
    task_description: str = ""
    result_data: dict[str, Any] = field(default_factory=dict)
    completed_at_ns: int = 0

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["task_description"] = self.task_description
        d["result_data"] = self.result_data
        d["completed_at_ns"] = self.completed_at_ns
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> WeaveCandidateArrived:
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
            task_description=data.get("task_description", ""),
            result_data=data.get("result_data", {}),
            completed_at_ns=data.get("completed_at_ns", 0),
        )


@dataclass
class WeaveDecisionMade(CanonicalEventMeta):
    """Weave policy made a decision on how to handle a candidate.

    Attributes:
        candidate_event_id: event_id of the WeaveCandidateArrived that triggered this decision.
        decision:           WeaveAction value (immediate/batch/defer/digest/suppress).
        reason:             Human-readable reason for the decision.
        fsm_state:          FSM state when decision was made.
        batch_window_ms:    Batch window duration in milliseconds.
        signal_snapshot:    Serialized WeaveSignal for auditable decision replay (M8 E8.2.4).
        urgency_override:   True if critical urgency overrode normal policy (M8 E8.2.4).
        emotional_gate_applied: True if emotional gate changed the decision (M8 E8.2.4).
    """

    event_type: str = field(default="conversation.weave.decided", init=False)
    candidate_event_id: str = ""
    decision: str = ""
    reason: str = ""
    fsm_state: str = ""
    batch_window_ms: int = 0
    signal_snapshot: dict[str, Any] = field(default_factory=dict)
    urgency_override: bool = False
    emotional_gate_applied: bool = False
    fallback_used: bool = False

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["candidate_event_id"] = self.candidate_event_id
        d["decision"] = self.decision
        d["reason"] = self.reason
        d["fsm_state"] = self.fsm_state
        d["batch_window_ms"] = self.batch_window_ms
        d["signal_snapshot"] = self.signal_snapshot
        d["urgency_override"] = self.urgency_override
        d["emotional_gate_applied"] = self.emotional_gate_applied
        d["fallback_used"] = self.fallback_used
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> WeaveDecisionMade:
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
            candidate_event_id=data.get("candidate_event_id", ""),
            decision=data.get("decision", ""),
            reason=data.get("reason", ""),
            fsm_state=data.get("fsm_state", ""),
            batch_window_ms=data.get("batch_window_ms", 0),
            signal_snapshot=data.get("signal_snapshot", {}),
            urgency_override=data.get("urgency_override", False),
            emotional_gate_applied=data.get("emotional_gate_applied", False),
            fallback_used=data.get("fallback_used", False),
        )


@dataclass
class WeaveEmitted(CanonicalEventMeta):
    """Weave content delivered to user.

    Attributes:
        candidate_event_ids:   List of WeaveCandidateArrived event_ids that were woven.
        response_text_preview: Truncated preview of the delivered response.
        delivery_mode:         How the response was delivered (immediate, batched).
    """

    event_type: str = field(default="conversation.weave.emitted", init=False)
    candidate_event_ids: list[str] = field(default_factory=list)
    response_text_preview: str = ""
    delivery_mode: str = "immediate"

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["candidate_event_ids"] = self.candidate_event_ids
        d["response_text_preview"] = self.response_text_preview
        d["delivery_mode"] = self.delivery_mode
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> WeaveEmitted:
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
            candidate_event_ids=data.get("candidate_event_ids", []),
            response_text_preview=data.get("response_text_preview", ""),
            delivery_mode=data.get("delivery_mode", "immediate"),
        )


@dataclass
class WeaveMetricsEvent(CanonicalEventMeta):
    """Per-session weave quality metrics.

    M8 E8.5.1: Emitted at session end with aggregate weave metrics.

    Attributes:
        weave_count:             Total IMMEDIATE + BATCH deliveries.
        digest_count:            Total DIGEST deliveries.
        defer_count:             Total DEFER decisions.
        suppress_count:          Total SUPPRESS decisions.
        avg_weave_latency_ms:    Average delivery latency.
        user_acknowledged_rate:  Fraction of results user acknowledged.
        fallback_count:          Times deterministic fallback was used.
    """

    event_type: str = field(default="metrics.weave.session", init=False)
    weave_count: int = 0
    digest_count: int = 0
    defer_count: int = 0
    suppress_count: int = 0
    avg_weave_latency_ms: float = 0.0
    user_acknowledged_rate: float = 0.0
    fallback_count: int = 0

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["weave_count"] = self.weave_count
        d["digest_count"] = self.digest_count
        d["defer_count"] = self.defer_count
        d["suppress_count"] = self.suppress_count
        d["avg_weave_latency_ms"] = self.avg_weave_latency_ms
        d["user_acknowledged_rate"] = self.user_acknowledged_rate
        d["fallback_count"] = self.fallback_count
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> WeaveMetricsEvent:
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
            weave_count=data.get("weave_count", 0),
            digest_count=data.get("digest_count", 0),
            defer_count=data.get("defer_count", 0),
            suppress_count=data.get("suppress_count", 0),
            avg_weave_latency_ms=data.get("avg_weave_latency_ms", 0.0),
            user_acknowledged_rate=data.get("user_acknowledged_rate", 0.0),
            fallback_count=data.get("fallback_count", 0),
        )


__all__ = [
    "WeaveCandidateArrived",
    "WeaveDecisionMade",
    "WeaveEmitted",
    "WeaveMetricsEvent",
]
