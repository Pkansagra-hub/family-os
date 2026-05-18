"""Back ReAct structured recovery regressions."""

from __future__ import annotations

import json

import pytest

from k1.concierge.llm.types import ModelMessage, ToolSchema
from k1.concierge.react.loop import react_loop
from k1.concierge.tools.recovery_contract import RECOVERY_SCHEMA_VERSION
from k1.concierge.tools.result_protocol import ToolResult
from tests.k1.concierge.conftest import make_hub_tool_response

_RECOVERY = {
    "schema_version": RECOVERY_SCHEMA_VERSION,
    "action": "ask_human",
    "hil_type": "clarification",
    "question": "I need the task title to keep going. What should I use?",
    "capability_name": "tool.execute.tasks.create_task",
    "missing_fields": ["title"],
    "field_contracts": [
        {
            "name": "title",
            "type": "string",
            "description": "Task title",
        }
    ],
    "retry_tool": "invoke_capability",
    "retry_args": {
        "capability_name": "tool.execute.tasks.create_task",
        "params": {"assigned_to": "jordan"},
    },
}


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def dispatch(self, tc) -> ToolResult:  # type: ignore[no-untyped-def]
        self.calls.append(tc.name)
        if tc.name == "invoke_capability":
            return ToolResult(
                tool_name=tc.name,
                status="error",
                error="capability_params_incomplete",
                data={
                    "status": "needs_human",
                    "capability_name": "tool.execute.tasks.create_task",
                    "recovery": dict(_RECOVERY),
                },
            )
        return ToolResult(tool_name=tc.name, status="ok", data={"delivered": True})


class _Model:
    def __init__(self, responses) -> None:  # type: ignore[no-untyped-def]
        self._responses = list(responses)
        self.calls = 0

    async def execute(self, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        return self._responses.pop(0)


def _tools() -> list[ToolSchema]:
    return [
        ToolSchema(
            name="discover_capabilities", description="discover", parameters={"type": "object"}
        ),
        ToolSchema(name="invoke_capability", description="invoke", parameters={"type": "object"}),
        ToolSchema(name="submit_result", description="submit", parameters={"type": "object"}),
    ]


async def _never_cancel() -> bool:
    return False


@pytest.mark.asyncio
async def test_back_tool_recovery_contract_suspends_for_human_without_model_question() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "invoke_capability",
                        "arguments": {
                            "capability_name": "tool.execute.tasks.create_task",
                            "params": {"assigned_to": "jordan"},
                        },
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
        tools=_tools(),
        max_iterations=4,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="trace-clarify",
        scenario="task_execution",
    )

    assert result.status == "suspended"
    assert result.data is not None
    assert result.data["result_type"] == "needs_human"
    assert result.data["hil_type"] == "clarification"
    assert result.data["question"] == _RECOVERY["question"]
    assert result.data["missing_fields"] == ["title"]
    assert result.data["recovery"]["schema_version"] == RECOVERY_SCHEMA_VERSION
    assert result.data["recovery"]["capability_name"] == "tool.execute.tasks.create_task"
    assert dispatcher.calls == ["invoke_capability"]
    assert model.calls == 1


@pytest.mark.asyncio
async def test_back_recovery_contract_preempts_submit_result_retry() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "invoke_capability",
                        "arguments": {
                            "capability_name": "tool.execute.tasks.create_task",
                            "params": {"assigned_to": "jordan"},
                        },
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "complete",
                            "final_answer": "I wasn't able to create the task.",
                        },
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
        tools=_tools(),
        max_iterations=4,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="trace-clarify",
        scenario="task_execution",
    )

    assert result.status == "suspended"
    assert result.data is not None
    assert result.data["question"] == _RECOVERY["question"]
    assert dispatcher.calls == ["invoke_capability"]
    assert model.calls == 1


class _DiscoveryThenAuthorityDispatcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def dispatch(self, tc) -> ToolResult:  # type: ignore[no-untyped-def]
        self.calls.append(tc.name)
        if tc.name == "discover_capabilities":
            return ToolResult(
                tool_name=tc.name,
                status="ok",
                data={
                    "count": 2,
                    "capabilities": [
                        {"name": "tool.read.records.list_records", "schema": {}},
                        {"name": "tool.execute.records.delete_record", "schema": {}},
                    ],
                },
            )
        if tc.name == "invoke_capability":
            return ToolResult(
                tool_name=tc.name,
                status="ok",
                data={"status": "success", "result": {"deleted": 2}},
            )
        return ToolResult(tool_name=tc.name, status="ok", data={"delivered": True})


