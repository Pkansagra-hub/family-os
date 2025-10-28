"""
Event Bus Schemas - Event Payload Schema Definitions

Layer: L5 Infrastructure
Component: Event Bus (Schemas)
Priority: P0 (Critical Path)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0004a: Layer 1-2 Event Bus Communication Pattern
      * Event schema definitions for IntentDetected, UserInput, VoiceCommand, BargeIn, etc.
      * Section: "Event Schema Definitions"
      * Zero-copy event passing (shared buffer, no serialization overhead)

    - ADR-0011: FlatBuffers Serialization
      * Zero-copy deserialization for events (future enhancement)
      * 150× faster than JSON for large payloads
      * Support both FlatBuffers and JSON serialization

Dependencies:
    Internal:
        - None (Layer 5 cannot import other layers per ADR-0004b)

    External:
        - dataclasses (Python 3.7+ standard library)
        - typing (type hints)
        - time (timestamp generation)
        - json (JSON serialization)

Connects To:
    Used By:
        - k1.l5_infrastructure.event_bus.event_bus (Event, EventTopic)
        - k1.l1_input.* (event payload creation)
        - k1.l2_orchestration.* (event payload parsing)

Performance Budgets:
    - Event creation: <100μs
    - Validation: <50μs
    - JSON serialization: <500μs (for <1KB payloads)
    - FlatBuffers serialization: <100μs (future, zero-copy)

Observability:
    - Metrics:
        * k1_event_schema_validation_errors_total{event_type} (counter)

    - Logs:
        * WARNING: schema validation failed (event_type, error)

References:
    - ADR-0004a: Event Bus Communication Pattern (event schema definitions)
    - ADR-0011: FlatBuffers Serialization (future zero-copy support)
    - Test: tests/k1/l5_infrastructure/event_bus/test_schemas.py
"""

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict

# Third-party imports
# None required for base schemas

# Internal imports
# NOTE: Layer 5 (Infrastructure) cannot import other K1 layers per ADR-0004b

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# Event schema version (for future schema evolution)
EVENT_SCHEMA_VERSION = "1.0"


# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class EventTopic(Enum):
    """
    Event topics for cross-layer communication (Layer 1 → Layer 2 via Layer 5)

    ADR-0004a: Section "Event Schema Definitions"
    """

    # Intent & Commands
    INTENT_DETECTED = (
        "intent.detected"  # User intent classification (3-tier: regex/SLM/LLM)
    )
    USER_INPUT = "user.input"  # Raw user message/action
    VOICE_COMMAND = "voice.command"  # Voice-based command (speech recognition)

    # Audio Events
    AUDIO_STARTED = "audio.started"  # Audio stream began
    AUDIO_ENDED = "audio.ended"  # Audio stream ended
    BARGE_IN = "audio.barge_in"  # User interruption

    # System Events
    CONSOLIDATION_COMPLETE = "system.consolidation_complete"  # K0 consolidation done
    SESSION_ENDED = "system.session_ended"  # Session termination
    QUOTA_EXCEEDED = "system.quota_exceeded"  # Usage quota hit


# =============================================================================
# SECTION 4: BASE EVENT SCHEMA
# =============================================================================


