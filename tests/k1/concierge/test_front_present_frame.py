"""M2 Front PRESENT typed frame extraction tests."""

from __future__ import annotations

import json
from typing import Any

from k1.bus.envelope.envelope import Envelope
from k1.concierge.actors.frames import BackResultFrame
from k1.concierge.actors.front import _extract_scenario_data
from k1.concierge.prompt.mode import PromptMode


def _env(payload: dict[str, Any]) -> Envelope:
    return Envelope(
        topic="k1.orchestration.task.complete.v1",
        payload=json.dumps(payload).encode("utf-8"),
    )


def test_present_extracts_typed_frame_fields_before_legacy_answer() -> None:
    frame = BackResultFrame(
        task_id="task-1",
        facts=[{"title": "Hotel booked", "url": "https://example.test"}],
        artifacts=[
            {
                "summary": "Confirmation saved",
                "semantic": {
                    "authority": {
                        "guidance_scope": "general",
                        "requires_external_authority": True,
                        "boundary_note": "Use the source instructions for specifics.",
                    }
                },
            }
        ],
        confidence=0.88,
        suggested_next_action="Mention check-in time.",
        raw_final_answer="Raw worker answer should be fallback only.",
    )

    out = _extract_scenario_data(
        PromptMode.PRESENT,
        _env(
            {
                "action": "book hotel",
                "final_answer": "Legacy final answer.",
                "frame": frame.to_dict(),
            }
        ),
        ss=None,
    )

    assert out["task_description"] == "book hotel"
    assert "Hotel booked" in out["task_facts"]
    assert "Confirmation saved" in out["task_artifacts"]
    assert out["task_confidence"] == 0.88
    assert out["suggested_next_action"] == "Mention check-in time."
    assert "Authority boundary" in out["semantic_guidance"]
    assert "source instructions" in out["semantic_guidance"]
    assert "Legacy final answer" not in out["task_result_summary"]


def test_present_legacy_payload_still_populates_legacy_fields() -> None:
    out = _extract_scenario_data(
        PromptMode.PRESENT,
        _env(
            {
                "action": "search restaurants",
                "final_answer": "Found three restaurants.",
                "results": ["A", "B", "C"],
                "artifacts_created": ["list saved"],
            }
        ),
        ss=None,
    )

    assert out["task_result_summary"] == "Found three restaurants."
    assert out["semantic_guidance"] == ""
    assert out["results"] == ["A", "B", "C"]
    assert out["artifacts"] == ["list saved"]
