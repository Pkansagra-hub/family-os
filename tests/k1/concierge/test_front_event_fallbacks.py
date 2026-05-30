"""Front event-mode fallback regressions."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k1.bus.envelope.envelope import Envelope
from k1.concierge.actors.front import front_handler
from k1.concierge.bus.topics import TOPIC_FINAL_RESPONSE, TOPIC_TASK_RESUME
from k1.concierge.prompt.mode import PromptMode
from k1.concierge.react.loop import ReactResult


class _RecordingBus:
    def __init__(self) -> None:
        self.published: list[Envelope] = []

    def publish(self, envelope: Envelope) -> None:
        self.published.append(envelope)


def _env(topic: str, payload: dict[str, Any]) -> Envelope:
    return Envelope(topic=topic, payload=json.dumps(payload).encode("utf-8"))


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
        react=SimpleNamespace(
            front_degenerate_fallback="Let me think about that for a moment.",
            front_budget_fallback="Let me get back to you on that.",
        ),
    )


def _prompt_context() -> Any:
    return SimpleNamespace(
        system_prompt="event system prompt",
        messages=[],
        tools=[],
        max_iterations=2,
        affect_band="calm",
    )


def _final_text(bus: _RecordingBus) -> str:
    final_events = [event for event in bus.published if event.topic == TOPIC_FINAL_RESPONSE]
    assert len(final_events) == 1
    payload = json.loads(final_events[0].payload)
    return payload["text"]


class _SuspendedTaskState:
    def get_all(self) -> list[dict[str, Any]]:
        return [
            {
                "task_id": "task-1",
                "status": "SUSPENDED",
                "action": "add task to Riley to clean her bedroom",
                "pending_hil_data": {
                    "hil_type": "clarification",
                    "pending_hil_id": "hil-1",
                    "question": "What title should I use?",
                    "legacy_bridge": True,
                },
            }
        ]


class _SuspendedSessionState:
    def get_section(self, name: str) -> Any:
        if name == "task_state":
            return _SuspendedTaskState()
        return None


@pytest.mark.asyncio
async def test_hitl_relay_passes_through_llm_text() -> None:
    bus = _RecordingBus()
    env = _env(
        "k1.hil.request.v1",
        {
            "hil_type": "clarification",
            "question": "Should I use Riley's regular bedtime?",
            "options": [],
        },
    )

    with (
        patch("k1.concierge.actors.front.determine_mode", return_value=PromptMode.HITL_RELAY),
        patch("k1.concierge.actors.front.compute_affect_band", return_value="calm"),
        patch("k1.concierge.actors.front.get_config", return_value=_mock_front_config()),
        patch("k1.concierge.actors.front._write_runtime_prompt_dump"),
        patch("k1.concierge.actors.front.DynamicPromptBuilder") as mock_builder,
        patch("k1.concierge.actors.front.react_loop", new_callable=AsyncMock) as react_loop,
    ):
        mock_builder.return_value.build.return_value = _prompt_context()
        react_loop.return_value = ReactResult(
            status="complete",
            text="Hey -- quick check: should I use Riley's regular bedtime?",
            dispatched_tasks=[],
        )

        await front_handler(
            envelope=env,
            model=AsyncMock(),
            ss=None,
            bus=bus,  # type: ignore[arg-type]
            tool_dispatcher=MagicMock(),
            all_tool_schemas=[],
            fsm_state="CLARIFYING_WORKER",
        )

    assert _final_text(bus) == "Hey -- quick check: should I use Riley's regular bedtime?"


@pytest.mark.asyncio
async def test_hitl_relay_falls_back_to_back_question_when_front_llm_empty() -> None:
    """When Front LLM returns the deterministic fallback (or empty), we forward
    the Back-LLM-generated hil_question verbatim instead of leaking the kernel
    fallback string to the user."""
    bus = _RecordingBus()
    env = _env(
        "k1.hil.request.v1",
        {
            "hil_type": "clarification",
            "question": "Should I use Riley's regular bedtime?",
            "options": [],
        },
    )

    with (
        patch("k1.concierge.actors.front.determine_mode", return_value=PromptMode.HITL_RELAY),
        patch("k1.concierge.actors.front.compute_affect_band", return_value="calm"),
        patch("k1.concierge.actors.front.get_config", return_value=_mock_front_config()),
        patch("k1.concierge.actors.front._write_runtime_prompt_dump"),
        patch("k1.concierge.actors.front.DynamicPromptBuilder") as mock_builder,
        patch("k1.concierge.actors.front.react_loop", new_callable=AsyncMock) as react_loop,
    ):
        mock_builder.return_value.build.return_value = _prompt_context()
        react_loop.return_value = ReactResult(
            status="complete",
            text="Let me think about that for a moment.",
            dispatched_tasks=[],
        )

        await front_handler(
            envelope=env,
            model=AsyncMock(),
            ss=None,
            bus=bus,  # type: ignore[arg-type]
            tool_dispatcher=MagicMock(),
            all_tool_schemas=[],
            fsm_state="CLARIFYING_WORKER",
        )

    assert _final_text(bus) == "Should I use Riley's regular bedtime?"


@pytest.mark.asyncio
async def test_weave_passes_through_llm_text() -> None:
    bus = _RecordingBus()
    env = _env(
        "k1.orchestration.async_results_ready.v1",
        {
            "results": [
                {
                    "result": {
                        "task_id": "task-1",
                        "action": "add a task for Riley to clean her bedroom",
                        "final_answer": (
                            "I hit an error while trying to execute the task because "
                            "WriteContext trace_id failed validation."
                        ),
                    }
                }
            ]
        },
    )

    with (
        patch("k1.concierge.actors.front.determine_mode", return_value=PromptMode.WEAVE),
        patch("k1.concierge.actors.front.compute_affect_band", return_value="calm"),
        patch("k1.concierge.actors.front.get_config", return_value=_mock_front_config()),
        patch("k1.concierge.actors.front._write_runtime_prompt_dump"),
        patch("k1.concierge.actors.front.DynamicPromptBuilder") as mock_builder,
        patch("k1.concierge.actors.front.react_loop", new_callable=AsyncMock) as react_loop,
    ):
        mock_builder.return_value.build.return_value = _prompt_context()
        react_loop.return_value = ReactResult(
            status="complete",
            text="Quick heads up -- I ran into a snag with that bedroom task.",
            dispatched_tasks=[],
        )

        await front_handler(
            envelope=env,
            model=AsyncMock(),
            ss=None,
            bus=bus,  # type: ignore[arg-type]
            tool_dispatcher=MagicMock(),
            all_tool_schemas=[],
            fsm_state="COMPANIONING",
        )

    text = _final_text(bus)
    assert text == "Quick heads up -- I ran into a snag with that bedroom task."


@pytest.mark.asyncio
async def test_weave_suppresses_kernel_fallback_string() -> None:
    """Mandate: kernel-canned fallback strings must NEVER be published."""
    bus = _RecordingBus()
    env = _env(
        "k1.orchestration.async_results_ready.v1",
        {"results": [{"result": {"task_id": "t1", "final_answer": "done"}}]},
    )

    with (
        patch("k1.concierge.actors.front.determine_mode", return_value=PromptMode.WEAVE),
        patch("k1.concierge.actors.front.compute_affect_band", return_value="calm"),
        patch("k1.concierge.actors.front.get_config", return_value=_mock_front_config()),
        patch("k1.concierge.actors.front._write_runtime_prompt_dump"),
        patch("k1.concierge.actors.front.DynamicPromptBuilder") as mock_builder,
        patch("k1.concierge.actors.front.react_loop", new_callable=AsyncMock) as react_loop,
    ):
        mock_builder.return_value.build.return_value = _prompt_context()
        react_loop.return_value = ReactResult(
            status="complete",
            text="Let me think about that for a moment.",
            dispatched_tasks=[],
        )

        await front_handler(
            envelope=env,
            model=AsyncMock(),
            ss=None,
            bus=bus,  # type: ignore[arg-type]
            tool_dispatcher=MagicMock(),
            all_tool_schemas=[],
            fsm_state="COMPANIONING",
        )

    # No response.final must be published when the LLM produced only the
    # kernel-canned fallback string. Downstream chain will deliver the
    # real LLM-authored response.
    final_events = [e for e in bus.published if e.topic == "k1.session.response.final.v1"]
    assert final_events == []


@pytest.mark.asyncio
async def test_hitl_resolve_passes_through_llm_text() -> None:
    bus = _RecordingBus()
    env = _env("k1.session.user.input.v1", {"text": "approve"})

    with (
        patch("k1.concierge.actors.front.determine_mode", return_value=PromptMode.HITL_RESOLVE),
        patch("k1.concierge.actors.front.compute_affect_band", return_value="calm"),
        patch("k1.concierge.actors.front.get_config", return_value=_mock_front_config()),
        patch("k1.concierge.actors.front._write_runtime_prompt_dump"),
        patch("k1.concierge.actors.front.DynamicPromptBuilder") as mock_builder,
        patch("k1.concierge.actors.front.react_loop", new_callable=AsyncMock) as react_loop,
    ):
        mock_builder.return_value.build.return_value = _prompt_context()
        react_loop.return_value = ReactResult(
            status="complete",
            text="Done! Riley has a new task to clean her bedroom.",
            dispatched_tasks=[],
        )

        await front_handler(
            envelope=env,
            model=AsyncMock(),
            ss=_SuspendedSessionState(),
            bus=bus,  # type: ignore[arg-type]
            tool_dispatcher=MagicMock(),
            all_tool_schemas=[],
            fsm_state="CLARIFYING_WORKER",
        )

    assert _final_text(bus) == "Done! Riley has a new task to clean her bedroom."
    assert [event.topic for event in bus.published].count(TOPIC_TASK_RESUME) == 1
