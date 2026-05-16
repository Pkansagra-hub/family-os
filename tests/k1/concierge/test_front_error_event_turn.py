"""Front ERROR event-turn prompt contract tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k1.bus.envelope.envelope import Envelope
from k1.concierge.actors.front import (
    _build_event_turn_text,
    _extract_scenario_data,
    front_handler,
)
from k1.concierge.llm.types import ModelMessage
from k1.concierge.prompt.mode import PromptMode
from k1.concierge.react.loop import ReactResult


class _TaskState:
    def get_by_id(self, task_id: str) -> dict[str, Any]:
        assert task_id == "task-1"
        return {"task_id": task_id, "action": "add the green token"}


class _SessionState:
    def get_section(self, name: str) -> Any:
        if name == "task_state":
            return _TaskState()
        return None


class _RecordingBus:
    def __init__(self) -> None:
        self.published: list[Envelope] = []

    def publish(self, envelope: Envelope) -> None:
        self.published.append(envelope)


def _env(payload: dict[str, Any]) -> Envelope:
    return Envelope(
        topic="k1.orchestration.task.failed.v1",
        payload=json.dumps(payload).encode("utf-8"),
    )


def _mock_front_config() -> Any:
    return SimpleNamespace(
        actors=SimpleNamespace(
            front=SimpleNamespace(
                default_fsm_state="LISTENING",
                default_affect_confidence=0.5,
                default_tier="LOW",
                history_window_fallback=12,
            )
        ),
        react=SimpleNamespace(front_degenerate_fallback="fallback"),
    )


def test_error_scenario_uses_task_state_action_when_failure_payload_has_only_id() -> None:
    out = _extract_scenario_data(
        PromptMode.ERROR,
        _env({"task_id": "task-1", "reason": "orchestrator_failed"}),
        _SessionState(),
    )

    assert out["task_id"] == "task-1"
    assert out["task_description"] == "add the green token"
    assert out["failure_reason"] == "orchestrator_failed"


def test_error_event_turn_gives_model_current_action_without_internal_codes() -> None:
    text = _build_event_turn_text(
        PromptMode.ERROR,
        {
            "task_description": "add the green token",
            "failure_reason": "orchestrator_failed",
            "error_code": "E_ORCH",
            "partial_results": [],
        },
    )

    assert "background task just failed" in text
    assert "add the green token" in text
    assert "Offer to try again" in text
    assert "orchestrator_failed" not in text
    assert "E_ORCH" not in text


@pytest.mark.asyncio
async def test_front_handler_appends_error_event_turn_to_react_messages() -> None:
    env = _env({"task_id": "task-1", "reason": "orchestrator_failed"})
    context = SimpleNamespace(
        system_prompt="error system prompt",
        messages=[ModelMessage(role="assistant", content="I'm adding that task now.")],
        tools=[],
        max_iterations=2,
        affect_band="calm",
    )
    result = ReactResult(status="complete", text="That did not go through.", dispatched_tasks=[])

    with (
        patch("k1.concierge.actors.front.determine_mode", return_value=PromptMode.ERROR),
        patch("k1.concierge.actors.front.compute_affect_band", return_value="calm"),
        patch("k1.concierge.actors.front.get_config", return_value=_mock_front_config()),
        patch("k1.concierge.actors.front._write_runtime_prompt_dump"),
        patch("k1.concierge.actors.front.DynamicPromptBuilder") as mock_builder,
        patch("k1.concierge.actors.front.react_loop", new_callable=AsyncMock) as react_loop,
    ):
        mock_builder.return_value.build.return_value = context
        react_loop.return_value = result

        await front_handler(
            envelope=env,
            model=AsyncMock(),
            ss=_SessionState(),
            bus=_RecordingBus(),  # type: ignore[arg-type]
            tool_dispatcher=MagicMock(),
            all_tool_schemas=[],
            fsm_state="COMPANIONING",
        )

    sent_messages = react_loop.call_args.kwargs["messages"]
    assert sent_messages[-1].role == "user"
    assert "background task just failed" in sent_messages[-1].content
    assert "add the green token" in sent_messages[-1].content
