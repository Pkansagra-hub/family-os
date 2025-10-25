"""K1 Event Bus Schema Definitions.

This module contains the runtime dataclass representations for the Layer 1→2
event bus payloads described in :doc:`ADR-0004a` and enforced by the contract
``k1/contracts/event_bus/event_schemas.yaml``. The dataclasses are immutable,
perform lightweight validation, and normalise timestamps to UTC so that event
publishers can safely share references across the in-memory bus without
serialization overhead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar, Mapping

EVENT_SCHEMA_VERSION = "1.0.0"
"""Semantic version applied to all event payloads."""


class EventSchemaError(ValueError):
    """Raised when an event payload violates the published contract."""


class EventTopic(str, Enum):
    """Contracted event topics for the internal event bus."""

    INTENT_DETECTED = "intent_detected"
    USER_INPUT = "user_input"
    VOICE_COMMAND = "voice_command"
    BARGE_IN = "barge_in"


_TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


def _empty_str_dict() -> dict[str, Any]:
    """Return an empty dict for mapping defaults."""

    return {}


def _validate_trace_id(value: str) -> None:
    """Ensure the trace identifier matches contract expectations."""

    if not value:
        raise EventSchemaError("cognitive_trace_id must be non-empty")
    normalized = value.replace("-", "")
    if not _TRACE_ID_PATTERN.fullmatch(normalized):
        raise EventSchemaError(
            "cognitive_trace_id must be 32 hexadecimal characters (hyphenated UUIDs allowed)",
        )


def _ensure_utc(dt: datetime) -> datetime:
    """Normalise timestamps to timezone-aware UTC datetimes."""

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _freeze_mapping(
    data: Mapping[str, Any] | Mapping[Any, Any] | None,
    *,
    field_name: str,
) -> Mapping[str, Any]:
    """Return an immutable mapping after validating key types."""

    if data is None:
        return MappingProxyType({})

    invalid_keys = [key for key in data.keys() if not isinstance(key, str)]
    if invalid_keys:
        raise EventSchemaError(
            f"{field_name} keys must be strings (invalid: {invalid_keys!r})"
        )

    return MappingProxyType(dict(data))


def _serialise_value(value: Any) -> Any:
    """Convert runtime dataclass attribute values for payload emission."""

    if isinstance(value, MappingProxyType):
        value = dict(value)
    if isinstance(value, Mapping):
        return {str(key): _serialise_value(inner) for key, inner in value.items()}
    if isinstance(value, tuple):
        return tuple(_serialise_value(item) for item in value)
    if isinstance(value, list):
        return [_serialise_value(item) for item in value]
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class EventBase:
    """Common envelope fields shared by all Layer 1→2 events."""

    session_id: str
    cognitive_trace_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    topic: ClassVar[EventTopic]
    schema_version: ClassVar[str] = EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:  # noqa: D401 - dataclass hook
        if not self.session_id:
            raise EventSchemaError("session_id must be provided")
        _validate_trace_id(self.cognitive_trace_id)
        object.__setattr__(self, "timestamp", _ensure_utc(self.timestamp))

    def to_payload(self) -> dict[str, Any]:
        """Serialise the event to a contract-compliant dictionary."""

        payload = {
            field_info.name: _serialise_value(getattr(self, field_info.name))
            for field_info in fields(self)
        }
        payload["timestamp"] = self.timestamp.isoformat()
        payload["topic"] = self.topic.value
        payload["schema_version"] = self.schema_version
        return payload


@dataclass(slots=True, kw_only=True, frozen=True)
class IntentDetectedEvent(EventBase):
    """Intent detection result emitted by the multi-tier intent router."""

    topic: ClassVar[EventTopic] = EventTopic.INTENT_DETECTED

    intent: str
    confidence: float
    tier: str
    entities: Mapping[str, Any] = field(default_factory=_empty_str_dict)

    VALID_TIERS: ClassVar[tuple[str, ...]] = ("T1_RULE", "T2_SLM", "T3_LLM")

    def __post_init__(self) -> None:
        EventBase.__post_init__(self)
        if not self.intent:
            raise EventSchemaError("intent must be non-empty")
        if not (0.0 <= self.confidence <= 1.0):
            raise EventSchemaError("confidence must be between 0.0 and 1.0 inclusive")
        if self.tier not in self.VALID_TIERS:
            raise EventSchemaError(f"tier must be one of {self.VALID_TIERS!r}")
        object.__setattr__(
            self, "entities", _freeze_mapping(self.entities, field_name="entities")
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class UserInputEvent(EventBase):
    """Normalised user input forwarded to the orchestration layer."""

    topic: ClassVar[EventTopic] = EventTopic.USER_INPUT

    text: str
    modality: str
    metadata: Mapping[str, Any] | None = None

    VALID_MODALITIES: ClassVar[tuple[str, ...]] = ("text", "voice")

    def __post_init__(self) -> None:
        EventBase.__post_init__(self)
        if not self.text:
            raise EventSchemaError("text must be non-empty")
        if self.modality not in self.VALID_MODALITIES:
            raise EventSchemaError(f"modality must be one of {self.VALID_MODALITIES!r}")
        frozen_metadata = _freeze_mapping(self.metadata, field_name="metadata")
        object.__setattr__(self, "metadata", frozen_metadata)


@dataclass(slots=True, kw_only=True, frozen=True)
class VoiceCommandEvent(EventBase):
    """Voice command transcription emitted by the ASR pipeline."""

    topic: ClassVar[EventTopic] = EventTopic.VOICE_COMMAND

    transcript: str
    vad_confidence: float
    language: str
    partial: bool = False

    _LANGUAGE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^[a-z]{2}(?:-[A-Z]{2})?$"
    )

    def __post_init__(self) -> None:
        EventBase.__post_init__(self)
        if not self.transcript:
            raise EventSchemaError("transcript must be non-empty")
        if not (0.0 <= self.vad_confidence <= 1.0):
            raise EventSchemaError(
                "vad_confidence must be between 0.0 and 1.0 inclusive"
            )
        if not self._LANGUAGE_PATTERN.fullmatch(self.language):
            raise EventSchemaError(
                "language must be a valid ISO 639-1 or BCP-47 code (e.g., 'en', 'en-US')"
            )


@dataclass(slots=True, kw_only=True, frozen=True)
class BargeInEvent(EventBase):
    """User interruption of an active conversational turn."""

    topic: ClassVar[EventTopic] = EventTopic.BARGE_IN

    interrupted_turn_id: str
    reason: str

    VALID_REASONS: ClassVar[tuple[str, ...]] = ("user_interrupt", "timeout", "error")

    def __post_init__(self) -> None:
        EventBase.__post_init__(self)
        if not self.interrupted_turn_id:
            raise EventSchemaError("interrupted_turn_id must be non-empty")
        if self.reason not in self.VALID_REASONS:
            raise EventSchemaError(f"reason must be one of {self.VALID_REASONS!r}")


__all__ = [
    "EVENT_SCHEMA_VERSION",
    "EventBase",
    "EventSchemaError",
    "EventTopic",
    "IntentDetectedEvent",
    "UserInputEvent",
    "VoiceCommandEvent",
    "BargeInEvent",
]
