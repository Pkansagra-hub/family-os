"""Normalize Live API final turn records into SectionUpdateInput."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.section_update.input_builder import build_section_update_input
from k1.concierge.section_update.types import SectionUpdateInput

LIVE_TURN_COMPLETED_TOPIC = "k1.live.turn.completed.v1"

_PARTIAL_MARKERS = (
    "partial",
    "delta",
    "stream",
    "streaming",
    "hypothesis",
)
_FINAL_EVENT_TYPES = frozenset(
    {
        "turn.completed",
        "turn_complete",
        "turn.completed.v1",
        "live.turn.completed",
        "response.done",
        "response.completed",
        "transcript.done",
        "transcription.completed",
        "input_audio_transcription.completed",
    }
)


@dataclass(frozen=True)
class LiveTurnNormalizationResult:
    """Result of normalizing a live event for section-update classification."""

    input_data: SectionUpdateInput | None
    ignored: bool = False
    reason: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def build_live_section_update_input(
    record: Mapping[str, Any],
    *,
    ss: Any | None = None,
    prompt_context: Mapping[str, Any] | None = None,
    constraints: Mapping[str, Any] | None = None,
) -> LiveTurnNormalizationResult:
    """Build SectionUpdateInput from a stable Live API final-turn record.

    Partial transcripts, deltas, and non-final records return ``ignored=True``
    and never reach the classifier/writer path.
    """

    payload = dict(record)
    if _is_partial_record(payload):
        return LiveTurnNormalizationResult(
            input_data=None,
            ignored=True,
            reason="partial_live_record",
            diagnostics=[{"code": "partial_live_record", "message": "ignored partial transcript"}],
        )
    if not _is_final_record(payload):
        return LiveTurnNormalizationResult(
            input_data=None,
            ignored=True,
            reason="live_record_not_final",
            diagnostics=[{"code": "live_record_not_final", "message": "final marker missing"}],
        )

    diagnostics: list[dict[str, Any]] = []
    session_id = _first_text(payload, "session_id", "conversation_id", "space_id")
    if not session_id:
        return LiveTurnNormalizationResult(
            input_data=None,
            ignored=True,
            reason="missing_session_id",
            diagnostics=[
                {"code": "missing_session_id", "message": "live final record lacks session_id"}
            ],
        )
    device_id = _first_text(payload, "device_id", "client_device_id", "source_device_id")
    if not device_id:
        diagnostics.append(
            {"code": "missing_device_id", "message": "live final record lacks device_id"}
        )
    timestamp_ms = _first_number(payload, "timestamp_ms", "event_timestamp_ms", "created_at_ms")
    if timestamp_ms is None:
        diagnostics.append(
            {"code": "missing_timestamp_ms", "message": "live final record lacks timestamp_ms"}
        )
        timestamp_ms = 0

    user_text = _first_text(
        payload,
        "user_text",
        "final_transcript",
        "input_transcript",
        "transcript",
        "text",
    )
    assistant_text = _first_text(
        payload,
        "assistant_text",
        "response_text",
        "final_response",
        "assistant_response",
    )
    turn_number = _optional_int(payload.get("turn_number"))
    turn_id = _first_text(payload, "turn_id")
    trace_id = _first_text(payload, "cognitive_trace_id", "trace_id", "request_id")
    envelope_payload = {
        "text": user_text,
        "device_id": device_id,
        "timestamp_ms": timestamp_ms,
        "turn_id": turn_id,
        "session_id": session_id,
        "cognitive_trace_id": trace_id,
        "event_type": _event_type(payload),
    }
    envelope = Envelope(
        topic=LIVE_TURN_COMPLETED_TOPIC,
        payload=json.dumps(envelope_payload, separators=(",", ":")).encode("utf-8"),
        payload_format=PayloadFormat.JSON,
        priority=Priority.INTERACTIVE,
        session_id=session_id,
        cognitive_trace_id=trace_id,
    )
    input_data = build_section_update_input(
        envelope=envelope,
        ss=ss,
        turn_id=turn_id or None,
        turn_number=turn_number,
        session_id=session_id,
        cognitive_trace_id=trace_id,
        user_text=user_text,
        assistant_text=assistant_text,
        prompt_mode="LIVE_API",
        fsm_state=str(payload.get("fsm_state", "") or ""),
        scenario_data={
            "source": "live_api",
            "event_type": _event_type(payload),
            "modality": str(payload.get("modality", "voice") or "voice"),
            "diagnostics": list(diagnostics),
        },
        prompt_context=prompt_context,
        constraints={"source": "live_api", **dict(constraints or {})},
    )
    return LiveTurnNormalizationResult(
        input_data=input_data,
        ignored=False,
        diagnostics=diagnostics,
    )


def normalize_live_turn_complete_record(
    record: Mapping[str, Any],
    *,
    ss: Any | None = None,
    prompt_context: Mapping[str, Any] | None = None,
    constraints: Mapping[str, Any] | None = None,
) -> LiveTurnNormalizationResult:
    """Normalize a Live API turn-complete record for section-update classification."""

    return build_live_section_update_input(
        record,
        ss=ss,
        prompt_context=prompt_context,
        constraints=constraints,
    )


def is_live_turn_complete_record(record: Mapping[str, Any]) -> bool:
    """Return True when a live record is stable enough for classifier input."""

    payload = dict(record)
    return not _is_partial_record(payload) and _is_final_record(payload)


def _is_partial_record(payload: Mapping[str, Any]) -> bool:
    if bool(payload.get("partial", False)) or bool(payload.get("is_partial", False)):
        return True
    if payload.get("is_final") is False or payload.get("final") is False:
        return True
    marker = " ".join(
        str(payload.get(key, "") or "").lower() for key in ("event_type", "type", "kind", "status")
    )
    return any(item in marker for item in _PARTIAL_MARKERS)


def _is_final_record(payload: Mapping[str, Any]) -> bool:
    if bool(payload.get("turn_complete", False)) or bool(payload.get("turn_completed", False)):
        return True
    if bool(payload.get("is_final", False)) or bool(payload.get("final", False)):
        return True
    event_type = _event_type(payload).lower()
    if event_type in _FINAL_EVENT_TYPES:
        return True
    status = str(payload.get("status", "") or "").lower()
    return status in {"complete", "completed", "done", "final"}


def _event_type(payload: Mapping[str, Any]) -> str:
    return _first_text(payload, "event_type", "type", "kind")


def _first_text(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            nested = _first_text(value, "text", "transcript", "final_text")
            if nested:
                return nested
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_number(payload: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "LIVE_TURN_COMPLETED_TOPIC",
    "LiveTurnNormalizationResult",
    "build_live_section_update_input",
    "normalize_live_turn_complete_record",
    "is_live_turn_complete_record",
]