class _ContractPlanDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def dispatch(self, tc) -> ToolResult:  # type: ignore[no-untyped-def]
        self.calls.append((tc.name, tc.arguments))
        if tc.name == "discover_capabilities":
            return ToolResult(
                tool_name=tc.name,
                status="ok",
                data={
                    "count": 2,
                    "capabilities": [
                        {
                            "name": "tool.execute.records.delete_record",
                            "score": 0.96,
                            "domains": ["system", "records"],
                            "schema": {
                                "capabilities": ["delete", "adapter:records"],
                                "required_inputs": [{"name": "record_id", "type": "string"}],
                                "optional_inputs": [],
                                "output": {
                                    "type": "object",
                                    "properties": {"record_id": {"type": "string"}},
                                },
                            },
                        },
                        {
                            "name": "tool.read.records.list_records",
                            "score": 0.92,
                            "domains": ["system", "records"],
                            "schema": {
                                "capabilities": ["read", "adapter:records"],
                                "required_inputs": [],
                                "optional_inputs": [],
                                "output": {
                                    "type": "object",
                                    "properties": {"records": {"type": "array"}},
                                    "required": ["records"],
                                },
                            },
                        },
                    ],
                },
            )
        if tc.name == "invoke_capability":
            assert tc.arguments["capability_name"] == "tool.read.records.list_records"
            return ToolResult(
                tool_name=tc.name,
                status="ok",
                data={
                    "status": "success",
                    "result": {"success": True, "records": [{"id": "r1"}, {"id": "r2"}]},
                },
            )
        if tc.name == "batch_invoke_capabilities":
            invocations = tc.arguments["invocations"]
            assert invocations == [
                {
                    "capability_name": "tool.execute.records.delete_record",
                    "params": {"record_id": "r1"},
                },
                {
                    "capability_name": "tool.execute.records.delete_record",
                    "params": {"record_id": "r2"},
                },
            ]
            return ToolResult(
                tool_name=tc.name,
                status="ok",
                data={
                    "results": [
                        {"capability_name": inv["capability_name"], "status": "success"}
                        for inv in invocations
                    ],
                    "total": 2,
                    "succeeded": 2,
                    "failed": 0,
                },
            )
        return ToolResult(tool_name=tc.name, status="ok", data={"delivered": True})


class _ReadPlanDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def dispatch(self, tc) -> ToolResult:  # type: ignore[no-untyped-def]
        self.calls.append((tc.name, tc.arguments))
        if tc.name == "discover_capabilities":
            return ToolResult(
                tool_name=tc.name,
                status="ok",
                data={
                    "count": 2,
                    "capabilities": [
                        {
                            "name": "tool.read.tasks.list_tasks",
                            "score": 0.96,
                            "domains": ["family", "tasks"],
                            "schema": {
                                "capabilities": ["read", "adapter:tasks"],
                                "required_inputs": [],
                                "optional_inputs": [
                                    {"name": "due_before", "type": "datetime"},
                                ],
                                "output": {
                                    "type": "object",
                                    "properties": {"tasks": {"type": "array"}},
                                    "required": ["tasks"],
                                },
                            },
                        },
                        {
                            "name": "tool.read.calendar.list_events",
                            "score": 0.94,
                            "domains": ["family", "calendar"],
                            "schema": {
                                "capabilities": ["read", "adapter:calendar"],
                                "required_inputs": [],
                                "optional_inputs": [
                                    {"name": "start", "type": "datetime"},
                                    {"name": "end", "type": "datetime"},
                                ],
                                "output": {
                                    "type": "object",
                                    "properties": {"events": {"type": "array"}},
                                    "required": ["events"],
                                },
                            },
                        },
                    ],
                },
            )
        if tc.name == "invoke_capability":
            capability_name = tc.arguments["capability_name"]
            if capability_name == "tool.read.tasks.list_tasks":
                result = {"success": True, "tasks": [{"id": "t1", "title": "Pack"}], "count": 1}
            else:
                result = {
                    "success": True,
                    "events": [{"id": "e1", "title": "Soccer"}],
                    "count": 1,
                }
            return ToolResult(
                tool_name=tc.name,
                status="ok",
                data={"status": "success", "result": result},
            )
        return ToolResult(tool_name=tc.name, status="ok", data={"delivered": True})


