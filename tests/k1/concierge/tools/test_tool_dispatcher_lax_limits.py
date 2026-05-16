"""Regression coverage for temporarily lax Front/Back tool-call limits."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import k1.concierge.tools.dispatcher as dispatcher_mod
from k1.concierge.config import reset_config
from k1.concierge.llm.types import ToolCallResult, ToolSchema
from k1.concierge.tools.dispatcher import (
    ToolDispatcher,
    create_back_dispatcher,
    create_front_dispatcher,
)
from k1.concierge.tools.implementations import ToolContext
from k1.concierge.tools.result_protocol import ToolResult


def _ctx() -> ToolContext:
    return ToolContext(session_manager=MagicMock())


def test_front_and_back_dispatchers_start_with_lax_400_budget() -> None:
    reset_config()
    front = create_front_dispatcher(tier="simple", ctx=_ctx())
    back = create_back_dispatcher(tier="plan", ctx=_ctx())

    assert front.budget_remaining == 400
    assert back.budget_remaining == 400


@pytest.mark.asyncio
async def test_repeated_front_cognitive_tool_calls_are_not_rejected_after_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_execute(name, args, ctx):  # type: ignore[no-untyped-def]
        return ToolResult(tool_name=name, status="ok", data={"args": args})

    reset_config()
    monkeypatch.setattr(dispatcher_mod, "execute_tool", fake_execute)
    schema = ToolSchema(
        name="update_scoreboard",
        description="fake scoreboard writer",
        parameters={"type": "object", "properties": {}},
    )
    dispatcher = ToolDispatcher(
        actor="front",
        allowlist={"update_scoreboard"},
        tool_schemas={"update_scoreboard": schema},
        ctx=_ctx(),
        tier="simple",
    )

    for index in range(3):
        result = await dispatcher.dispatch(
            ToolCallResult(
                id=f"call-{index}",
                name="update_scoreboard",
                arguments={"question": f"q{index}"},
            )
        )
        assert result.status == "ok"

    assert dispatcher.call_count == 3
    assert dispatcher.budget_remaining == 397


@pytest.mark.asyncio
async def test_back_submit_complete_after_recall_memory_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_execute(name, args, ctx):  # type: ignore[no-untyped-def]
        return ToolResult(tool_name=name, status="ok", data={"args": args})

    reset_config()
    monkeypatch.setattr(dispatcher_mod, "execute_tool", fake_execute)
    schemas = {
        "recall_memory": ToolSchema(
            name="recall_memory",
            description="fake memory reader",
            parameters={"type": "object", "properties": {}},
        ),
        "submit_result": ToolSchema(
            name="submit_result",
            description="fake submit",
            parameters={"type": "object", "properties": {}},
        ),
    }
    dispatcher = ToolDispatcher(
        actor="back",
        allowlist=set(schemas),
        tool_schemas=schemas,
        ctx=_ctx(),
        tier="simple",
    )

    recall = await dispatcher.dispatch(
        ToolCallResult(
            id="recall-1",
            name="recall_memory",
            arguments={"query": "known prep notes"},
        )
    )
    submit = await dispatcher.dispatch(
        ToolCallResult(
            id="submit-1",
            name="submit_result",
            arguments={"result_type": "complete", "final_answer": "memory answer"},
        )
    )

    assert recall.status == "ok"
    assert submit.status == "ok"
    assert dispatcher.call_count == 2
