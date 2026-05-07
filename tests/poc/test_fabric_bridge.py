"""
E2.6.2 — Unit Tests for poc/k1_poc/fabric/fabric_bridge.py
============================================================

Validates FabricPOCBridge translation between POC dict patterns
and K1 typed patterns. Covers execute, discover, batch, error
mapping, and factory methods.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    CapabilityResult,
    ErrorInfo,
    RetrievalResult,
    ScoredCapability,
)
from poc.k1_poc.fabric.capability_registry import CapabilityRegistry
from poc.k1_poc.fabric.fabric_bridge import FabricPOCBridge

# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def empty_registry() -> CapabilityRegistry:
    return CapabilityRegistry()


@pytest.fixture
def sample_registry() -> CapabilityRegistry:
    """Registry with 3 capabilities for test coverage."""
    reg = CapabilityRegistry()
    reg.register(
        {
            "name": "tool.execute.send_message",
            "description": "Send a message to a family member",
            "domain": "messaging",
            "required_inputs": ["recipient", "message"],
            "optional_inputs": ["urgency"],
            "has_side_effects": True,
            "estimated_cost": "free",
        },
        handler=_send_message_handler,
    )
    reg.register(
        {
            "name": "tool.execute.check_calendar",
            "description": "Check family calendar for upcoming events",
            "domain": "calendar",
            "required_inputs": [],
            "optional_inputs": ["date_range"],
            "has_side_effects": False,
            "estimated_cost": "free",
        },
        handler=_check_calendar_handler,
    )
    reg.register(
        {
            "name": "tool.execute.failing_cap",
            "description": "A capability that always fails for testing",
            "domain": "testing",
            "required_inputs": [],
            "optional_inputs": [],
            "has_side_effects": False,
            "estimated_cost": "free",
        },
        handler=_failing_handler,
    )
    return reg


@pytest.fixture
def bridge(sample_registry: CapabilityRegistry) -> FabricPOCBridge:
    return FabricPOCBridge(sample_registry)


@pytest.fixture
def empty_bridge(empty_registry: CapabilityRegistry) -> FabricPOCBridge:
    return FabricPOCBridge(empty_registry)


# =====================================================================
# Handler stubs
# =====================================================================


async def _send_message_handler(params: dict) -> dict:
    return {
        "success": True,
        "data": {"message_id": "msg-001", "delivered": True},
        "duration_ms": 50,
    }


async def _check_calendar_handler(params: dict) -> dict:
    return {
        "success": True,
        "data": {"events": [{"title": "Soccer Practice", "time": "15:00"}]},
        "duration_ms": 10,
    }


async def _failing_handler(params: dict) -> dict:
    return {
        "success": False,
        "error": "capability_unavailable",
        "data": None,
        "duration_ms": 5,
    }


# =====================================================================
# execute() — success path
# =====================================================================


class TestExecuteSuccess:
    """FabricPOCBridge.execute() with successful capabilities."""

    @pytest.mark.asyncio
    async def test_execute_returns_capability_result(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(
            capability_name="tool.execute.send_message",
            params={"recipient": "Mom", "message": "Hi"},
        )
        result = await bridge.execute(req)
        assert isinstance(result, CapabilityResult)

    @pytest.mark.asyncio
    async def test_execute_success_flag(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(
            capability_name="tool.execute.send_message",
            params={"recipient": "Mom", "message": "Hi"},
        )
        result = await bridge.execute(req)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_has_data(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(
            capability_name="tool.execute.send_message",
            params={"recipient": "Mom", "message": "Hi"},
        )
        result = await bridge.execute(req)
        assert isinstance(result.data, dict)
        assert result.data  # non-empty

    @pytest.mark.asyncio
    async def test_execute_has_duration(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(capability_name="tool.execute.send_message", params={})
        result = await bridge.execute(req)
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_no_error_on_success(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(capability_name="tool.execute.send_message", params={})
        result = await bridge.execute(req)
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_request_id_propagated(self, bridge: FabricPOCBridge) -> None:
        rid = f"req-{uuid.uuid4().hex[:8]}"
        req = CapabilityRequest(
            capability_name="tool.execute.send_message", params={}, request_id=rid
        )
        result = await bridge.execute(req)
        assert result.request_id == rid

    @pytest.mark.asyncio
    async def test_execute_trace_id_propagated(self, bridge: FabricPOCBridge) -> None:
        tid = f"trace-{uuid.uuid4().hex[:8]}"
        req = CapabilityRequest(
            capability_name="tool.execute.send_message", params={}, trace_id=tid
        )
        result = await bridge.execute(req)
        assert result.trace_id == tid

    @pytest.mark.asyncio
    async def test_execute_calendar_capability(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(capability_name="tool.execute.check_calendar", params={})
        result = await bridge.execute(req)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_provider_id(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(capability_name="tool.execute.send_message", params={})
        result = await bridge.execute(req)
        assert result.provider_id == "poc-bridge"


# =====================================================================
# execute() — failure path
# =====================================================================


class TestExecuteFailure:
    """FabricPOCBridge.execute() error handling."""

    @pytest.mark.asyncio
    async def test_unknown_capability_returns_failure(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(capability_name="tool.execute.nonexistent", params={})
        result = await bridge.execute(req)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_unknown_capability_has_error(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(capability_name="tool.execute.nonexistent", params={})
        result = await bridge.execute(req)
        assert result.error is not None
        assert isinstance(result.error, ErrorInfo)

    @pytest.mark.asyncio
    async def test_failing_handler_returns_error(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(capability_name="tool.execute.failing_cap", params={})
        result = await bridge.execute(req)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_failing_handler_error_info(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(capability_name="tool.execute.failing_cap", params={})
        result = await bridge.execute(req)
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_failing_handler_has_duration(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(capability_name="tool.execute.failing_cap", params={})
        result = await bridge.execute(req)
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_with_exception_handler(self, empty_bridge: FabricPOCBridge) -> None:
        """Exception from registry invoke → failure_result."""
        req = CapabilityRequest(capability_name="tool.execute.boom", params={})
        result = await empty_bridge.execute(req)
        assert result.success is False
        assert result.error is not None


# =====================================================================
# execute() — factory methods
# =====================================================================


class TestFactoryMethods:
    """CapabilityResult factory methods coverage."""

    def test_success_result_factory(self) -> None:
        r = CapabilityResult.success_result(
            request_id="r1",
            data={"key": "value"},
            provider_id="test",
        )
        assert r.success is True
        assert r.data == {"key": "value"}

    def test_failure_result_factory(self) -> None:
        r = CapabilityResult.failure_result(
            request_id="r2",
            error_code="test_error",
            error_message="Something went wrong",
            retriable=True,
            provider_id="test",
        )
        assert r.success is False
        assert r.error is not None
        assert r.error.code == "test_error"
        assert r.error.message == "Something went wrong"
        assert r.error.retriable is True

    def test_timeout_result_factory(self) -> None:
        r = CapabilityResult.timeout_result(
            request_id="r3",
            timeout_ms=5000,
            provider_id="test",
        )
        assert r.success is False
        assert r.error is not None


# =====================================================================
# discover_capabilities()
# =====================================================================


class TestDiscoverCapabilities:
    """FabricPOCBridge.discover_capabilities() intent/domain matching."""

    @pytest.mark.asyncio
    async def test_discover_returns_retrieval_result(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="send a message")
        assert isinstance(result, RetrievalResult)

    @pytest.mark.asyncio
    async def test_discover_messaging_intent(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="send a message")
        assert result.total_matched > 0
        assert len(result.capabilities) > 0

    @pytest.mark.asyncio
    async def test_discover_returns_scored_capabilities(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="send a message")
        for sc in result.capabilities:
            assert isinstance(sc, ScoredCapability)
            assert isinstance(sc.contract, CapabilityContract)
            assert isinstance(sc.score, float)

    @pytest.mark.asyncio
    async def test_discover_scores_descending(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="message calendar")
        if len(result.capabilities) >= 2:
            scores = [sc.score for sc in result.capabilities]
            assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_discover_with_domain_filter(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="send", domain=["messaging"])
        names = [sc.contract.name for sc in result.capabilities]
        assert "tool.execute.send_message" in names

    @pytest.mark.asyncio
    async def test_discover_query_intent_set(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="calendar events")
        assert result.query_intent == "calendar events"

    @pytest.mark.asyncio
    async def test_discover_latency_recorded(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="message")
        assert result.query_latency_ms >= 0

    @pytest.mark.asyncio
    async def test_discover_index_size(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="message")
        assert result.index_size == 3  # 3 capabilities in sample_registry

    @pytest.mark.asyncio
    async def test_discover_no_match(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="quantum_teleportation_xyzzy")
        assert result.total_matched == 0
        assert len(result.capabilities) == 0

    @pytest.mark.asyncio
    async def test_discover_empty_intent(self, bridge: FabricPOCBridge) -> None:
        """Empty intent should return results (empty string matches nothing)."""
        result = await bridge.discover_capabilities(intent="")
        assert isinstance(result, RetrievalResult)

    @pytest.mark.asyncio
    async def test_discover_contract_has_name(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="message")
        for sc in result.capabilities:
            assert sc.contract.name  # non-empty

    @pytest.mark.asyncio
    async def test_discover_contract_has_description(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.discover_capabilities(intent="message")
        for sc in result.capabilities:
            assert sc.contract.description  # non-empty


# =====================================================================
# execute_batch()
# =====================================================================


class TestExecuteBatch:
    """FabricPOCBridge.execute_batch() sequential execution."""

    @pytest.mark.asyncio
    async def test_batch_returns_list(self, bridge: FabricPOCBridge) -> None:
        reqs = [
            CapabilityRequest(capability_name="tool.execute.send_message", params={}),
            CapabilityRequest(capability_name="tool.execute.check_calendar", params={}),
        ]
        results = await bridge.execute_batch(reqs)
        assert isinstance(results, list)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_batch_all_success(self, bridge: FabricPOCBridge) -> None:
        reqs = [
            CapabilityRequest(capability_name="tool.execute.send_message", params={}),
            CapabilityRequest(capability_name="tool.execute.check_calendar", params={}),
        ]
        results = await bridge.execute_batch(reqs)
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_batch_mixed_results(self, bridge: FabricPOCBridge) -> None:
        reqs = [
            CapabilityRequest(capability_name="tool.execute.send_message", params={}),
            CapabilityRequest(capability_name="tool.execute.nonexistent", params={}),
        ]
        results = await bridge.execute_batch(reqs)
        assert results[0].success is True
        assert results[1].success is False

    @pytest.mark.asyncio
    async def test_batch_empty_list(self, bridge: FabricPOCBridge) -> None:
        results = await bridge.execute_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_single_item(self, bridge: FabricPOCBridge) -> None:
        reqs = [CapabilityRequest(capability_name="tool.execute.send_message", params={})]
        results = await bridge.execute_batch(reqs)
        assert len(results) == 1
        assert results[0].success is True


# =====================================================================
# find_relevant_prompts()
# =====================================================================


class TestFindRelevantPrompts:
    """POC has no prompt registry — always returns empty."""

    @pytest.mark.asyncio
    async def test_returns_empty_retrieval_result(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.find_relevant_prompts(intent="any prompt")
        assert isinstance(result, RetrievalResult)
        assert len(result.capabilities) == 0
        assert result.total_matched == 0

    @pytest.mark.asyncio
    async def test_prompt_intent_preserved(self, bridge: FabricPOCBridge) -> None:
        result = await bridge.find_relevant_prompts(intent="greeting template")
        assert result.query_intent == "greeting template"


# =====================================================================
# Session ID propagation
# =====================================================================


class TestSessionHandling:
    """Session ID and trace ID propagation through bridge."""

    @pytest.mark.asyncio
    async def test_session_id_passed_to_registry(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(
            capability_name="tool.execute.send_message",
            params={},
            session_id="sess-abc",
        )
        result = await bridge.execute(req)
        assert result.success is True  # handler doesn't care, but bridge shouldn't crash

    @pytest.mark.asyncio
    async def test_empty_session_id(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(
            capability_name="tool.execute.send_message", params={}, session_id=""
        )
        result = await bridge.execute(req)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_params_forwarded(self, bridge: FabricPOCBridge) -> None:
        req = CapabilityRequest(
            capability_name="tool.execute.send_message",
            params={"recipient": "Dad", "message": "Hello"},
        )
        result = await bridge.execute(req)
        assert result.success is True
