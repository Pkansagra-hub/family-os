"""
k1.concierge.events.conversation -- V3 canonical conversation events.

M1 E1.1.2: Three conversation-level event schemas.

Events:
    UserInputReceived          -- User sent a message.
    IntentArbitrated           -- Arbiter classified intent (schema only; M4 implementation).
    DeadLettered               -- Event routed to dead-letter stream (schema only; M2 implementation).

Topic mapping (V3 reuses existing topic strings):
    UserInputReceived   -> k1.session.user.input.v1
    IntentArbitrated    -> (future: k1.session.intent.arbitrated.v1, M4)
    DeadLettered        -> (future: k1.internal.dead_letter.v1, M2)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from k1.concierge.events.base import CanonicalEventMeta


@dataclass
class UserInputReceived(CanonicalEventMeta):
    """User sent a message to the system.

    This is typically the root event of a causal chain.
    Maps to existing topic k1.session.user.input.v1.

    Attributes:
        text:        The user's message text.
        input_type:  Input modality (text, voice, gesture).
        device_id:   Device identifier for multi-device support (M6).
        raw_input:   Original unprocessed input form.
    """

    event_type: str = field(default="conversation.user_input.received", init=False)
    text: str = ""
    input_type: str = "text"
    device_id: str = ""
    raw_input: str = ""

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["text"] = self.text
        d["input_type"] = self.input_type
        d["device_id"] = self.device_id
        d["raw_input"] = self.raw_input
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> UserInputReceived:
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
            text=data.get("text", ""),
            input_type=data.get("input_type", "text"),
            device_id=data.get("device_id", ""),
            raw_input=data.get("raw_input", ""),
        )


@dataclass
class IntentArbitrated(CanonicalEventMeta):
    """Arbiter classified user intent.

    Schema defined in M1; implementation in M4 (Conversation Arbiter).

    Attributes:
        intent_class:     Classification result (cancel, modify_inflight, parallel_new, defer).
        confidence:       Classification confidence [0.0, 1.0].
        target_task_id:   Task ID if modifying an existing task.
        routing_metadata: Additional routing context from the arbiter.
    """

    event_type: str = field(default="conversation.intent.arbitrated", init=False)
    intent_class: str = ""
    confidence: float = 0.0
    target_task_id: str = ""
    routing_metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["intent_class"] = self.intent_class
        d["confidence"] = self.confidence
        d["target_task_id"] = self.target_task_id
        d["routing_metadata"] = self.routing_metadata
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> IntentArbitrated:
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
            intent_class=data.get("intent_class", ""),
            confidence=data.get("confidence", 0.0),
            target_task_id=data.get("target_task_id", ""),
            routing_metadata=data.get("routing_metadata", {}),
        )


@dataclass
class DeadLettered(CanonicalEventMeta):
    """Event routed to the dead-letter stream.

    Schema defined in M1; implementation in M2 (FSM Hardening).

    Attributes:
        original_event:        Serialized original event that was rejected.
        reason:                Why the event was dead-lettered (invalid_transition, orphan, expired).
        fsm_state_at_rejection: FSM state when the event was rejected.
        original_topic:        Bus topic of the original event.
    """

    event_type: str = field(default="conversation.dead_lettered", init=False)
    original_event: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    fsm_state_at_rejection: str = ""
    original_topic: str = ""

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["original_event"] = self.original_event
        d["reason"] = self.reason
        d["fsm_state_at_rejection"] = self.fsm_state_at_rejection
        d["original_topic"] = self.original_topic
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> DeadLettered:
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
            original_event=data.get("original_event", {}),
            reason=data.get("reason", ""),
            fsm_state_at_rejection=data.get("fsm_state_at_rejection", ""),
            original_topic=data.get("original_topic", ""),
        )


@dataclass
class ResponseFinalDecided(CanonicalEventMeta):
    """Response-final decision recorded for audit trail.

    M2 E2.5.4: Records the pure-function decision from decide_response_final()
    into the ledger for crash recovery, observability, and debugging.

    Attributes:
        decision_action:     ResponseFinalAction value string.
        target_state:        ConciergeState name the FSM transitions to.
        has_pending_results: Whether pending results existed at decision time.
        has_active_tasks:    Whether active tasks existed at decision time.
        emit_turn_completed: Whether the decision emits turn.completed.
        schedule_weave:      Whether the decision schedules a weave batch.
        entry_type:          History entry type (final, weave, proactive, proactive_fallback).
    """

    event_type: str = field(default="conversation.response_final.decided", init=False)
    decision_action: str = ""
    target_state: str = ""
    has_pending_results: bool = False
    has_active_tasks: bool = False
    emit_turn_completed: bool = False
    schedule_weave: bool = False
    entry_type: str = ""

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["decision_action"] = self.decision_action
        d["target_state"] = self.target_state
        d["has_pending_results"] = self.has_pending_results
        d["has_active_tasks"] = self.has_active_tasks
        d["emit_turn_completed"] = self.emit_turn_completed
        d["schedule_weave"] = self.schedule_weave
        d["entry_type"] = self.entry_type
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> ResponseFinalDecided:
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
            decision_action=data.get("decision_action", ""),
            target_state=data.get("target_state", ""),
            has_pending_results=data.get("has_pending_results", False),
            has_active_tasks=data.get("has_active_tasks", False),
            emit_turn_completed=data.get("emit_turn_completed", False),
            schedule_weave=data.get("schedule_weave", False),
            entry_type=data.get("entry_type", ""),
        )


__all__ = [
    "UserInputReceived",
    "IntentArbitrated",
    "DeadLettered",
    "ResponseFinalDecided",
    "Phase1Classified",
    "TaskRouted",
]


# ---------------------------------------------------------------------------
# M10 E10.3.4: Phase 1 and routing observability events
# ---------------------------------------------------------------------------


@dataclass
class Phase1Classified(CanonicalEventMeta):
    """Emitted after every Phase 1 classification.

    M10 E10.3.4: Observability event for tracing and dashboards.
    """

    event_type: str = field(default="k1.phase1.classified.v1", init=False)
    turn_number: int = 0
    # P3.4a: complexity_tier removed; replaced by derived_plan.
    intent_primary: str = ""
    domain_primary: str = ""
    safety_band: str = ""
    emotion_primary: str = ""
    classification_latency_ms: float = 0.0
    is_degraded: bool = False
    # P3.4c: derived "needs plan" flag computed at FSM/Phase 1 time.
    derived_plan: bool = False

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["turn_number"] = self.turn_number
        d["intent_primary"] = self.intent_primary
        d["domain_primary"] = self.domain_primary
        d["safety_band"] = self.safety_band
        d["emotion_primary"] = self.emotion_primary
        d["classification_latency_ms"] = self.classification_latency_ms
        d["is_degraded"] = self.is_degraded
        d["derived_plan"] = self.derived_plan
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Phase1Classified:
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
            turn_number=data.get("turn_number", 0),
            intent_primary=data.get("intent_primary", ""),
            domain_primary=data.get("domain_primary", ""),
            safety_band=data.get("safety_band", ""),
            emotion_primary=data.get("emotion_primary", ""),
            classification_latency_ms=data.get("classification_latency_ms", 0.0),
            is_degraded=data.get("is_degraded", False),
            derived_plan=bool(data.get("derived_plan", False)),
        )


@dataclass
class TaskRouted(CanonicalEventMeta):
    """Emitted after task routing decision.

    M10 E10.3.4: Observability event for tracing and dashboards.
    """

    event_type: str = field(default="k1.task.routed.v1", init=False)
    task_id: str = ""
    assigned_tier: str = ""
    routing_path: str = ""
    budget_limit: int = 0

    def to_payload(self) -> dict[str, Any]:
        d = super().to_payload()
        d["task_id"] = self.task_id
        d["assigned_tier"] = self.assigned_tier
        d["routing_path"] = self.routing_path
        d["budget_limit"] = self.budget_limit
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> TaskRouted:
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
            assigned_tier=data.get("assigned_tier", ""),
            routing_path=data.get("routing_path", ""),
            budget_limit=data.get("budget_limit", 0),
        )
