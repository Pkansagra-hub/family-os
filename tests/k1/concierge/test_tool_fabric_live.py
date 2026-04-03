"""
E6.7.4 — Tool functions with a real K1 Fabric (live integration).

Validates: tool functions -> ToolContext.fabric_port -> Fabric -> BridgeProvider -> handler.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from k1.concierge.fabric.capability_registry import create_demo_registry
from k1.concierge.fabric.contract_converter import convert_all_poc_capabilities
from k1.concierge.fabric.poc_bridge_adapter import POCMockBridgeAdapter
from k1.concierge.tools.implementations import (
    ToolContext,
    execute_batch_invoke_capabilities,
    execute_discover_capabilities,
    execute_execute_workflow,
    execute_invoke_capability,
    execute_spawn_via_fabric,
)
from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory, _auto_register_providers

# =====================================================================
# Helpers
# =====================================================================


def _mock_session_manager() -> MagicMock:
    sm = MagicMock()
    sm.get_section = MagicMock(return_value=None)
    return sm


def _create_wired_fabric() -> Fabric:
    registry = create_demo_registry()
    poc_bridge = POCMockBridgeAdapter(registry)
    fabric = FabricFactory.create_with_ports(
        state_reader=TestSessionStateReaderAdapter(),
        event_port=LocalEventAdapter(capture_mode=True),
        bridge=poc_bridge,
        model_gateway=TestModelGatewayAdapter(),
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
        production_mode=False,
    )
    for contract in convert_all_poc_capabilities():
        fabric.register(contract)

    # Re-run auto-registration so poc-mock-bridge gets a ProviderConfig
    provider_registry = fabric.facade._resolver._provider_matcher._provider_registry
    _auto_register_providers(fabric.registry, provider_registry)

    return fabric


def _make_ctx(fabric: Fabric | None = None) -> ToolContext:
    return ToolContext(
        session_manager=_mock_session_manager(),
        cognitive_trace_id=f"test-{uuid.uuid4().hex[:6]}",
        actor="back",
        fabric_port=fabric,
    )


# =====================================================================
# discover_capabilities via real Fabric
# =====================================================================


class TestDiscoverLive:
    """discover_capabilities tool through real Fabric pipeline."""

    @pytest.mark.asyncio
    async def test_discover_returns_ok(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_discover_capabilities(
            {"intent": "book a hotel", "domain": "travel"}, ctx
        )
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_discover_returns_capabilities_list(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_discover_capabilities(
            {"intent": "book a hotel", "domain": "travel"}, ctx
        )
        assert "capabilities" in result.data
        assert isinstance(result.data["capabilities"], list)

    @pytest.mark.asyncio
    async def test_discover_caches_result(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        r1 = await execute_discover_capabilities(
            {"intent": "search hotel", "domain": "travel"}, ctx
        )
        r2 = await execute_discover_capabilities(
            {"intent": "search hotel", "domain": "travel"}, ctx
        )
        # Same object from cache
        assert r1 is r2

    @pytest.mark.asyncio
    async def test_discover_empty_intent_errors(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_discover_capabilities({"intent": ""}, ctx)
        assert result.status == "error"


# =====================================================================
# invoke_capability via real Fabric
# =====================================================================


class TestInvokeLive:
    """invoke_capability tool through real Fabric pipeline."""

    @pytest.mark.asyncio
    async def test_invoke_hotel_search_ok(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_invoke_capability(
            {"capability_name": "tool.execute.hotel_search", "params": {"location": "Paris"}},
            ctx,
        )
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_invoke_returns_data(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_invoke_capability(
            {"capability_name": "tool.execute.hotel_search", "params": {"location": "Paris"}},
            ctx,
        )
        assert result.data is not None
        assert "result" in result.data
        assert "duration_ms" in result.data

    @pytest.mark.asyncio
    async def test_invoke_nonexistent_fails(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_invoke_capability(
            {"capability_name": "tool.execute.no_such_cap", "params": {}},
            ctx,
        )
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_invoke_empty_name_errors(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_invoke_capability({"capability_name": "", "params": {}}, ctx)
        assert result.status == "error"
        assert "required" in result.error.lower()


# =====================================================================
# batch_invoke_capabilities via real Fabric
# =====================================================================


class TestBatchInvokeLive:
    """batch_invoke_capabilities through real Fabric pipeline."""

    @pytest.mark.asyncio
    async def test_batch_two_caps(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_batch_invoke_capabilities(
            {
                "invocations": [
                    {
                        "capability_name": "tool.execute.hotel_search",
                        "params": {"location": "Paris"},
                    },
                    {
                        "capability_name": "tool.execute.weather_forecast",
                        "params": {"location": "NYC"},
                    },
                ]
            },
            ctx,
        )
        assert result.status == "ok"
        assert result.data["total"] == 2
        assert result.data["succeeded"] >= 1

    @pytest.mark.asyncio
    async def test_batch_empty_errors(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_batch_invoke_capabilities({"invocations": []}, ctx)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_batch_with_bad_cap_partial_failure(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_batch_invoke_capabilities(
            {
                "invocations": [
                    {
                        "capability_name": "tool.execute.hotel_search",
                        "params": {"location": "Paris"},
                    },
                    {"capability_name": "tool.execute.nonexistent_xyz", "params": {}},
                ]
            },
            ctx,
        )
        assert result.data["total"] == 2
        assert result.data["failed"] >= 1


# =====================================================================
# spawn_via_fabric via real Fabric
# =====================================================================


class TestSpawnLive:
    """spawn_via_fabric — no AgentProvider registered, expects failure."""

    @pytest.mark.asyncio
    async def test_spawn_agent_no_provider(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_spawn_via_fabric(
            {"agent_type": "researcher", "task": "find info"}, ctx
        )
        # No AgentProvider registered → execute fails at resolution
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_spawn_missing_args_errors(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_spawn_via_fabric({"agent_type": "", "task": ""}, ctx)
        assert result.status == "error"


# =====================================================================
# execute_workflow via real Fabric
# =====================================================================


class TestWorkflowLive:
    """execute_workflow — no WorkflowProvider registered, expects failure."""

    @pytest.mark.asyncio
    async def test_workflow_no_provider(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_execute_workflow(
            {"workflow_id": "morning_routine", "params": {}}, ctx
        )
        # No WorkflowProvider registered → resolution fails
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_workflow_missing_id_errors(self) -> None:
        fabric = _create_wired_fabric()
        ctx = _make_ctx(fabric)
        result = await execute_execute_workflow({"workflow_id": "", "params": {}}, ctx)
        assert result.status == "error"
        assert "required" in result.error.lower()


# =====================================================================
# No fabric_port fallback (defensive)
# =====================================================================


class TestNoFabricFallback:
    """Tool functions still work when fabric_port is None."""

    @pytest.mark.asyncio
    async def test_discover_empty_without_fabric(self) -> None:
        ctx = _make_ctx(None)
        result = await execute_discover_capabilities({"intent": "hotel search"}, ctx)
        assert result.status == "ok"
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_invoke_poc_placeholder_without_fabric(self) -> None:
        ctx = _make_ctx(None)
        result = await execute_invoke_capability(
            {"capability_name": "tool.execute.hotel_search", "params": {}},
            ctx,
        )
        assert result.status == "ok"
        assert result.data["result"]["_poc"] is True
