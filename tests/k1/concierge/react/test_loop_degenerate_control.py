"""M3 ReAct loop control and degenerate-loop coverage."""

from __future__ import annotations

import asyncio

import pytest

from k1.concierge.llm.types import ToolSchema
from k1.concierge.react.control import BackControlEvent
from k1.concierge.react.loop import react_loop
from k1.concierge.tools.result_protocol import ToolResult
from tests.k1.concierge.conftest import (
    make_hub_empty_response,
    make_hub_text_response,
    make_hub_tool_response,
)


def _submit_tool() -> ToolSchema:
    return ToolSchema(
        name="submit_result",
        description="submit",
        parameters={"type": "object", "properties": {}},
    )


def _tool(name: str) -> ToolSchema:
    return ToolSchema(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {}},
    )


async def _never_cancel() -> bool:
    return False


class _SubmitDispatcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def dispatch(self, tool_call):  # type: ignore[no-untyped-def]
        self.calls.append(tool_call.name)
        return ToolResult(tool_name=tool_call.name, status="ok", data={"ok": True})


@pytest.mark.asyncio
async def test_control_queue_parameter_update_reaches_next_iteration() -> None:
    queue: asyncio.Queue[BackControlEvent] = asyncio.Queue()

    class Model:
        def __init__(self) -> None:
            self.requests = []

        async def execute(self, request):  # type: ignore[no-untyped-def]
            self.requests.append(request)
            if len(self.requests) == 1:
                queue.put_nowait(
                    BackControlEvent(
                        event_type="parameter_update",
                        task_id="task-1",
                        payload={"modifications": {"city": "Kyoto"}},
                    )
                )
                return make_hub_text_response("thinking")
            return make_hub_tool_response(
                [
                    {
                        "id": "submit-1",
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "complete",
                            "final_answer": "done",
                        },
                    }
                ]
            )

    model = Model()
    dispatcher = _SubmitDispatcher()

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=[_submit_tool()],
        max_iterations=3,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="control-test",
        scenario="task_execution",
        control_queue=queue,
    )

    assert result.status == "complete"
    second_messages = model.requests[1].payload.messages
    assert any("BACK_CONTROL_EVENT" in message.content for message in second_messages)
    assert any("Kyoto" in message.content for message in second_messages)
    assert any(event["event_type"] == "parameter_update" for event in result.loop_events)


@pytest.mark.asyncio
async def test_repeated_empty_back_response_returns_loop_degenerate() -> None:
    class Model:
        async def execute(self, request):  # type: ignore[no-untyped-def]
            return make_hub_empty_response()

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=[_submit_tool()],
        max_iterations=5,
        model=Model(),  # type: ignore[arg-type]
        tool_dispatcher=_SubmitDispatcher(),  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="degenerate-test",
        scenario="task_execution",
    )

    assert result.status == "loop_degenerate"
    assert result.data == {"error_code": "REACT_LOOP_DEGENERATE"}
    assert any(event["event_type"] == "degenerate_loop" for event in result.loop_events)


@pytest.mark.asyncio
async def test_back_missing_submit_result_is_typed_terminal_status() -> None:
    class Model:
        async def execute(self, request):  # type: ignore[no-untyped-def]
            return make_hub_text_response("still thinking")

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=[_submit_tool()],
        max_iterations=2,
        model=Model(),  # type: ignore[arg-type]
        tool_dispatcher=_SubmitDispatcher(),  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="missing-submit-test",
        scenario="task_execution",
    )

    assert result.status == "missing_submit_result"
    assert result.data == {"error_code": "REACT_MISSING_SUBMIT_RESULT"}


@pytest.mark.asyncio
async def test_back_text_after_empty_discovery_nudges_needs_human() -> None:
    class Model:
        def __init__(self) -> None:
            self.requests = []

        async def execute(self, request):  # type: ignore[no-untyped-def]
            self.requests.append(request)
            if len(self.requests) == 1:
                return make_hub_tool_response(
                    [
                        {
                            "id": "discover-1",
                            "name": "discover_capabilities",
                            "arguments": {"intent": "find missing service"},
                        }
                    ]
                )
            if len(self.requests) == 2:
                return make_hub_text_response("I cannot find a matching capability.")
            return make_hub_tool_response(
                [
                    {
                        "id": "submit-1",
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "needs_human",
                            "hil_type": "escalate",
                            "question": "No matching capability is available.",
                        },
                    }
                ]
            )

    class Dispatcher:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def dispatch(self, tool_call):  # type: ignore[no-untyped-def]
            self.calls.append(tool_call.name)
            if tool_call.name == "discover_capabilities":
                return ToolResult(
                    tool_name="discover_capabilities",
                    status="ok",
                    data={"capabilities": [], "count": 0},
                )
            return ToolResult(tool_name=tool_call.name, status="ok", data={"ok": True})

    model = Model()
    dispatcher = Dispatcher()

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=[_tool("discover_capabilities"), _submit_tool()],
        max_iterations=4,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="empty-discovery-test",
        scenario="task_execution",
    )

    assert result.status == "suspended"
    assert result.data and result.data["result_type"] == "needs_human"
    assert dispatcher.calls == ["discover_capabilities", "submit_result"]
    nudge_messages = [
        message.content
        for request in model.requests
        for message in request.payload.messages
        if "Discovery returned no viable capability candidates" in message.content
    ]
    assert nudge_messages
    assert "result_type='needs_human'" in nudge_messages[-1]


