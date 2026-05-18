"""
E2.6.3 — Unit Tests for Tool ↔ IDispatchPort Wiring
===================================================

Validates that the 5 Back tool functions correctly use IDispatchPort
when set, and fall back to legacy callbacks when dispatch is None.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter
from k1.concierge.ports import IDispatchPort
from k1.concierge.tools.implementations import (
    ToolContext,
    ToolResult,
    execute_batch_invoke_capabilities,
    execute_discover_capabilities,
    execute_execute_workflow,
    execute_invoke_capability,
    execute_spawn_via_fabric,
)
from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    CapabilityResult,
    InputSpec,
    RetrievalResult,
    ScoredCapability,
)

# =====================================================================
# Fixtures
# =====================================================================


def _mock_session_manager() -> MagicMock:
    """Minimal session manager mock for ToolContext."""
    sm = MagicMock()
    sm.get_section = MagicMock(return_value=None)
    return sm


def _make_ctx(
    dispatch: IDispatchPort | None = None,
    actor: str = "back",
    active_task_id: str | None = None,
    *,
    allow_dispatch_passthrough: bool = True,
    session_id: str = "",
    safety_band: str = "AMBER",
) -> ToolContext:
    """Build a minimal ToolContext for tool-handler tests.

    M17.E1.I1: ``allow_dispatch_passthrough`` defaults to True here so
    that this test module's legacy ``TestBackwardCompat`` cases (which
    deliberately exercise the POC stub via ``dispatch=None``) keep their
    original semantics. The hard-fail behaviour with the production
    default (False) is covered by
    ``tests/unit/concierge/tools/test_dispatch_passthrough_gate.py``.
    """
    return ToolContext(
        session_manager=_mock_session_manager(),
        cognitive_trace_id=f"test-{uuid.uuid4().hex[:6]}",
        actor=actor,
        dispatch=dispatch,
        active_task_id=active_task_id,
        allow_dispatch_passthrough=allow_dispatch_passthrough,
        session_id=session_id,
        safety_band=safety_band,
    )


def _success_result(**kwargs) -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id=kwargs.get("request_id", "r1"),
        data=kwargs.get("data", {"ok": True}),
        provider_id="test",
    )


def _failure_result(**kwargs) -> CapabilityResult:
    return CapabilityResult.failure_result(
        request_id=kwargs.get("request_id", "r1"),
        error_code="test_error",
        error_message=kwargs.get("error_message", "boom"),
        retriable=False,
        provider_id="test",
    )


def _retrieval_result(names: list[str] | None = None) -> RetrievalResult:
    caps = []
    for i, name in enumerate(names or ["tool.execute.send_message"]):
        caps.append(
            ScoredCapability(
                contract=CapabilityContract(
                    name=name, description=f"Desc of {name}", domain=["test"]
                ),
                score=1.0 - i * 0.1,
            )
        )
    return RetrievalResult(capabilities=caps, total_matched=len(caps), query_intent="test")


# =====================================================================
# discover_capabilities + fabric_port
# =====================================================================


class TestDiscoverWithFabricPort:
    """execute_discover_capabilities uses fabric_port when set."""

    @pytest.mark.asyncio
    async def test_calls_fabric_port_discover(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.return_value = _retrieval_result(
            ["tool.execute.send_message"]
        )
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_discover_capabilities({"intent": "send message"}, ctx)
        mock_port.discover_capabilities.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_ok_tool_result(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.return_value = _retrieval_result(
            ["tool.execute.send_message"]
        )
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_discover_capabilities({"intent": "send message"}, ctx)
        assert isinstance(result, ToolResult)
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_result_contains_capabilities(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.return_value = _retrieval_result(
            ["tool.execute.send_message", "tool.execute.check_calendar"]
        )
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_discover_capabilities({"intent": "send message"}, ctx)
        assert "capabilities" in result.data
        assert len(result.data["capabilities"]) == 2

    @pytest.mark.asyncio
    async def test_capability_dict_has_name(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.return_value = _retrieval_result(
            ["tool.execute.send_message"]
        )
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_discover_capabilities({"intent": "send message"}, ctx)
        cap = result.data["capabilities"][0]
        assert cap["name"] == "tool.execute.send_message"

    @pytest.mark.asyncio
    async def test_capability_dict_has_score(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.return_value = _retrieval_result(
            ["tool.execute.send_message"]
        )
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_discover_capabilities({"intent": "send message"}, ctx)
        cap = result.data["capabilities"][0]
        assert "score" in cap
        assert isinstance(cap["score"], float)

    @pytest.mark.asyncio
    async def test_capability_dict_has_input_schema_and_caches_contract(self) -> None:
        contract = CapabilityContract(
            name="tool.execute.tasks.create_task",
            description="Create a task",
            domain=["family", "tasks"],
            required_inputs=[InputSpec(name="title", type="string", description="Task title")],
            optional_inputs=[InputSpec(name="assigned_to", type="string", description="Member id")],
        )
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.return_value = RetrievalResult(
            capabilities=[ScoredCapability(contract=contract, score=1.0)],
            total_matched=1,
        )
        ctx = _make_ctx(dispatch=mock_port)

        result = await execute_discover_capabilities({"intent": "create task"}, ctx)

        cap = result.data["capabilities"][0]
        assert cap["schema"]["required_inputs"] == [
            {"name": "title", "type": "string", "description": "Task title"}
        ]
        assert cap["schema"]["optional_inputs"] == [
            {"name": "assigned_to", "type": "string", "description": "Member id"}
        ]
        assert ctx.capability_cache[("capability_contract", contract.name)] is contract

    @pytest.mark.asyncio
    async def test_capability_dict_has_contract_metadata_for_planning(self) -> None:
        contract = CapabilityContract(
            name="tool.read.records.list_records",
            description="List records",
            domain=["system", "records"],
            prompt_template="records_activity_v1",
            activity_profile="records.v1",
            tool_instructions="Read records before writing summaries.",
            capabilities=["read", "adapter:records"],
            limitations=["do not use for writes"],
            output={
                "type": "object",
                "properties": {"records": {"type": "array"}},
                "required": ["records"],
            },
        )
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.return_value = RetrievalResult(
            capabilities=[ScoredCapability(contract=contract, score=1.0)],
            total_matched=1,
        )
        ctx = _make_ctx(dispatch=mock_port)

        result = await execute_discover_capabilities({"intent": "list records"}, ctx)

        cap = result.data["capabilities"][0]
        assert cap["domains"] == ["system", "records"]
        assert cap["prompt_template"] == "records_activity_v1"
        assert cap["activity_profile"] == "records.v1"
        assert cap["tool_instructions"] == "Read records before writing summaries."
        assert cap["limitations"] == ["do not use for writes"]
        assert cap["schema"]["capabilities"] == ["read", "adapter:records"]
        assert cap["schema"]["output"]["properties"]["records"]["type"] == "array"

    @pytest.mark.asyncio
    async def test_domain_passed_as_list(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.return_value = _retrieval_result()
        ctx = _make_ctx(dispatch=mock_port)
        await execute_discover_capabilities({"intent": "send", "domain": "messaging"}, ctx)
        call_kwargs = mock_port.discover_capabilities.call_args_list[0]
        assert call_kwargs.kwargs.get("domain") == ["messaging"] or call_kwargs[1].get(
            "domain"
        ) == ["messaging"]

    @pytest.mark.asyncio
    async def test_domain_is_soft_hint_and_global_results_are_merged(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.side_effect = [
            _retrieval_result(["tool.read.records.list_records"]),
            _retrieval_result(["tool.execute.records.delete_record"]),
        ]
        ctx = _make_ctx(dispatch=mock_port)

        result = await execute_discover_capabilities(
            {"intent": "delete all matching records", "domain": "operations"}, ctx
        )

        assert mock_port.discover_capabilities.await_count == 2
        names = [cap["name"] for cap in result.data["capabilities"]]
        assert names == ["tool.read.records.list_records", "tool.execute.records.delete_record"]
        assert mock_port.discover_capabilities.call_args_list[0].kwargs["domain"] == ["operations"]
        assert mock_port.discover_capabilities.call_args_list[1].kwargs["domain"] is None

    @pytest.mark.asyncio
    async def test_empty_intent_returns_error(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_discover_capabilities({"intent": ""}, ctx)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_exception_returns_error(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.side_effect = RuntimeError("network down")
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_discover_capabilities({"intent": "test"}, ctx)
        assert result.status == "error"
        assert "network down" in result.error

    @pytest.mark.asyncio
    async def test_result_cached_per_session(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.return_value = _retrieval_result()
        ctx = _make_ctx(dispatch=mock_port)
        r1 = await execute_discover_capabilities({"intent": "send message"}, ctx)
        r2 = await execute_discover_capabilities({"intent": "send message"}, ctx)
        # Second call should use cache, not call fabric_port again
        assert mock_port.discover_capabilities.await_count == 1
        assert r1.data == r2.data


# =====================================================================
# invoke_capability + fabric_port
# =====================================================================


class TestInvokeWithFabricPort:
    """execute_invoke_capability uses fabric_port when set."""

    @pytest.mark.asyncio
    async def test_calls_fabric_port_execute(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_invoke_capability(
            {"capability_name": "tool.execute.send_message", "params": {}}, ctx
        )
        mock_port.dispatch_direct.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_builds_correct_capability_request(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port, actor="back")
        await execute_invoke_capability(
            {"capability_name": "tool.execute.test", "params": {"key": "val"}}, ctx
        )
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert isinstance(call_args, CapabilityRequest)
        assert call_args.capability_name == "tool.execute.test"
        assert call_args.params == {"key": "val"}
        assert call_args.caller == "concierge"
        assert call_args.caller_id == "concierge.back"
        assert call_args.safety_band == "AMBER"

    @pytest.mark.asyncio
    async def test_uses_context_safety_band(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port, actor="back", safety_band="RED")
        await execute_invoke_capability({"capability_name": "tool.execute.test", "params": {}}, ctx)
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert call_args.safety_band == "RED"

    @pytest.mark.asyncio
    async def test_synthesizes_trace_id_when_context_trace_missing(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port, actor="back")
        ctx.cognitive_trace_id = ""
        await execute_invoke_capability({"capability_name": "tool.execute.test", "params": {}}, ctx)
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert call_args.trace_id.startswith("tool-")
        assert ctx.cognitive_trace_id == call_args.trace_id

    @pytest.mark.asyncio
    async def test_normalizes_task_create_alias_params(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port, actor="back")
        await execute_invoke_capability(
            {
                "capability_name": "tool.execute.tasks.create_task",
                "params": {"description": "clean her bedroom", "assignee": "Riley"},
            },
            ctx,
        )
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert call_args.params["title"] == "clean her bedroom"
        assert call_args.params["assigned_to"] == "riley"

    @pytest.mark.asyncio
    async def test_normalizes_task_create_content_param(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port, actor="back")
        await execute_invoke_capability(
            {
                "capability_name": "tool.execute.tasks.create_task",
                "params": {"content": "start washer and dryer for Jordan"},
            },
            ctx,
        )
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert call_args.params["title"] == "start washer and dryer for Jordan"
        assert call_args.params["assigned_to"] == "jordan"

    @pytest.mark.asyncio
    async def test_missing_required_capability_param_returns_recovery_contract(self) -> None:
        contract = CapabilityContract(
            name="tool.execute.tasks.create_task",
            description="Create a task",
            domain=["family", "tasks"],
            required_inputs=[InputSpec(name="title", type="string", description="Task title")],
            optional_inputs=[InputSpec(name="assigned_to", type="string", description="Member id")],
        )
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.discover_capabilities.return_value = RetrievalResult(
            capabilities=[ScoredCapability(contract=contract, score=1.0)],
            total_matched=1,
        )
        ctx = _make_ctx(dispatch=mock_port, actor="back")

        result = await execute_invoke_capability(
            {
                "capability_name": "tool.execute.tasks.create_task",
                "params": {"assigned_to": "jordan"},
            },
            ctx,
        )

        assert result.status == "error"
        assert result.error == "capability_params_incomplete"
        assert result.data["status"] == "needs_human"
        assert result.data["recovery"]["schema_version"] == "k1.concierge.tool_recovery.v1"
        assert result.data["recovery"]["action"] == "ask_human"
        assert result.data["recovery"]["capability_name"] == "tool.execute.tasks.create_task"
        assert result.data["recovery"]["missing_fields"] == ["title"]
        mock_port.dispatch_direct.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_returns_ok(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result(data={"result": "done"})
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_invoke_capability({"capability_name": "cap1", "params": {}}, ctx)
        assert result.status == "ok"
        assert result.data["result"] == {"result": "done"}

    @pytest.mark.asyncio
    async def test_failure_returns_error(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _failure_result(error_message="not found")
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_invoke_capability({"capability_name": "cap1", "params": {}}, ctx)
        assert result.status == "error"
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_exception_returns_error(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.side_effect = RuntimeError("kaboom")
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_invoke_capability({"capability_name": "cap1", "params": {}}, ctx)
        assert result.status == "error"
        assert "kaboom" in result.error

    @pytest.mark.asyncio
    async def test_empty_name_returns_error(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_invoke_capability({"capability_name": "", "params": {}}, ctx)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_session_id_forwarded(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port)
        await execute_invoke_capability(
            {"capability_name": "cap1", "params": {}, "session_id": "sess-123"}, ctx
        )
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert call_args.session_id == "sess-123"

    @pytest.mark.asyncio
    async def test_has_duration_in_data(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_invoke_capability({"capability_name": "cap1", "params": {}}, ctx)
        assert "duration_ms" in result.data

    @pytest.mark.asyncio
    async def test_active_back_task_blocks_non_exact_candidate_before_fabric(self) -> None:
        contract = CapabilityContract(
            name="tool.execute.tasks.create_task",
            description="Create a task",
            domain=["tasks"],
        )
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.discover_capabilities.return_value = RetrievalResult(
            capabilities=[ScoredCapability(contract=contract, score=1.0)],
            total_matched=1,
        )
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port, actor="back", active_task_id="task-1")

        result = await execute_invoke_capability(
            {"capability_name": "tool.execute.tasks.add_task", "params": {}},
            ctx,
        )

        assert result.status == "error"
        assert result.error == "capability_binding_invalid_candidate"
        assert result.data["status"] == "invalid_candidate"
        assert result.data["candidates"][0]["name"] == "tool.execute.tasks.create_task"
        mock_port.dispatch_direct.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_active_back_task_attaches_contract_prompt_profile_metadata(self) -> None:
        contract = CapabilityContract(
            name="tool.execute.tasks.create_task",
            description="Create a task",
            domain=["tasks"],
            prompt_template="tasks_activity_v1",
            activity_profile="tasks.v1",
        )
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.discover_capabilities.return_value = RetrievalResult(
            capabilities=[ScoredCapability(contract=contract, score=1.0)],
            total_matched=1,
        )
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port, actor="back", active_task_id="task-1")

        await execute_invoke_capability(
            {
                "capability_name": "tool.execute.tasks.create_task",
                "params": {"title": "Clean room"},
            },
            ctx,
        )

        request = mock_port.dispatch_direct.call_args[0][0]
        assert request.prompt_template == "tasks_activity_v1"
        assert request.context_override == {
            "activity_profile": "tasks.v1",
            "prompt_variables": {"title": "Clean room"},
        }


class TestBatchInvokeWithFabricPort:
    """execute_batch_invoke_capabilities preserves Back context on Fabric requests."""

    @pytest.mark.asyncio
    async def test_forwards_session_and_safety_band(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port, session_id="sess-123", safety_band="AMBER")

        result = await execute_batch_invoke_capabilities(
            {
                "invocations": [
                    {
                        "capability_name": "tool.execute.calendar.create_event",
                        "params": {"title": "Dentist"},
                    }
                ]
            },
            ctx,
        )

        assert result.status == "ok"
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert isinstance(call_args, CapabilityRequest)
        assert call_args.session_id == "sess-123"
        assert call_args.safety_band == "AMBER"

    @pytest.mark.asyncio
    async def test_active_back_batch_attaches_contract_prompt_profile_metadata(self) -> None:
        contract = CapabilityContract(
            name="tool.execute.calendar.create_event",
            description="Create calendar event",
            domain=["calendar"],
            prompt_template="calendar_activity_v1",
            activity_profile="calendar.v1",
        )
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.discover_capabilities.return_value = RetrievalResult(
            capabilities=[ScoredCapability(contract=contract, score=1.0)],
            total_matched=1,
        )
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port, active_task_id="task-1")

        result = await execute_batch_invoke_capabilities(
            {
                "invocations": [
                    {
                        "capability_name": "tool.execute.calendar.create_event",
                        "params": {"title": "Dentist"},
                    }
                ]
            },
            ctx,
        )

        assert result.status == "ok"
        request = mock_port.dispatch_direct.call_args[0][0]
        assert request.prompt_template == "calendar_activity_v1"
        assert request.context_override == {
            "activity_profile": "calendar.v1",
            "prompt_variables": {"title": "Dentist"},
        }

    @pytest.mark.asyncio
    async def test_batch_all_failed_returns_outer_error(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _failure_result(error_message="provider down")
        ctx = _make_ctx(dispatch=mock_port)

        result = await execute_batch_invoke_capabilities(
            {
                "invocations": [
                    {
                        "capability_name": "tool.execute.calendar.create_event",
                        "params": {"title": "Dentist"},
                    }
                ]
            },
            ctx,
        )

        assert result.status == "error"
        assert result.error == "batch_invoke_all_failed"
        assert result.data["succeeded"] == 0
        assert result.data["failed"] == 1
        assert result.data["retryable"] is False

    @pytest.mark.asyncio
    async def test_active_back_exact_lookup_binds_registered_capability_without_semantic_match(
        self,
    ) -> None:
        contract = CapabilityContract(
            name="tool.read.shopping.list_lists",
            description="Return shopping lists",
            domain=["shopping"],
            prompt_template="shopping_activity_v1",
            activity_profile="shopping.v1",
        )
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.lookup_capability.return_value = contract
        mock_port.discover_capabilities.return_value = RetrievalResult(
            capabilities=[
                ScoredCapability(
                    contract=CapabilityContract(
                        name="tool.execute.shopping.add_item",
                        description="Add shopping item",
                        domain=["shopping"],
                    ),
                    score=1.0,
                )
            ],
            total_matched=1,
        )
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port, actor="back", active_task_id="task-1")

        result = await execute_invoke_capability(
            {
                "capability_name": "tool.read.shopping.list_lists",
                "params": {"category": "groceries"},
            },
            ctx,
        )

        assert result.status == "ok"
        request = mock_port.dispatch_direct.call_args[0][0]
        assert request.capability_name == "tool.read.shopping.list_lists"
        assert request.prompt_template == "shopping_activity_v1"
        assert request.context_override == {
            "activity_profile": "shopping.v1",
            "prompt_variables": {"category": "groceries"},
        }


# =====================================================================
# spawn_via_fabric + fabric_port
# =====================================================================


class TestSpawnWithFabricPort:
    """execute_spawn_via_fabric uses fabric_port when set."""

    @pytest.mark.asyncio
    async def test_calls_fabric_port_execute(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result(data={"agent_id": "a1"})
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_spawn_via_fabric(
            {"agent_type": "researcher", "task": "find info"}, ctx
        )
        mock_port.dispatch_direct.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_builds_agent_capability_name(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port)
        await execute_spawn_via_fabric({"agent_type": "researcher", "task": "find"}, ctx)
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert call_args.capability_name == "agent.researcher"

    @pytest.mark.asyncio
    async def test_success_returns_ok(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result(data={"agent_id": "a1"})
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_spawn_via_fabric({"agent_type": "researcher", "task": "go"}, ctx)
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_failure_returns_error(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _failure_result(error_message="no agent")
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_spawn_via_fabric({"agent_type": "researcher", "task": "go"}, ctx)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_missing_args_returns_error(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_spawn_via_fabric({"agent_type": "", "task": "go"}, ctx)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_params_include_task(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port)
        await execute_spawn_via_fabric({"agent_type": "researcher", "task": "find docs"}, ctx)
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert call_args.params["task"] == "find docs"


# =====================================================================
# execute_workflow + fabric_port
# =====================================================================


class TestWorkflowWithFabricPort:
    """execute_execute_workflow uses fabric_port when set."""

    @pytest.mark.asyncio
    async def test_calls_fabric_port_execute(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result(data={"workflow_done": True})
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_execute_workflow({"workflow_id": "wf_cleanup", "params": {}}, ctx)
        mock_port.dispatch_direct.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_builds_workflow_capability_name(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port)
        await execute_execute_workflow({"workflow_id": "wf_cleanup", "params": {}}, ctx)
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert call_args.capability_name == "workflow.wf_cleanup"

    @pytest.mark.asyncio
    async def test_timeout_forwarded(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()
        ctx = _make_ctx(dispatch=mock_port)
        await execute_execute_workflow(
            {"workflow_id": "wf1", "params": {}, "timeout_ms": 15000}, ctx
        )
        call_args = mock_port.dispatch_direct.call_args[0][0]
        assert call_args.timeout_ms == 15000

    @pytest.mark.asyncio
    async def test_success_returns_ok(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result(data={"done": True})
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_execute_workflow({"workflow_id": "wf1", "params": {}}, ctx)
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_failure_returns_error(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _failure_result(error_message="wf failed")
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_execute_workflow({"workflow_id": "wf1", "params": {}}, ctx)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_missing_workflow_id(self) -> None:
        mock_port = AsyncMock(spec=IDispatchPort)
        ctx = _make_ctx(dispatch=mock_port)
        result = await execute_execute_workflow({"workflow_id": "", "params": {}}, ctx)
        assert result.status == "error"


# =====================================================================
# Backward compat — dispatch=None falls through to placeholder
# =====================================================================


class TestBackwardCompat:
    """When dispatch=None, tool functions return safe defaults."""

    @pytest.mark.asyncio
    async def test_discover_returns_empty_without_fabric(self) -> None:
        ctx = _make_ctx(dispatch=None)
        result = await execute_discover_capabilities({"intent": "test"}, ctx)
        assert result.status == "ok"
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_invoke_returns_placeholder_without_fabric(self) -> None:
        ctx = _make_ctx(dispatch=None)
        result = await execute_invoke_capability({"capability_name": "cap1", "params": {}}, ctx)
        assert result.status == "ok"
        assert result.data["result"].get("_poc") is True

    @pytest.mark.asyncio
    async def test_spawn_falls_through_to_placeholder(self) -> None:
        """No fabric_port → POC placeholder."""
        ctx = _make_ctx(dispatch=None)
        result = await execute_spawn_via_fabric({"agent_type": "test", "task": "go"}, ctx)
        assert result.status == "ok"
        assert "agent_id" in result.data

    @pytest.mark.asyncio
    async def test_workflow_falls_through_to_placeholder(self) -> None:
        """No fabric_port → POC placeholder."""
        ctx = _make_ctx(dispatch=None)
        result = await execute_execute_workflow({"workflow_id": "wf1", "params": {}}, ctx)
        assert result.status == "ok"
        assert "execution_id" in result.data


# =====================================================================
# E4.M1.3: HIL enforcement migrated to fabric capability gate (E3)
# =====================================================================


class TestInvokeCapabilityPassesThroughToFabric:
    """E4.M1.3 -- ``execute_invoke_capability`` no longer consults a HIL
    coordinator.  L2 enforcement was removed in favour of the unified
    fabric capability gate (Epic E3), which guards every invocation
    pre-execution regardless of caller.  The two legacy tests for
    ``validate_before_invoke == "allow"`` and ``"block_red"`` are now
    duplicated by ``tests/k1/fabric/test_fabric_execute_with_gate.py``
    and have been removed here.
    """

    @pytest.mark.asyncio
    async def test_invoke_capability_passes_through_to_fabric(self) -> None:
        """With an active task id set, the tool still dispatches straight
        to the fabric port -- no HIL coordinator is consulted."""
        mock_port = AsyncMock(spec=IDispatchPort)
        mock_port.dispatch_direct.return_value = _success_result()

        ctx = _make_ctx(dispatch=mock_port, active_task_id="task-001")

        # The ToolContext exposes no HIL surface after E4.M1.3.
        assert not hasattr(ctx, "hil_coordinator")

        result = await execute_invoke_capability({"capability_name": "cap1", "params": {}}, ctx)
        assert result.status == "ok"
        mock_port.dispatch_direct.assert_awaited_once()
