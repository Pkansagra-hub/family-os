"""
k1.concierge.events.base -- V3 canonical event envelope metadata.

M1 E1.1.1: Every V3 event payload extends CanonicalEventMeta.

The 11 canonical metadata fields provide correlation, causation tracking,
and schema versioning for all domain events. These fields go INSIDE the
bus payload (the Envelope is transport; the event is domain).

Field mapping (Envelope transport vs CanonicalEventMeta domain):
    Envelope.envelope_id      != event_id        (transport vs domain)
    Envelope.cognitive_trace_id -> correlation_id (mapped at creation)
    Envelope.parent_id        != causation_id    (bus ordering vs domain cause)
    Envelope.created_ns       != ts_utc          (monotonic clock vs wall clock)
    Envelope.sequence         != ledger seq       (bus gap detection vs session order)

Reference: poc/k1_poc/sessionstate/events.py:80 (BaseEvent pattern extended).
Reference: k1/bus/envelope/envelope.py:135 (Envelope field names for mapping).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Required metadata field names for validation
CANONICAL_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "event_id",
        "event_type",
        "session_id",
        "correlation_id",
        "causation_id",
        "actor",
        "ts_utc",
        "payload_schema_version",
    }
)


def _utcnow_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CanonicalEventMeta:
    """Base class for all V3 canonical events.

    Every V3 event payload extends this with domain-specific fields.
    Subclasses MUST set ``event_type`` as a class-level default.

    Attributes:
        event_id:               Unique domain event ID (UUID4, auto-generated).
        event_type:             Canonical type string (e.g. "task.completed").
        session_id:             Session scope identifier.
        correlation_id:         Request-level correlation (maps from Envelope.cognitive_trace_id).
        causation_id:           ID of the event that CAUSED this event.
        parent_event_id:        ID of the logical parent event (domain hierarchy, not bus).
        task_id:                Task scope (empty for conversation-level events).
        actor:                  Who emitted this event ("front", "back", "fsm", "arbiter", "system").
        ts_utc:                 Wall-clock UTC timestamp (ISO 8601, auto-generated).
        priority:               Event priority (0=URGENT .. 3=BACKGROUND).
        payload_schema_version: Schema version string (semver).
    """

    event_type: str = ""
    session_id: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    parent_event_id: str = ""
    task_id: str = ""
    actor: str = ""
    priority: int = 1
    payload_schema_version: str = "1.0.0"
    # Auto-generated fields last (have defaults)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts_utc: str = field(default_factory=_utcnow_iso)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to dict suitable for bus envelope payload.

        Returns all canonical metadata fields plus subclass-specific fields.
        """
        result: dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "parent_event_id": self.parent_event_id,
            "task_id": self.task_id,
            "actor": self.actor,
            "ts_utc": self.ts_utc,
            "priority": self.priority,
            "payload_schema_version": self.payload_schema_version,
        }
        # Add subclass-specific fields (anything not in base)
        base_fields = {
            "event_id",
            "event_type",
            "session_id",
            "correlation_id",
            "causation_id",
            "parent_event_id",
            "task_id",
            "actor",
            "ts_utc",
            "priority",
            "payload_schema_version",
        }
        for key, value in self.__dict__.items():
            if key not in base_fields:
                result[key] = value
        return result

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> CanonicalEventMeta:
        """Deserialize from dict payload.

        Subclasses should override this to parse domain-specific fields.
        """
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=data.get("event_type", ""),
            session_id=data.get("session_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            parent_event_id=data.get("parent_event_id", ""),
            task_id=data.get("task_id", ""),
            actor=data.get("actor", ""),
            ts_utc=data.get("ts_utc", _utcnow_iso()),
            priority=data.get("priority", 1),
            payload_schema_version=data.get("payload_schema_version", "1.0.0"),
        )


def validate_canonical_metadata(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate that a payload dict contains all required canonical metadata fields.

    Args:
        payload: Dict to validate.

    Returns:
        Tuple of (is_valid, list_of_error_messages).
    """
    errors: list[str] = []
    for field_name in CANONICAL_REQUIRED_FIELDS:
        if field_name not in payload:
            errors.append(f"Missing required canonical field: {field_name}")
        elif not payload[field_name] and field_name not in ("causation_id", "correlation_id"):
            # causation_id can be empty for root events
            # correlation_id can be empty when not correlated to a request
            errors.append(f"Empty canonical field: {field_name}")
    return (len(errors) == 0, errors)


def from_envelope(envelope: Any, actor: str, causation_id: str | None = None) -> dict[str, Any]:
    """Extract canonical metadata seed from a bus Envelope.

    Returns a dict of metadata fields that can be passed as kwargs
    to any CanonicalEventMeta subclass constructor.

    Args:
        envelope: A k1.bus.envelope.Envelope instance.
        actor: Who is creating this canonical event.
        causation_id: Explicit causation ID; falls back to str(envelope.parent_id).

    Returns:
        Dict of canonical metadata fields.
    """
    return {
        "session_id": getattr(envelope, "session_id", ""),
        "correlation_id": getattr(envelope, "cognitive_trace_id", ""),
        "causation_id": causation_id or str(getattr(envelope, "parent_id", 0)),
        "actor": actor,
    }
