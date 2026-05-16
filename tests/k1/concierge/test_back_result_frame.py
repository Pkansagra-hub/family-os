"""M2 typed Back result frame tests."""

from __future__ import annotations

import json
from typing import Any

from k1.bus.envelope.envelope import Envelope
from k1.concierge.actors.back import _emit_back_result
from k1.concierge.actors.frames import BackResultFrame
from k1.concierge.react.loop import ReactResult


class _RecordingBus:
    def __init__(self) -> None:
        self.published: list[Any] = []

    def publish(self, envelope: Any) -> None:
        self.published.append(envelope)


def _payload(envelope: Any) -> dict[str, Any]:
    return json.loads(envelope.payload.decode("utf-8"))


def test_back_result_frame_round_trip_prefers_typed_facts() -> None:
    frame = BackResultFrame(
        task_id="task-1",
        facts=[{"title": "Hotel booked", "url": "https://example.test"}],
        artifacts=[{"summary": "Confirmation saved"}],
        confidence=0.91,
        raw_final_answer="Worker prose for compatibility only.",
    )

    round_trip = BackResultFrame.from_dict(frame.to_dict())

    assert round_trip.task_id == "task-1"
    assert "Hotel booked" in round_trip.summary_text()
    assert "Confirmation saved" in round_trip.summary_text()
    assert round_trip.raw_final_answer == "Worker prose for compatibility only."


def test_back_result_frame_preserves_semantic_guidance() -> None:
    frame = BackResultFrame(
        task_id="task-1",
        facts=[
            {
                "title": "Appointment scheduled",
                "semantic": {
                    "authority": {
                        "guidance_scope": "general",
                        "authority_source": "provider",
                        "requires_external_authority": True,
                        "boundary_note": "Follow the provider's specific instructions.",
                    },
                    "future_weave": {"triggers": ["day before"], "prep_notes": ["bring ID"]},
                },
            }
        ],
        presentation_guidance="Lead with the scheduled appointment details.",
    )

    round_trip = BackResultFrame.from_dict(frame.to_dict())
    guidance = round_trip.semantic_guidance_text()

    assert round_trip.semantic_context == {}
    assert "Lead with the scheduled appointment details" in guidance
    assert "Authority boundary" in guidance
    assert "external_authority_required=True" in guidance
    assert "day before" in guidance


def test_emit_back_result_includes_frame_and_keeps_legacy_fields() -> None:
    bus = _RecordingBus()
    envelope = Envelope(
        topic="k1.orchestration.task.dispatch.v1",
        envelope_id=7,
        payload=json.dumps({"action": "book hotel"}).encode("utf-8"),
    )
    result = ReactResult(
        status="complete",
        data={
            "final_answer": "Booked the hotel.",
            "results": [{"title": "Hotel booked", "url": "https://example.test"}],
            "artifacts_created": [{"summary": "Confirmation saved"}],
            "semantic_context": {
                "authority": {
                    "guidance_scope": "general",
                    "requires_external_authority": True,
                }
            },
            "presentation_guidance": "Lead with the booking confirmation.",
            "confidence": 0.95,
            "suggested_next_action": "Tell the user the confirmation is saved.",
        },
    )

    _emit_back_result(
        bus,
        envelope,
        "task-1",
        result,
        tool_call_summaries=[{"tool": "booking.create", "status": "ok"}],
    )

    out = _payload(bus.published[0])
    assert out["final_answer"] == "Booked the hotel."
    assert out["results"] == [{"title": "Hotel booked", "url": "https://example.test"}]
    assert out["frame"]["_frame_type"] == "back_result"
    assert out["frame"]["facts"] == out["results"]
    assert out["frame"]["artifacts"] == out["artifacts_created"]
    assert out["frame"]["raw_final_answer"] == "Booked the hotel."
    assert out["semantic_context"] == {
        "authority": {"guidance_scope": "general", "requires_external_authority": True}
    }
    assert out["frame"]["presentation_guidance"] == "Lead with the booking confirmation."
    assert out["frame"]["tool_call_summaries"] == [{"tool": "booking.create", "status": "ok"}]


def test_emit_back_result_synthesizes_trace_when_source_is_empty() -> None:
    bus = _RecordingBus()
    envelope = Envelope(
        topic="k1.orchestration.task.dispatch.v1",
        envelope_id=7,
        payload=json.dumps({"action": "book hotel"}).encode("utf-8"),
    )
    result = ReactResult(status="complete", data={"final_answer": "Booked the hotel."})

    _emit_back_result(bus, envelope, "task-1", result)

    assert bus.published[0].cognitive_trace_id.startswith("back-")
