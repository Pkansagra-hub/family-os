"""M2.I7 Live API final-turn normalization for section updates."""

from __future__ import annotations

import json

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.section_update.input_builder import build_section_update_input
from k1.concierge.section_update.live_api import (
    LIVE_TURN_COMPLETED_TOPIC,
    build_live_section_update_input,
    is_live_turn_complete_record,
    normalize_live_turn_complete_record,
)


def _text_envelope(payload: dict) -> Envelope:
    return Envelope(
        topic=LIVE_TURN_COMPLETED_TOPIC,
        payload=json.dumps(payload).encode(),
        payload_format=PayloadFormat.JSON,
        priority=Priority.INTERACTIVE,
        session_id=str(payload.get("session_id", "")),
        cognitive_trace_id=str(payload.get("cognitive_trace_id", "")),
    )


def test_live_and_text_final_turns_produce_same_semantic_input_fields() -> None:
    record = {
        "event_type": "response.done",
        "session_id": "session-1",
        "turn_id": "session-1:7",
        "turn_number": 7,
        "cognitive_trace_id": "trace-1",
        "device_id": "device-voice",
        "timestamp_ms": 123456,
        "final_transcript": "I prefer quiet rooms",
        "assistant_text": "Got it.",
    }

    assert is_live_turn_complete_record(record) is True
    live = normalize_live_turn_complete_record(record).input_data
    text = build_section_update_input(
        envelope=_text_envelope(
            {
                "text": "I prefer quiet rooms",
                "device_id": "device-voice",
                "timestamp_ms": 123456,
                "turn_id": "session-1:7",
                "session_id": "session-1",
                "cognitive_trace_id": "trace-1",
            }
        ),
        turn_id="session-1:7",
        turn_number=7,
        session_id="session-1",
        cognitive_trace_id="trace-1",
        user_text="I prefer quiet rooms",
        assistant_text="Got it.",
        prompt_mode="LIVE_API",
    )

    assert live is not None
    assert live.turn_id == text.turn_id
    assert live.session_id == text.session_id
    assert live.cognitive_trace_id == text.cognitive_trace_id
    assert live.user_turn == text.user_turn
    assert live.assistant_turn["final_text"] == text.assistant_turn["final_text"]
    assert live.bus_topic == LIVE_TURN_COMPLETED_TOPIC


def test_partial_transcripts_are_ignored_before_classifier_writer_path() -> None:
    record = {
        "event_type": "transcript.delta",
        "session_id": "session-1",
        "partial": True,
        "transcript": "I prefer qui",
    }
    result = build_live_section_update_input(record)

    assert is_live_turn_complete_record(record) is False
    assert result.ignored is True
    assert result.input_data is None
    assert result.reason == "partial_live_record"
    assert result.diagnostics[0]["code"] == "partial_live_record"


def test_non_final_live_records_are_ignored() -> None:
    result = build_live_section_update_input(
        {
            "event_type": "transcript.created",
            "session_id": "session-1",
            "transcript": "I prefer quiet rooms",
        }
    )

    assert result.ignored is True
    assert result.input_data is None
    assert result.reason == "live_record_not_final"


def test_missing_device_or_timestamp_returns_explicit_diagnostics() -> None:
    result = build_live_section_update_input(
        {
            "event_type": "turn.completed",
            "session_id": "session-1",
            "turn_id": "session-1:8",
            "final_transcript": "Please remember this",
            "assistant_text": "I will.",
        }
    )

    assert result.input_data is not None
    assert result.input_data.user_turn["device_id"] == ""
    assert result.input_data.user_turn["timestamp_ms"] == 0
    assert {item["code"] for item in result.diagnostics} == {
        "missing_device_id",
        "missing_timestamp_ms",
    }
    assert result.input_data.scenario_context["diagnostics"] == result.diagnostics
