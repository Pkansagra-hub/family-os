"""Front capability routing guard regressions."""

from __future__ import annotations

import pytest

from k1.concierge.llm.types import ModelMessage, ToolSchema
from k1.concierge.react.loop import react_loop
from k1.concierge.tools.result_protocol import ToolResult
from tests.k1.concierge.conftest import make_hub_text_response, make_hub_tool_response


class _ScriptedModel:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def execute(self, request):
        self.calls += 1
        if not self.responses:
            return make_hub_text_response("done")
        return self.responses.pop(0)


class _ToolDispatcher:
    def __init__(self, data: dict | None = None) -> None:
        self.calls: list[str] = []
        self.data = data or {"memories": [], "count": 0}

    async def dispatch(self, tc) -> ToolResult:
        self.calls.append(tc.name)
        return ToolResult(
            tool_name=tc.name,
            status="ok",
            data=self.data,
        )


async def _never_cancel() -> bool:
    return False


_TOOL_SCHEMAS = [
    ToolSchema(
        name="recall_memory",
        description="recall",
        parameters={"type": "object"},
    ),
    ToolSchema(
        name="update_beliefs",
        description="beliefs",
        parameters={"type": "object"},
    ),
    ToolSchema(
        name="dispatch_task",
        description="dispatch",
        parameters={"type": "object"},
    ),
]


@pytest.mark.asyncio
async def test_front_empty_context_read_routes_to_worker_without_domain_terms() -> None:
    model = _ScriptedModel(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "recall_memory",
                        "arguments": {"query": "current system record"},
                    }
                ]
            )
        ]
    )
    dispatcher = _ToolDispatcher()

    result = await react_loop(
        actor="front",
        system_prompt="system",
        messages=[ModelMessage(role="user", content="check whether the record was updated")],
        tools=_TOOL_SCHEMAS,
        max_iterations=4,
        model=model,
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="trace-chores",
        scenario="standard",
    )

    assert result.status == "complete"
    assert model.calls == 1
    assert dispatcher.calls == ["recall_memory"]
    assert result.text == ""
    assert len(result.dispatched_tasks) == 1
    task = result.dispatched_tasks[0]
    assert task["_policy_route"] == "context_read_no_evidence"
    assert task["intents"] == [
        {
            "action": "check whether the record was updated",
            "params": {},
        }
    ]


@pytest.mark.asyncio
async def test_front_context_read_with_evidence_can_answer_without_dispatch() -> None:
    model = _ScriptedModel(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "recall_memory",
                        "arguments": {"query": "stored preference"},
                    }
                ]
            ),
            make_hub_text_response("The stored preference is morning delivery."),
        ]
    )
    dispatcher = _ToolDispatcher(
        data={"memories": [{"text": "prefers morning delivery"}], "count": 1}
    )

    result = await react_loop(
        actor="front",
        system_prompt="system",
        messages=[ModelMessage(role="user", content="what delivery timing do they prefer?")],
        tools=_TOOL_SCHEMAS,
        max_iterations=4,
        model=model,
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="trace-chores",
        scenario="standard",
    )

    assert result.status == "complete"
    assert dispatcher.calls == ["recall_memory"]
    assert result.text == "The stored preference is morning delivery."
    assert result.dispatched_tasks == []


@pytest.mark.asyncio
async def test_front_historical_memory_lookup_can_answer_without_dispatch() -> None:
    model = _ScriptedModel([make_hub_text_response("The stored routine is the short one.")])
    dispatcher = _ToolDispatcher()
    seen_text: list[str] = []

    result = await react_loop(
        actor="front",
        system_prompt="system",
        messages=[ModelMessage(role="user", content="what routine was stored for this account?")],
        tools=_TOOL_SCHEMAS,
        max_iterations=4,
        model=model,
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=seen_text.append,
        cancellation_check=_never_cancel,
        trace_id="trace-memory",
        scenario="standard",
    )

    assert result.status == "complete"
    assert result.text == "The stored routine is the short one."
    assert result.dispatched_tasks == []
    assert seen_text == []
