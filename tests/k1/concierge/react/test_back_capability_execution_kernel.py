"""M8.E1 Back capability execution kernel regressions."""

from __future__ import annotations

import pytest

from k1.concierge.llm.types import ToolSchema
from k1.concierge.react.back_execution_plan import BackExecutionPlan
from k1.concierge.react.loop import react_loop
from k1.concierge.tools.result_protocol import ToolResult
from tests.k1.concierge.conftest import make_hub_tool_response


def _tool(name: str) -> ToolSchema:
    return ToolSchema(name=name, description=name, parameters={"type": "object"})


async def _never_cancel() -> bool:
    return False


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def dispatch(self, tc) -> ToolResult:  # type: ignore[no-untyped-def]
        self.calls.append(tc.name)
        if tc.name == "discover_capabilities":
            domain = tc.arguments.get("domain")
            capability = (
                "tool.execute.tasks.create_task"
                if domain == "tasks"
                else "tool.execute.calendar.create_event"
            )
            return ToolResult(
                tool_name=tc.name,
                status="ok",
                data={"count": 1, "capabilities": [{"name": capability, "domains": [domain]}]},
            )
        if tc.name == "invoke_capability":
            return ToolResult(
                tool_name=tc.name,
                status="ok",
                data={
                    "status": "success",
                    "result": {"capability_name": tc.arguments.get("capability_name")},
                },
            )
        return ToolResult(tool_name=tc.name, status="ok", data={"accepted": True})


class _Model:
    def __init__(self, responses) -> None:  # type: ignore[no-untyped-def]
        self.responses = list(responses)

    async def execute(self, request):  # type: ignore[no-untyped-def]
        return self.responses.pop(0)


def _plan() -> BackExecutionPlan:
    return BackExecutionPlan.from_task(
        {
            "task_id": "task-1",
            "intents": [
                {"action": "create task", "domain": "tasks", "params": {"title": "Pack"}},
                {
                    "action": "create calendar event",
                    "domain": "calendar",
                    "params": {"title": "Dentist"},
                },
            ],
        }
    )


@pytest.mark.asyncio
async def test_submit_complete_is_rejected_until_every_intent_is_covered() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "invoke_capability",
                        "arguments": {
                            "capability_name": "tool.execute.tasks.create_task",
                            "domain": "tasks",
                            "params": {"title": "Pack"},
                        },
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {"result_type": "complete", "final_answer": "done"},
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "invoke_capability",
                        "arguments": {
                            "capability_name": "tool.execute.calendar.create_event",
                            "domain": "calendar",
                            "params": {"title": "Dentist"},
                        },
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {"result_type": "complete", "final_answer": "done"},
                    }
                ]
            ),
        ]
    )
    dispatcher = _Dispatcher()

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=[_tool("invoke_capability"), _tool("submit_result")],
        max_iterations=5,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        execution_plan=_plan(),
    )

    assert result.status == "complete"
    assert dispatcher.calls == ["invoke_capability", "invoke_capability", "submit_result"]
    assert result.data is not None
    assert result.data["execution_plan"]["complete"] is True
    assert [fact["domain"] for fact in result.data["facts"]] == ["tasks", "calendar"]
    assert any(
        event["event_type"] == "back_execution_plan_incomplete" for event in result.loop_events
    )


@pytest.mark.asyncio
async def test_batch_success_covers_multiple_intents_before_submit() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "batch_invoke_capabilities",
                        "arguments": {
                            "invocations": [
                                {
                                    "capability_name": "tool.execute.tasks.create_task",
                                    "domain": "tasks",
                                },
                                {
                                    "capability_name": "tool.execute.calendar.create_event",
                                    "domain": "calendar",
                                },
                            ]
                        },
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {"result_type": "complete", "final_answer": "done"},
                    }
                ]
            ),
        ]
    )

    class BatchDispatcher(_Dispatcher):
        async def dispatch(self, tc) -> ToolResult:  # type: ignore[no-untyped-def]
            self.calls.append(tc.name)
            if tc.name == "batch_invoke_capabilities":
                return ToolResult(
                    tool_name=tc.name,
                    status="ok",
                    data={
                        "results": [
                            {
                                "capability_name": invocation["capability_name"],
                                "status": "success",
                            }
                            for invocation in tc.arguments["invocations"]
                        ],
                        "total": 2,
                        "succeeded": 2,
                        "failed": 0,
                    },
                )
            if tc.name == "submit_result":
                return ToolResult(tool_name=tc.name, status="ok", data={"accepted": True})
            return await super().dispatch(tc)

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=[_tool("batch_invoke_capabilities"), _tool("submit_result")],
        max_iterations=3,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=BatchDispatcher(),  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        execution_plan=_plan(),
    )

    assert result.status == "complete"
    assert result.data is not None
    assert result.data["execution_plan"]["pending"] == []


