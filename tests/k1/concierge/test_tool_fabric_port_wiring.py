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
    execute_discover_capabilities,
    execute_execute_workflow,
    execute_invoke_capability,
    execute_spawn_via_fabric,
)
from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    CapabilityResult,
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
    async def test_domain_passed_as_list(self) -> None:
        mock_port = AsyncMock(spec=FabricDispatchAdapter)
        mock_port.discover_capabilities.return_value = _retrieval_result()
        ctx = _make_ctx(dispatch=mock_port)
        await execute_discover_capabilities({"intent": "send", "domain": "messaging"}, ctx)
        call_kwargs = mock_port.discover_capabilities.call_args
        assert call_kwargs.kwargs.get("domain") == ["messaging"] or call_kwargs[1].get(
            "domain"
        ) == ["messaging"]

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
