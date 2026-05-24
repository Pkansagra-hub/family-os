"""Front ReAct dispatch termination regressions."""

from __future__ import annotations

import pytest

from k1.concierge.llm.types import ModelMessage, ToolSchema
from k1.concierge.react.loop import react_loop
from k1.concierge.tools.result_protocol import ToolResult
from tests.k1.concierge.conftest import make_hub_text_response, make_hub_tool_response


class _DispatchingTool:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def dispatch(self, tc) -> ToolResult:
        self.calls.append(tc.name)
        return ToolResult(
            tool_name=tc.name,
            status="ok",
            data={
                "task_id": "task-1",
                "_dispatch": {
                    "task_id": "task-1",
                    "intents": tc.arguments.get("intents", []),
                    "tier": "LOW",
                },
            },
        )


class _Model:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request):
        self.calls += 1
        if self.calls == 1:
            return make_hub_tool_response(
                [
                    {
                        "name": "dispatch_task",
                        "arguments": {
                            "intents": [
                                {
                                    "action": "add task to Riley to clean her bedroom",
                                    "params": {"child_name": "Riley", "task": "clean her bedroom"},
                                    "domain": "family",
                                }
                            ]
                        },
                    }
                ]
            )
        return make_hub_text_response("This should not be needed.")


class _ScriptedModel:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def execute(self, request):
        self.calls += 1
        if not self.responses:
            return make_hub_text_response("done")
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_front_stops_after_successful_dispatch_task() -> None:
    model = _Model()
    dispatcher = _DispatchingTool()

    async def never_cancel() -> bool:
        return False

    result = await react_loop(
        actor="front",
        system_prompt="system",
        messages=[],
        tools=[
            ToolSchema(
                name="dispatch_task",
                description="dispatch work",
                parameters={"type": "object"},
            )
        ],
        max_iterations=4,
        model=model,
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=never_cancel,
        trace_id="trace-1",
        scenario="standard",
    )

    assert result.status == "complete"
    assert model.calls == 1
    assert dispatcher.calls == ["dispatch_task"]
    assert len(result.dispatched_tasks) == 1
    assert result.dispatched_tasks[0]["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_front_rejects_vague_advisory_dispatch_and_answers_directly() -> None:
    model = _ScriptedModel(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "dispatch_task",
                        "arguments": {
                            "intents": [
                                {
                                    "action": "prepare lunch",
                                    "params": {},
                                    "domain": "cooking",
                                }
                            ]
                        },
                    }
                ],
                text="I can definitely help you think through lunch ideas.",
            ),
            make_hub_text_response("Try a gentle lentil bowl with hidden veg."),
        ]
    )
    dispatcher = _DispatchingTool()

    async def never_cancel() -> bool:
        return False

    result = await react_loop(
        actor="front",
        system_prompt="system",
        messages=[
            ModelMessage(
                role="user",
                content="I was planning good food for family and I'm confused",
            )
        ],
        tools=[
            ToolSchema(
                name="dispatch_task",
                description="dispatch work",
                parameters={"type": "object"},
            )
        ],
        max_iterations=4,
        model=model,
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=never_cancel,
        trace_id="trace-food",
        scenario="standard",
    )

    assert result.status == "complete"
    assert dispatcher.calls == []
    assert result.dispatched_tasks == []
    assert result.text == "Try a gentle lentil bowl with hidden veg."


@pytest.mark.asyncio
async def test_front_allows_explicit_shopping_side_effect_dispatch() -> None:
    model = _ScriptedModel(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "dispatch_task",
                        "arguments": {
                            "intents": [
                                {
                                    "action": "add lentils to the shopping list",
                                    "params": {"item": "lentils"},
                                    "domain": "shopping",
                                }
                            ]
                        },
                    }
                ],
            )
        ]
    )
    dispatcher = _DispatchingTool()

    async def never_cancel() -> bool:
        return False

    result = await react_loop(
        actor="front",
        system_prompt="system",
        messages=[],
        tools=[
            ToolSchema(
                name="dispatch_task",
                description="dispatch work",
                parameters={"type": "object"},
            )
        ],
        max_iterations=4,
        model=model,
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=never_cancel,
        trace_id="trace-shopping",
        scenario="standard",
    )

    assert result.status == "complete"
    assert dispatcher.calls == ["dispatch_task"]
    assert len(result.dispatched_tasks) == 1
    assert result.dispatched_tasks[0]["task_id"] == "task-1"