@pytest.mark.asyncio
async def test_failed_capability_binding_does_not_count_as_authority_progress() -> None:
    class Model:
        def __init__(self) -> None:
            self.requests = []

        async def execute(self, request):  # type: ignore[no-untyped-def]
            self.requests.append(request)
            if len(self.requests) == 1:
                return make_hub_tool_response(
                    [
                        {
                            "id": "invoke-1",
                            "name": "invoke_capability",
                            "arguments": {
                                "capability_name": "tool.read.shopping.list_lists",
                                "params": {"category": "groceries"},
                            },
                        }
                    ]
                )
            if len(self.requests) == 2:
                return make_hub_text_response("I handled it.")
            return make_hub_tool_response(
                [
                    {
                        "id": "submit-1",
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "needs_human",
                            "hil_type": "clarification",
                            "question": "No valid registry capability was available.",
                        },
                    }
                ]
            )

    class Dispatcher:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def dispatch(self, tool_call):  # type: ignore[no-untyped-def]
            self.calls.append(tool_call.name)
            if tool_call.name == "invoke_capability":
                return ToolResult(
                    tool_name="invoke_capability",
                    status="error",
                    error="capability_binding_invalid_candidate",
                    data={
                        "candidates": [{"name": "tool.read.shopping.list_lists"}],
                        "recovery": {
                            "rejected_name": "tool.read.shopping.bad_name",
                        },
                    },
                )
            return ToolResult(tool_name=tool_call.name, status="ok", data={"ok": True})

    model = Model()
    dispatcher = Dispatcher()

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=[_tool("invoke_capability"), _submit_tool()],
        max_iterations=4,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="failed-binding-authority-test",
        scenario="task_execution",
    )

    assert result.status == "suspended"
    assert dispatcher.calls == ["invoke_capability", "submit_result"]
    message_text = "\n".join(
        message.content for request in model.requests for message in request.payload.messages
    )
    assert "failed during registry binding" in message_text
    assert "You already invoked an authority capability" not in message_text


@pytest.mark.asyncio
async def test_back_discovery_context_spin_gets_authority_nudge() -> None:
    class Model:
        def __init__(self) -> None:
            self.requests = []

        async def execute(self, request):  # type: ignore[no-untyped-def]
            self.requests.append(request)
            if len(self.requests) == 1:
                return make_hub_tool_response(
                    [
                        {
                            "id": "discover-1",
                            "name": "discover_capabilities",
                            "arguments": {"intent": "add groceries", "domain": "shopping"},
                        }
                    ]
                )
            if len(self.requests) == 2:
                return make_hub_tool_response(
                    [
                        {
                            "id": "recall-1",
                            "name": "recall_memory",
                            "arguments": {"query": "shopping list ingredients"},
                        }
                    ]
                )
            return make_hub_tool_response(
                [
                    {
                        "id": "submit-1",
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "needs_human",
                            "hil_type": "clarification",
                            "question": "Which list should I use?",
                        },
                    }
                ]
            )

    class Dispatcher:
        async def dispatch(self, tool_call):  # type: ignore[no-untyped-def]
            if tool_call.name == "discover_capabilities":
                return ToolResult(
                    tool_name="discover_capabilities",
                    status="ok",
                    data={
                        "count": 1,
                        "capabilities": [
                            {
                                "name": "tool.execute.shopping.add_item",
                                "schema": {
                                    "capabilities": ["write", "adapter:shopping"],
                                    "required_inputs": [
                                        {"name": "list_id"},
                                        {"name": "name"},
                                    ],
                                },
                            }
                        ],
                    },
                )
            return ToolResult(tool_name=tool_call.name, status="ok", data={"ok": True})

    model = Model()

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=[_tool("discover_capabilities"), _tool("recall_memory"), _submit_tool()],
        max_iterations=4,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=Dispatcher(),  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="back-spin-nudge-test",
        scenario="task_execution",
    )

    assert result.status == "suspended"
    assert any(event["event_type"] == "back_capability_spin_nudge" for event in result.loop_events)
    third_request_text = "\n".join(
        message.content for message in model.requests[2].payload.messages
    )
    assert (
        "Do NOT call discover_capabilities, recall_memory, or summarize_context again"
        in third_request_text
    )
