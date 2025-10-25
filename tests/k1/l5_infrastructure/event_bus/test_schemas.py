"""WARD tests for K1 event bus schema dataclasses.

Verifies contract invariants for Layer 1→2 event payloads described in
ADR-0004a and implemented in ``k1.l5_infrastructure.event_bus.schemas``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from ward import test  # type: ignore[attr-defined]

from k1.l5_infrastructure.event_bus.schemas import (
    BargeInEvent,
    EventSchemaError,
    EventTopic,
    IntentDetectedEvent,
    UserInputEvent,
    VoiceCommandEvent,
)

_TIMESTAMP = datetime(2025, 10, 24, 12, 0, 0, tzinfo=timezone.utc)
_TRACE_ID = "5f2d4c7a8b3e41e8a9d9c6f1b2a4d687"
_SESSION_ID = "session_12345"


def _intent_event(**overrides: Any) -> IntentDetectedEvent:
    payload: Dict[str, Any] = {
        "session_id": _SESSION_ID,
        "cognitive_trace_id": _TRACE_ID,
        "timestamp": _TIMESTAMP,
        "intent": "weather_query",
        "confidence": 0.91,
        "tier": "T1_RULE",
        "entities": {"location": "San Francisco"},
    }
    payload.update(overrides)
    return IntentDetectedEvent(**payload)


def _user_input_event(**overrides: Any) -> UserInputEvent:
    payload: Dict[str, Any] = {
        "session_id": _SESSION_ID,
        "cognitive_trace_id": _TRACE_ID,
        "timestamp": _TIMESTAMP,
        "text": "Show me the weather",
        "modality": "voice",
        "metadata": {"language": "en", "asr_confidence": 0.95},
    }
    payload.update(overrides)
    return UserInputEvent(**payload)


def _voice_command_event(**overrides: Any) -> VoiceCommandEvent:
    payload: Dict[str, Any] = {
        "session_id": _SESSION_ID,
        "cognitive_trace_id": _TRACE_ID,
        "timestamp": _TIMESTAMP,
        "transcript": "Turn on the living room lights",
        "vad_confidence": 0.84,
        "language": "en",
        "partial": False,
    }
    payload.update(overrides)
    return VoiceCommandEvent(**payload)


def _barge_in_event(**overrides: Any) -> BargeInEvent:
    payload: Dict[str, Any] = {
        "session_id": _SESSION_ID,
        "cognitive_trace_id": _TRACE_ID,
        "timestamp": _TIMESTAMP,
        "interrupted_turn_id": "turn_98765",
        "reason": "user_interrupt",
    }
    payload.update(overrides)
    return BargeInEvent(**payload)


@test("intent detected event serialises with topic and schema version")
def _() -> None:
    event = _intent_event()
    payload = event.to_payload()

    assert payload["topic"] == EventTopic.INTENT_DETECTED.value
    assert payload["schema_version"] == "1.0.0"
    assert payload["timestamp"] == _TIMESTAMP.isoformat()
    assert payload["entities"]["location"] == "San Francisco"


@test("confidence outside contract bounds raises validation error")
def _() -> None:
    try:
        _intent_event(confidence=1.5)
        assert False, "Expected EventSchemaError for confidence > 1.0"
    except EventSchemaError as exc:
        assert "confidence" in str(exc)


@test("metadata mapping is immutable")
def _() -> None:
    event = _user_input_event()

    try:
        event.metadata["asr_confidence"] = 1.0  # type: ignore[index]
        assert False, "Expected metadata mapping to be immutable"
    except TypeError:
        pass


@test("invalid cognitive trace id is rejected")
def _() -> None:
    try:
        _user_input_event(cognitive_trace_id="invalid-trace")
        assert False, "Expected EventSchemaError for malformed trace id"
    except EventSchemaError as exc:
        assert "cognitive_trace_id" in str(exc)


@test("voice command validates language and VAD confidence range")
def _() -> None:
    try:
        _voice_command_event(vad_confidence=-0.1)
        assert False, "Expected EventSchemaError for negative VAD confidence"
    except EventSchemaError as exc:
        assert "vad_confidence" in str(exc)

    try:
        _voice_command_event(language="english")
        assert False, "Expected EventSchemaError for invalid language code"
    except EventSchemaError as exc:
        assert "language" in str(exc)


@test("barge-in reason enum is enforced")
def _() -> None:
    try:
        _barge_in_event(reason="network_glitch")
        assert False, "Expected EventSchemaError for unsupported reason"
    except EventSchemaError as exc:
        assert "reason" in str(exc)
