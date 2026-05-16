"""M2 Front WEAVE typed presentation frame tests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k1.bus.envelope.envelope import Envelope
from k1.concierge.actors.frames import BackResultFrame
from k1.concierge.actors.front import _extract_scenario_data, front_handler
from k1.concierge.prompt.mode import PromptMode


class _RecordingBus:
    def __init__(self) -> None:
        self.published: list[Any] = []

    def publish(self, envelope: Any) -> None:
        self.published.append(envelope)


def _env(payload: dict[str, Any]) -> Envelope:
    return Envelope(
        topic="k1.orchestration.async_results_ready.v1",
        payload=json.dumps(payload).encode("utf-8"),
    )


def _mock_front_config() -> Any:
    cfg = type("Cfg", (), {})()
    actors = type("Actors", (), {})()
    front = type("Front", (), {})()
    front.default_affect_confidence = 0.5
    front.default_tier = "LOW"
    front.default_fsm_state = "IDLE"
    front.history_window_fallback = 10
    actors.front = front
    cfg.actors = actors
    return cfg


def test_weave_extracts_back_frame_summary_not_raw_worker_prose() -> None:
    frame = BackResultFrame(
        task_id="task-1",
        facts=[
            {
                "title": "Dentist booked",
                "snippet": "Tuesday at 3 PM",
                "semantic": {
                    "future_weave": {"triggers": ["morning of"], "prep_notes": ["bring forms"]}
                },
            }
        ],
        raw_final_answer="Raw worker prose should not drive weave.",
    )

    out = _extract_scenario_data(
        PromptMode.WEAVE,
        _env(
            {
                "results": [
                    {
                        "result": {
                            "task_id": "task-1",
                            "action": "book dentist",
                            "final_answer": "Legacy worker prose.",
                            "frame": frame.to_dict(),
                        }
                    }
                ]
            }
        ),
        ss=None,
    )

    assert out["result_count"] == 1
    assert "Dentist booked" in out["results_summary"]
    assert "Tuesday at 3 PM" in out["results_summary"]
    assert "Legacy worker prose" not in out["results_summary"]
    assert "morning of" in out["semantic_guidance"]
    assert "bring forms" in out["semantic_guidance"]
    assert out["source_task_ids"] == ["task-1"]


@pytest.mark.asyncio
async def test_front_handler_skips_weave_when_no_result_frame_or_summary() -> None:
    env = _env({"results": []})
    bus = _RecordingBus()

    with (
        patch("k1.concierge.actors.front.determine_mode", return_value=PromptMode.WEAVE),
        patch("k1.concierge.actors.front.get_config", return_value=_mock_front_config()),
        patch("k1.concierge.actors.front.compute_affect_band", return_value="calm"),
        patch("k1.concierge.actors.front.react_loop", new_callable=AsyncMock) as react_loop,
    ):
        result = await front_handler(
            envelope=env,
            model=AsyncMock(),
            ss=None,
            bus=bus,  # type: ignore[arg-type]
            tool_dispatcher=MagicMock(),
            all_tool_schemas=[],
        )

    assert result.status == "skipped"
    react_loop.assert_not_called()
    assert len(bus.published) == 1
    ack = json.loads(bus.published[0].payload.decode("utf-8"))
    assert ack["text"] == ""
    assert ack["is_ack"] is True
