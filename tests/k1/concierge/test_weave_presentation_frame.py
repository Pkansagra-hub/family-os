"""M2 WeavePresentationFrame tests."""

from __future__ import annotations

from typing import Any

from k1.concierge.actors.frames import BackResultFrame, WeavePresentationFrame


class _Narrative:
    def get_active_thread_name(self) -> str:
        return "calendar planning"


class _Session:
    def __init__(self, affect: dict[str, Any] | None = None) -> None:
        self._affect = affect or {}

    def get_section(self, name: str) -> Any:
        if name == "narrative_active":
            return _Narrative()
        if name == "affective_now":
            return self._affect
        return None


def test_weave_presentation_frame_preserves_digest_payload() -> None:
    frame = WeavePresentationFrame.from_payload_and_pending(
        {
            "results": [
                {
                    "is_digest": True,
                    "digest_count": 3,
                    "digest_summary": "Three routine tasks completed.",
                }
            ]
        },
        pending=None,
        ss=_Session(),
    )

    assert frame.result_count == 3
    assert frame.results_summary == "Three routine tasks completed."
    assert frame.presentation_mode == "digest"
    assert frame.current_thread == "calendar planning"


def test_weave_presentation_frame_builds_summary_from_back_frames() -> None:
    back_frame = BackResultFrame(
        task_id="task-1",
        facts=[
            {
                "title": "Reminder set",
                "snippet": "Tomorrow at 9 AM",
                "semantic": {
                    "authority": {
                        "guidance_scope": "user_supplied",
                        "authority_source": "user",
                    }
                },
            }
        ],
        suggested_next_action="Mention the reminder time.",
    )
    frame = WeavePresentationFrame.from_payload_and_pending(
        {},
        pending=[
            {
                "result": {
                    "task_id": "task-1",
                    "action": "set reminder",
                    "urgency": "critical",
                    "frame": back_frame.to_dict(),
                }
            }
        ],
        ss=_Session({"valence": 0.7, "band": "positive"}),
    )

    assert frame.result_count == 1
    assert frame.source_task_ids == ["task-1"]
    assert "Reminder set" in frame.results_summary
    assert "Tomorrow at 9 AM" in frame.results_summary
    assert "Suggested next action" in frame.results_summary
    assert frame.urgency_label.startswith("URGENT")
    assert "positive mood" in frame.emotional_context
    assert "Authority boundary" in frame.semantic_guidance
    assert "user_supplied" in frame.semantic_guidance