@pytest.mark.asyncio
async def test_tasks_calendar_bundled_read_regression_completes_with_two_facts() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "discover_capabilities",
                        "arguments": {"intent": "list tasks", "domain": "tasks"},
                    },
                    {
                        "name": "discover_capabilities",
                        "arguments": {
                            "intent": "list calendar events",
                            "domain": "calendar",
                        },
                    },
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "batch_invoke_capabilities",
                        "arguments": {
                            "invocations": [
                                {
                                    "capability_name": "tool.read.family_tasks.list_tasks",
                                    "params": {},
                                },
                                {
                                    "capability_name": "tool.read.calendar.list_events",
                                    "params": {},
                                },
                            ]
                        },
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {"result_type": "complete", "final_answer": "done"},
                    }
                ]
            ),
        ]
    )

    class TasksCalendarDispatcher(_Dispatcher):
        async def dispatch(self, tc) -> ToolResult:  # type: ignore[no-untyped-def]
            self.calls.append(tc.name)
            if tc.name == "discover_capabilities":
                domain = tc.arguments.get("domain")
                capability = (
                    "tool.read.family_tasks.list_tasks"
                    if domain == "tasks"
                    else "tool.read.calendar.list_events"
                )
                return ToolResult(
                    tool_name=tc.name,
                    status="ok",
                    data={
                        "count": 1,
                        "capabilities": [
                            {
                                "name": capability,
                                "domains": [domain],
                                "diagnostics": {"contract_evidence_score": 1.0},
                            }
                        ],
                    },
                )
            if tc.name == "batch_invoke_capabilities":
                return ToolResult(
                    tool_name=tc.name,
                    status="ok",
                    data={
                        "results": [
                            {
                                "capability_name": "tool.read.family_tasks.list_tasks",
                                "status": "success",
                                "result": {"tasks": [{"title": "Pack lunch"}]},
                            },
                            {
                                "capability_name": "tool.read.calendar.list_events",
                                "status": "success",
                                "result": {"events": [{"title": "Soccer", "time": "6 PM"}]},
                            },
                        ],
                        "total": 2,
                        "succeeded": 2,
                        "failed": 0,
                    },
                )
            return await super().dispatch(tc)

    task = {
        "task_id": "task-tasks-calendar",
        "intents": [
            {"action": "list tasks", "domain": "tasks", "params": {}},
            {"action": "list calendar events", "domain": "calendar", "params": {}},
        ],
    }
    dispatcher = TasksCalendarDispatcher()

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=[
            _tool("discover_capabilities"),
            _tool("batch_invoke_capabilities"),
            _tool("submit_result"),
        ],
        max_iterations=4,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        execution_plan=BackExecutionPlan.from_task(task),
    )

    assert result.status == "complete"
    assert result.data is not None
    assert result.data["execution_plan"]["complete"] is True
    facts = result.data["facts"]
    assert [fact["domain"] for fact in facts] == ["tasks", "calendar"]
    assert facts[0]["result"]["tasks"][0]["title"] == "Pack lunch"
    assert facts[1]["result"]["events"][0]["title"] == "Soccer"
    assert result.status not in {"missing_submit_result", "degenerate_loop"}
    assert not any(
        event.get("event_type") == "back_execution_plan_incomplete" for event in result.loop_events
    )
    assert dispatcher.calls[:3] == [
        "discover_capabilities",
        "discover_capabilities",
        "batch_invoke_capabilities",
    ]
    assert "submit_result" in dispatcher.calls


@pytest.mark.asyncio
async def test_back_parallelizes_read_only_invoke_capability_but_not_write() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "invoke_capability",
                        "arguments": {"capability_name": "tool.read.tasks.list_tasks"},
                    },
                    {
                        "name": "invoke_capability",
                        "arguments": {"capability_name": "tool.execute.tasks.create_task"},
                    },
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {"result_type": "complete", "final_answer": "done"},
                    }
                ]
            ),
        ]
    )

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=[_tool("invoke_capability"), _tool("submit_result")],
        max_iterations=3,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=_Dispatcher(),  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
    )

    assert result.status == "complete"
    assert result.parallel_tool_calls == 1
    assert result.sequential_tool_calls == 1


@pytest.mark.asyncio
async def test_parallel_tool_exception_becomes_tool_observation() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "invoke_capability",
                        "arguments": {"capability_name": "tool.read.tasks.list_tasks"},
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {"result_type": "complete", "final_answer": "done"},
                    }
                ]
            ),
        ]
    )

    class RaisingDispatcher:
        async def dispatch(self, tc) -> ToolResult:  # type: ignore[no-untyped-def]
            if tc.name == "invoke_capability":
                raise RuntimeError("provider broken")
            return ToolResult(tool_name=tc.name, status="ok", data={"accepted": True})

    messages = []
    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=messages,
        tools=[_tool("invoke_capability"), _tool("submit_result")],
        max_iterations=3,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=RaisingDispatcher(),  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
    )

    assert result.status == "complete"
    assert any("tool_exception: provider broken" in message.content for message in messages)