@dataclass
class Event:
    """
    Event envelope for all event bus messages

    ADR-0004a: Section "Component 1: Event Bus"

    Fields:
        topic: Event topic (routing key)
        session_id: Session identifier (for correlation)
        payload: Event-specific data (dict, flexible schema)
        cognitive_trace_id: Trace ID for observability (propagated end-to-end)
        timestamp: Unix timestamp (when event created)

    Usage:
        event = Event(
            topic=EventTopic.INTENT_DETECTED,
            session_id="session_123",
            payload={"intent": "weather_query", "confidence": 0.95},
            cognitive_trace_id="trace_456",
            timestamp=time.time(),
        )
    """

    topic: EventTopic
    session_id: str
    payload: Dict[str, Any]
    cognitive_trace_id: str
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize event to dict (for JSON encoding)

        Returns:
            Dict representation of event

        TODO(@infrastructure-team): Implement event serialization
        Assigned to: Issue #L5-2.1.2
        """
        return {
            "topic": self.topic.value,
            "session_id": self.session_id,
            "payload": self.payload,
            "cognitive_trace_id": self.cognitive_trace_id,
            "timestamp": self.timestamp,
            "schema_version": EVENT_SCHEMA_VERSION,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """
        Deserialize event from dict (from JSON decoding)

        Args:
            data: Dict representation of event

        Returns:
            Event object

        Raises:
            ValueError: If data invalid

        TODO(@infrastructure-team): Implement event deserialization
        Assigned to: Issue #L5-2.1.2
        """
        return cls(
            topic=EventTopic(data["topic"]),
            session_id=data["session_id"],
            payload=data["payload"],
            cognitive_trace_id=data["cognitive_trace_id"],
            timestamp=data["timestamp"],
        )


# =============================================================================
# SECTION 5: SPECIALIZED EVENT TYPES
# =============================================================================


@dataclass
class IntentDetectedEvent(Event):
    """
    Intent detection result from NLU (3-tier: regex/SLM/LLM)

    ADR-0004a: Section "IntentDetected Event"

    Payload Fields:
        intent: Intent name (e.g., "weather_query", "calendar_add")
        confidence: Confidence score (0.0-1.0)
        tier: Classification tier (1=regex, 2=SLM, 3=LLM)
        timestamp: Unix timestamp (when classified)

    Usage:
        event = IntentDetectedEvent.create(
            session_id="session_123",
            cognitive_trace_id="trace_456",
            intent="weather_query",
            confidence=0.95,
            tier=2,  # SLM classified
        )
    """

    @classmethod
    def create(
        cls,
        session_id: str,
        cognitive_trace_id: str,
        intent: str,
        confidence: float,
        tier: int,
    ) -> "IntentDetectedEvent":
        """
        Create IntentDetected event

        Args:
            session_id: Session identifier
            cognitive_trace_id: Trace ID for observability
            intent: Intent name
            confidence: Confidence score (0.0-1.0)
            tier: Classification tier (1=regex, 2=SLM, 3=LLM)

        Returns:
            IntentDetectedEvent object

        TODO(@infrastructure-team): Implement event creation
        Assigned to: Issue #L5-2.1.2
        """
        return cls(
            topic=EventTopic.INTENT_DETECTED,
            session_id=session_id,
            payload={
                "intent": intent,
                "confidence": confidence,
                "tier": tier,
                "timestamp": time.time(),
            },
            cognitive_trace_id=cognitive_trace_id,
            timestamp=time.time(),
        )


@dataclass
class UserInputEvent(Event):
    """
    Raw user input (text, audio, video, etc.)

    ADR-0004a: Section "UserInput Event"

    Payload Fields:
        text: User input text (normalized)
        modality: "text", "voice", "video"
        language: ISO 639-1 code (e.g., "en", "es")
        timestamp: Unix timestamp

    Usage:
        event = UserInputEvent.create(
            session_id="session_123",
            cognitive_trace_id="trace_456",
            text="What's the weather?",
            modality="text",
            language="en",
        )
    """

    @classmethod
    def create(
        cls,
        session_id: str,
        cognitive_trace_id: str,
        text: str,
        modality: str,
        language: str,
    ) -> "UserInputEvent":
        """
        Create UserInput event

        Args:
            session_id: Session identifier
            cognitive_trace_id: Trace ID for observability
            text: User input text (normalized)
            modality: "text", "voice", "video"
            language: ISO 639-1 code (e.g., "en", "es")

        Returns:
            UserInputEvent object

        TODO(@infrastructure-team): Implement event creation
        Assigned to: Issue #L5-2.1.2
        """
        return cls(
            topic=EventTopic.USER_INPUT,
            session_id=session_id,
            payload={
                "text": text,
                "modality": modality,
                "language": language,
                "timestamp": time.time(),
            },
            cognitive_trace_id=cognitive_trace_id,
            timestamp=time.time(),
        )


@dataclass
class VoiceCommandEvent(Event):
    """
    Voice command (from speech recognition)

    ADR-0004a: Section "VoiceCommand Event"

    Payload Fields:
        command: Voice command (e.g., "stop", "pause", "resume")
        action: Action type ("barge_in", "pause", "resume", "stop")
        timestamp: Unix timestamp

    Usage:
        event = VoiceCommandEvent.create(
            session_id="session_123",
            cognitive_trace_id="trace_456",
            command="stop",
            action="stop",
        )
    """

    @classmethod
    def create(
        cls,
        session_id: str,
        cognitive_trace_id: str,
        command: str,
        action: str,
    ) -> "VoiceCommandEvent":
        """
        Create VoiceCommand event

        Args:
            session_id: Session identifier
            cognitive_trace_id: Trace ID for observability
            command: Voice command
            action: Action type

        Returns:
            VoiceCommandEvent object

        TODO(@infrastructure-team): Implement event creation
        Assigned to: Issue #L5-2.1.2
        """
        return cls(
            topic=EventTopic.VOICE_COMMAND,
            session_id=session_id,
            payload={
                "command": command,
                "action": action,
                "timestamp": time.time(),
            },
            cognitive_trace_id=cognitive_trace_id,
            timestamp=time.time(),
        )


@dataclass
class BargeInEvent(Event):
    """
    User interruption event (barge-in)

    ADR-0004a: Section "VoiceCommand Event" (barge-in action)

    Payload Fields:
        interrupted_at: Unix timestamp (when interruption detected)
        interrupted_task: Task ID that was interrupted
        timestamp_ms: Timestamp in milliseconds

    Usage:
        event = BargeInEvent.create(
            session_id="session_123",
            cognitive_trace_id="trace_456",
            interrupted_task="task_456",
        )
    """

    @classmethod
    def create(
        cls,
        session_id: str,
        cognitive_trace_id: str,
        interrupted_task: str,
    ) -> "BargeInEvent":
        """
        Create BargeIn event

        Args:
            session_id: Session identifier
            cognitive_trace_id: Trace ID for observability
            interrupted_task: Task ID that was interrupted

        Returns:
            BargeInEvent object

        TODO(@infrastructure-team): Implement event creation
        Assigned to: Issue #L5-2.1.2
        """
        timestamp = time.time()
        return cls(
            topic=EventTopic.BARGE_IN,
            session_id=session_id,
            payload={
                "interrupted_at": timestamp,
                "interrupted_task": interrupted_task,
                "timestamp_ms": int(timestamp * 1000),
            },
            cognitive_trace_id=cognitive_trace_id,
            timestamp=timestamp,
        )


@dataclass
class ConsolidationCompleteEvent(Event):
    """
    K0 consolidation completed event

    ADR-0004a: Section "System Events"

    Payload Fields:
        session_id: Session identifier
        consolidation_duration_ms: Duration in milliseconds
        timestamp: Unix timestamp

    Usage:
        event = ConsolidationCompleteEvent.create(
            session_id="session_123",
            cognitive_trace_id="trace_456",
            consolidation_duration_ms=150,
        )
    """

    @classmethod
    def create(
        cls,
        session_id: str,
        cognitive_trace_id: str,
        consolidation_duration_ms: int,
    ) -> "ConsolidationCompleteEvent":
        """
        Create ConsolidationComplete event

        Args:
            session_id: Session identifier
            cognitive_trace_id: Trace ID for observability
            consolidation_duration_ms: Duration in milliseconds

        Returns:
            ConsolidationCompleteEvent object

        TODO(@infrastructure-team): Implement event creation
        Assigned to: Issue #L5-2.1.2
        """
        return cls(
            topic=EventTopic.CONSOLIDATION_COMPLETE,
            session_id=session_id,
            payload={
                "session_id": session_id,
                "consolidation_duration_ms": consolidation_duration_ms,
                "timestamp": time.time(),
            },
            cognitive_trace_id=cognitive_trace_id,
            timestamp=time.time(),
        )


@dataclass
class SessionEndedEvent(Event):
    """
    Session termination event

    ADR-0004a: Section "System Events"

    Payload Fields:
        session_id: Session identifier
        reason: Termination reason ("user_exit", "timeout", "error")
        total_turns: Total conversation turns
        timestamp: Unix timestamp

    Usage:
        event = SessionEndedEvent.create(
            session_id="session_123",
            cognitive_trace_id="trace_456",
            reason="user_exit",
            total_turns=42,
        )
    """

    @classmethod
    def create(
        cls,
        session_id: str,
        cognitive_trace_id: str,
        reason: str,
        total_turns: int,
    ) -> "SessionEndedEvent":
        """
        Create SessionEnded event

        Args:
            session_id: Session identifier
            cognitive_trace_id: Trace ID for observability
            reason: Termination reason
            total_turns: Total conversation turns

        Returns:
            SessionEndedEvent object

        TODO(@infrastructure-team): Implement event creation
        Assigned to: Issue #L5-2.1.2
        """
        return cls(
            topic=EventTopic.SESSION_ENDED,
            session_id=session_id,
            payload={
                "session_id": session_id,
                "reason": reason,
                "total_turns": total_turns,
                "timestamp": time.time(),
            },
            cognitive_trace_id=cognitive_trace_id,
            timestamp=time.time(),
        )


# =============================================================================
# SECTION 6: VALIDATION & SERIALIZATION
# =============================================================================


def validate_event(event: Event) -> bool:
    """
    Validate event schema

    Args:
        event: Event object to validate

    Returns:
        True if valid, False otherwise

    Validates:
        - topic is valid EventTopic
        - session_id not empty
        - cognitive_trace_id not empty
        - timestamp is positive float
        - payload is dict

    TODO(@infrastructure-team): Implement event validation
    Assigned to: Issue #L5-2.1.2
    """
    try:
        # TODO(@infrastructure-team): Validate topic
        if not isinstance(event.topic, EventTopic):
            logger.warning("invalid_event_topic", topic=str(event.topic))
            return False

        # TODO(@infrastructure-team): Validate session_id
        if not event.session_id or not isinstance(event.session_id, str):
            logger.warning("invalid_event_session_id", session_id=event.session_id)
            return False

        # TODO(@infrastructure-team): Validate cognitive_trace_id
        if not event.cognitive_trace_id or not isinstance(
            event.cognitive_trace_id, str
        ):
            logger.warning("invalid_event_trace_id", trace_id=event.cognitive_trace_id)
            return False

        # TODO(@infrastructure-team): Validate timestamp
        if not isinstance(event.timestamp, (int, float)) or event.timestamp <= 0:
            logger.warning("invalid_event_timestamp", timestamp=event.timestamp)
            return False

        # TODO(@infrastructure-team): Validate payload
        if not isinstance(event.payload, dict):
            logger.warning("invalid_event_payload", payload_type=type(event.payload))
            return False

        return True

    except Exception as e:
        logger.error("event_validation_error", error=str(e))
        return False


def serialize_event(event: Event, format: str = "json") -> bytes:
    """
    Serialize event to bytes

    Args:
        event: Event object to serialize
        format: Serialization format ("json" or "flatbuffers")

    Returns:
        Serialized event bytes

    Raises:
        ValueError: If format invalid

    TODO(@infrastructure-team): Implement event serialization
    Assigned to: Issue #L5-2.1.2

    Steps:
        1. Validate event
        2. If format == "json": Use json.dumps(event.to_dict()).encode()
        3. If format == "flatbuffers": Use FlatBuffers builder (future)
        4. Return bytes
    """
    if not validate_event(event):
        raise ValueError("Invalid event schema")

    if format == "json":
        # TODO(@infrastructure-team): JSON serialization
        data = event.to_dict()
        return json.dumps(data).encode("utf-8")
    elif format == "flatbuffers":
        # TODO(@infrastructure-team): FlatBuffers serialization (future)
        raise NotImplementedError(
            "FlatBuffers serialization not yet implemented (ADR-0011)"
        )
    else:
        raise ValueError(f"Unknown serialization format: {format}")


def deserialize_event(data: bytes, format: str = "json") -> Event:
    """
    Deserialize event from bytes

    Args:
        data: Serialized event bytes
        format: Serialization format ("json" or "flatbuffers")

    Returns:
        Event object

    Raises:
        ValueError: If format invalid or data malformed

    TODO(@infrastructure-team): Implement event deserialization
    Assigned to: Issue #L5-2.1.2

    Steps:
        1. If format == "json": Use json.loads(data.decode()) + Event.from_dict()
        2. If format == "flatbuffers": Use FlatBuffers reader (future)
        3. Validate deserialized event
        4. Return Event object
    """
    if format == "json":
        # TODO(@infrastructure-team): JSON deserialization
        data_dict = json.loads(data.decode("utf-8"))
        event = Event.from_dict(data_dict)

        if not validate_event(event):
            raise ValueError("Deserialized event failed validation")

        return event
    elif format == "flatbuffers":
        # TODO(@infrastructure-team): FlatBuffers deserialization (future)
        raise NotImplementedError(
            "FlatBuffers deserialization not yet implemented (ADR-0011)"
        )
    else:
        raise ValueError(f"Unknown serialization format: {format}")


# =============================================================================
# SECTION 7: MODULE EXPORTS
# =============================================================================

__all__ = [
    "Event",
    "EventTopic",
    "IntentDetectedEvent",
    "UserInputEvent",
    "VoiceCommandEvent",
    "BargeInEvent",
    "ConsolidationCompleteEvent",
    "SessionEndedEvent",
    "validate_event",
    "serialize_event",
    "deserialize_event",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_event_schema_validation_errors_total{event_type} (counter)
#
# Logs to emit:
#   - Level: WARNING (validation failures)
#   - Fields: component="event_bus.schemas", event_type, error
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/event_bus/test_schemas.py
#   - Test: Event creation and validation
#   - Test: IntentDetectedEvent.create()
#   - Test: UserInputEvent.create()
#   - Test: VoiceCommandEvent.create()
#   - Test: BargeInEvent.create()
#   - Test: ConsolidationCompleteEvent.create()
#   - Test: SessionEndedEvent.create()
#   - Test: JSON serialization/deserialization
#   - Test: Schema validation (valid and invalid events)
#   - Test: FlatBuffers support (future)
#
# No simulation code allowed:
#   - Use real event objects
#   - Test with actual payload data
#   - Integration tests > unit tests
#
# =============================================================================