@pytest.mark.asyncio
async def test_back_accepts_needs_human_after_capability_discovery() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "discover_capabilities",
                        "arguments": {"intent": "delete all records", "domain": "operations"},
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "needs_human",
                            "hil_type": "clarification",
                            "question": "Should I delete them one by one?",
                        },
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "invoke_capability",
                        "arguments": {
                            "capability_name": "tool.execute.records.delete_record",
                            "params": {"record_id": "record-1"},
                        },
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "complete",
                            "final_answer": "Deleted the matching records.",
                        },
                    }
                ]
            ),
        ]
    )
    dispatcher = _DiscoveryThenAuthorityDispatcher()

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=_tools(),
        max_iterations=6,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="trace-authority",
        scenario="task_execution",
    )

    assert result.status == "suspended"
    assert result.data is not None
    assert result.data["result_type"] == "needs_human"
    assert result.data["question"] == "Should I delete them one by one?"
    assert dispatcher.calls == ["discover_capabilities", "submit_result"]
    assert model.calls == 2


@pytest.mark.asyncio
async def test_back_does_not_auto_execute_collection_plan_after_needs_human() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "discover_capabilities",
                        "arguments": {"intent": "delete all records", "domain": "operations"},
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "needs_human",
                            "hil_type": "clarification",
                            "question": "Should I delete them one by one?",
                        },
                    }
                ]
            ),
        ]
    )
    dispatcher = _ContractPlanDispatcher()

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=_tools(),
        max_iterations=6,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="trace-contract-plan",
        scenario="task_execution",
    )

    assert result.status == "suspended"
    assert result.data is not None
    assert result.data["result_type"] == "needs_human"
    assert [name for name, _ in dispatcher.calls] == [
        "discover_capabilities",
        "submit_result",
    ]
    assert model.calls == 2


@pytest.mark.asyncio
async def test_back_does_not_auto_execute_collection_read_plan_after_needs_human() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "discover_capabilities",
                        "arguments": {"intent": "list tasks and calendar events"},
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "needs_human",
                            "hil_type": "clarification",
                            "question": "Should I try another source?",
                        },
                    }
                ]
            ),
        ]
    )
    dispatcher = _ReadPlanDispatcher()

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=[],
        tools=_tools(),
        max_iterations=6,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="trace-read-plan",
        scenario="task_execution",
    )

    assert result.status == "suspended"
    assert result.data is not None
    assert result.data["result_type"] == "needs_human"
    assert [name for name, _ in dispatcher.calls] == [
        "discover_capabilities",
        "submit_result",
    ]
    assert model.calls == 2


@pytest.mark.asyncio
async def test_back_resume_accepts_needs_human_from_history() -> None:
    model = _Model(
        [
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "needs_human",
                            "hil_type": "clarification",
                            "question": "Should I delete them one by one?",
                        },
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "invoke_capability",
                        "arguments": {
                            "capability_name": "tool.execute.records.delete_record",
                            "params": {"record_id": "record-1"},
                        },
                    }
                ]
            ),
            make_hub_tool_response(
                [
                    {
                        "name": "submit_result",
                        "arguments": {
                            "result_type": "complete",
                            "final_answer": "Deleted the matching records.",
                        },
                    }
                ]
            ),
        ]
    )
    dispatcher = _DiscoveryThenAuthorityDispatcher()
    prior_messages = [
        ModelMessage(
            role="tool",
            name="discover_capabilities",
            content=json.dumps(
                {
                    "count": 1,
                    "capabilities": [{"name": "tool.execute.records.delete_record", "schema": {}}],
                }
            ),
        )
    ]

    result = await react_loop(
        actor="back",
        system_prompt="system",
        messages=prior_messages,
        tools=_tools(),
        max_iterations=5,
        model=model,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        on_text_response=lambda text: None,  # type: ignore[arg-type]
        cancellation_check=_never_cancel,
        trace_id="trace-resume-authority",
        scenario="task_execution",
    )

    assert result.status == "suspended"
    assert result.data is not None
    assert result.data["result_type"] == "needs_human"
    assert dispatcher.calls == ["submit_result"]
    assert model.calls == 1
