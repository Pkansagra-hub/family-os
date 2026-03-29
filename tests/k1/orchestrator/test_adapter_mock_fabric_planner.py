"""
Tests for MockFabricAdapter (6.1.9) and MockPlannerAdapter (6.1.10).

Coverage targets:
  MockFabricAdapter:
    - Default success on execute()
    - Scripted result returned
    - Scripted error raises AdapterException
    - Scripted timeout (asyncio.sleep) precedes response
    - execute_batch delegates to execute()
    - query_registry returns entry or None
    - query_registry_by_category prefix matching
    - call_log populated
    - assert_called / assert_not_called
    - register_capability
    - reset clears all state

  MockPlannerAdapter:
    - request_plan returns ACCEPTED by default
    - request_plan returns REJECTED for scripted failures
    - script_plan + callback delivers plan asynchronously
    - cancel_plan logs request_id
    - micro_replan returns scripted plan or None
    - assert_plan_requested / assert_cancel_requested / assert_micro_replan_requested
    - reset clears all state
"""

from __future__ import annotations

import asyncio
from typing import List

import pytest

from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import (
    AdapterError,
    CommittedPlan,
    ErrorSeverity,
    MicroReplanRequest,
    PlanRequest,
    PlanStep,
    RegistryEntry,
)

# ===================================================================
# Helpers
# ===================================================================


def _cap_request(name: str = "tool.echo", **kw) -> CapabilityRequest:
    """Create a CapabilityRequest with sensible defaults."""
    return CapabilityRequest(capability_name=name, **kw)


def _plan_request(
    intent: str = "test-intent",
    trace_id: str = "t-1",
    request_id: str = "r-1",
) -> PlanRequest:
    return PlanRequest(intent=intent, trace_id=trace_id, request_id=request_id)


def _plan_step(step_id: str = "s1", cap: str = "tool.test") -> PlanStep:
    return PlanStep(id=step_id, capability=cap)


def _committed_plan(
    plan_id: str = "p-1",
    request_id: str = "r-1",
    intent: str = "test-intent",
    trace_id: str = "t-1",
) -> CommittedPlan:
    return CommittedPlan(
        plan_id=plan_id,
        request_id=request_id,
        intent=intent,
        steps=[_plan_step()],
        trace_id=trace_id,
    )


def _micro_replan_request(
    original_plan_id: str = "p-1",
    trace_id: str = "t-1",
    request_id: str = "mr-1",
) -> MicroReplanRequest:
    return MicroReplanRequest(
        original_plan_id=original_plan_id,
        completed_results={},
        remaining_steps=[_plan_step("s2", "tool.other")],
        trace_id=trace_id,
        request_id=request_id,
    )


# ===================================================================
# MockFabricAdapter (6.1.9)
# ===================================================================


class TestMockFabricAdapterDefaultBehavior:
    """6.1.9 -- default behavior returns generic success."""

    @pytest.mark.asyncio
    async def test_default_success(self):
        adapter = MockFabricAdapter()
        req = _cap_request("tool.echo")
        result = await adapter.execute(req)
        assert result.success is True
        assert result.request_id == req.request_id

    @pytest.mark.asyncio
    async def test_default_provider_is_mock(self):
        adapter = MockFabricAdapter()
        result = await adapter.execute(_cap_request())
        assert result.provider_id == "mock"

    @pytest.mark.asyncio
    async def test_default_data_is_empty_dict(self):
        adapter = MockFabricAdapter()
        result = await adapter.execute(_cap_request())
        assert result.data == {}


class TestMockFabricAdapterScriptedResults:
    """6.1.9 -- scripted results."""

    @pytest.mark.asyncio
    async def test_scripted_result_returned(self):
        adapter = MockFabricAdapter()
        expected = CapabilityResult.success_result(
            request_id="r-1",
            data={"answer": 42},
            provider_id="test-provider",
            trace_id="t-1",
        )
        adapter.script_result("tool.echo", expected)
        result = await adapter.execute(_cap_request("tool.echo"))
        assert result is expected

    @pytest.mark.asyncio
    async def test_unscripted_capability_still_succeeds(self):
        adapter = MockFabricAdapter()
        adapter.script_result(
            "tool.other",
            CapabilityResult.success_result(
                request_id="x",
                data={},
                provider_id="x",
                trace_id="x",
            ),
        )
        result = await adapter.execute(_cap_request("tool.echo"))
        assert result.success is True


class TestMockFabricAdapterScriptedErrors:
    """6.1.9 -- scripted errors raise AdapterException."""

    @pytest.mark.asyncio
    async def test_scripted_error_raises_adapter_exception(self):
        adapter = MockFabricAdapter()
        err = AdapterError(
            adapter_name="MockFabricAdapter",
            operation="execute",
            error_code="TEST_ERR",
            error_message="boom",
            severity=ErrorSeverity.TERMINAL,
        )
        adapter.script_error("tool.explode", err)
        with pytest.raises(AdapterException) as exc_info:
            await adapter.execute(_cap_request("tool.explode"))
        assert exc_info.value.error_code == "TEST_ERR"

    @pytest.mark.asyncio
    async def test_scripted_error_preserves_detail(self):
        adapter = MockFabricAdapter()
        err = AdapterError(
            adapter_name="Mock",
            operation="execute",
            error_code="E1",
            error_message="detail",
            severity=ErrorSeverity.RECOVERABLE,
        )
        adapter.script_error("cap", err)
        with pytest.raises(AdapterException) as exc_info:
            await adapter.execute(_cap_request("cap"))
        assert exc_info.value.detail is err


class TestMockFabricAdapterScriptedTimeouts:
    """6.1.9 -- scripted timeouts with asyncio.sleep."""

    @pytest.mark.asyncio
    async def test_scripted_timeout_delays_response(self):
        adapter = MockFabricAdapter()
        adapter.script_timeout("tool.slow", 0.05)
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        result = await adapter.execute(_cap_request("tool.slow"))
        elapsed = loop.time() - t0
        assert elapsed >= 0.04  # allow small timing slack
        assert result.success is True


class TestMockFabricAdapterBatch:
    """6.1.9 -- execute_batch delegates to execute()."""

    @pytest.mark.asyncio
    async def test_batch_returns_results_per_request(self):
        adapter = MockFabricAdapter()
        reqs = [_cap_request("a"), _cap_request("b"), _cap_request("c")]
        results = await adapter.execute_batch(reqs)
        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_batch_logs_all_calls(self):
        adapter = MockFabricAdapter()
        reqs = [_cap_request("a"), _cap_request("b")]
        await adapter.execute_batch(reqs)
        assert len(adapter.call_log) == 2

    @pytest.mark.asyncio
    async def test_batch_propagates_scripted_error(self):
        adapter = MockFabricAdapter()
        adapter.script_error(
            "fail",
            AdapterError(
                adapter_name="Mock",
                operation="execute",
                error_code="BATCH_ERR",
                error_message="fail in batch",
                severity=ErrorSeverity.TERMINAL,
            ),
        )
        reqs = [_cap_request("ok"), _cap_request("fail")]
        with pytest.raises(AdapterException):
            await adapter.execute_batch(reqs)


class TestMockFabricAdapterRegistry:
    """6.1.9 -- query_registry and query_registry_by_category."""

    @pytest.mark.asyncio
    async def test_query_registry_returns_entry(self):
        adapter = MockFabricAdapter()
        entry = RegistryEntry(
            name="tool.echo",
            provider_type="mock",
            safety_band_min="0.0",
            availability="1.0",
        )
        adapter.register_capability("tool.echo", entry)
        result = await adapter.query_registry("tool.echo")
        assert result is entry

    @pytest.mark.asyncio
    async def test_query_registry_returns_none_when_missing(self):
        adapter = MockFabricAdapter()
        result = await adapter.query_registry("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_by_category_prefix_match(self):
        adapter = MockFabricAdapter()
        e1 = RegistryEntry(
            name="tool.a", provider_type="m", safety_band_min="0.0", availability="1.0"
        )
        e2 = RegistryEntry(
            name="tool.b", provider_type="m", safety_band_min="0.0", availability="1.0"
        )
        e3 = RegistryEntry(
            name="other.c", provider_type="m", safety_band_min="0.0", availability="1.0"
        )
        adapter.register_capability("tool.a", e1)
        adapter.register_capability("tool.b", e2)
        adapter.register_capability("other.c", e3)
        results = await adapter.query_registry_by_category("tool.")
        assert len(results) == 2
        assert e1 in results
        assert e2 in results

    @pytest.mark.asyncio
    async def test_query_by_category_empty_on_no_match(self):
        adapter = MockFabricAdapter()
        results = await adapter.query_registry_by_category("nope.")
        assert results == []


class TestMockFabricAdapterCallLog:
    """6.1.9 -- call logging and assertions."""

    @pytest.mark.asyncio
    async def test_call_log_populated(self):
        adapter = MockFabricAdapter()
        req = _cap_request("tool.x")
        await adapter.execute(req)
        assert len(adapter.call_log) == 1
        assert adapter.call_log[0] is req

    @pytest.mark.asyncio
    async def test_assert_called_passes(self):
        adapter = MockFabricAdapter()
        await adapter.execute(_cap_request("tool.x"))
        adapter.assert_called("tool.x", times=1)

    @pytest.mark.asyncio
    async def test_assert_called_fails(self):
        adapter = MockFabricAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_called("tool.x", times=1)

    @pytest.mark.asyncio
    async def test_assert_not_called_passes(self):
        adapter = MockFabricAdapter()
        adapter.assert_not_called("tool.x")

    @pytest.mark.asyncio
    async def test_assert_not_called_fails(self):
        adapter = MockFabricAdapter()
        await adapter.execute(_cap_request("tool.x"))
        with pytest.raises(AssertionError):
            adapter.assert_not_called("tool.x")


class TestMockFabricAdapterReset:
    """6.1.9 -- reset clears all state."""

    @pytest.mark.asyncio
    async def test_reset_clears_everything(self):
        adapter = MockFabricAdapter()
        adapter.script_result(
            "a",
            CapabilityResult.success_result(
                request_id="r",
                data={},
                provider_id="p",
                trace_id="t",
            ),
        )
        adapter.script_error(
            "b",
            AdapterError(
                adapter_name="M",
                operation="e",
                error_code="E",
                error_message="m",
                severity=ErrorSeverity.RECOVERABLE,
            ),
        )
        adapter.script_timeout("c", 1.0)
        adapter.register_capability(
            "d",
            RegistryEntry(
                name="d",
                provider_type="m",
                safety_band_min="0.0",
                availability="1.0",
            ),
        )
        await adapter.execute(_cap_request("a"))
        adapter.reset()
        assert adapter.scripted_results == {}
        assert adapter.scripted_errors == {}
        assert adapter.scripted_timeouts == {}
        assert adapter.call_log == []
        assert adapter.registry == {}


# ===================================================================
# MockPlannerAdapter (6.1.10)
# ===================================================================


class TestMockPlannerAdapterRequestPlan:
    """6.1.10 -- request_plan behavior."""

    @pytest.mark.asyncio
    async def test_default_accepted(self):
        adapter = MockPlannerAdapter()
        ack = await adapter.request_plan(_plan_request())
        assert ack.status == "ACCEPTED"
        assert ack.request_id == "r-1"

    @pytest.mark.asyncio
    async def test_scripted_failure_rejected(self):
        adapter = MockPlannerAdapter()
        adapter.script_failure("r-1")
        ack = await adapter.request_plan(_plan_request(request_id="r-1"))
        assert ack.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_request_logged(self):
        adapter = MockPlannerAdapter()
        req = _plan_request()
        await adapter.request_plan(req)
        assert len(adapter.request_log) == 1
        assert adapter.request_log[0] is req

    @pytest.mark.asyncio
    async def test_multiple_requests_logged(self):
        adapter = MockPlannerAdapter()
        await adapter.request_plan(_plan_request(request_id="r-1"))
        await adapter.request_plan(_plan_request(request_id="r-2"))
        assert len(adapter.request_log) == 2


class TestMockPlannerAdapterPlanDelivery:
    """6.1.10 -- async plan delivery via callback."""

    @pytest.mark.asyncio
    async def test_plan_delivered_via_callback(self):
        delivered: List[CommittedPlan] = []
        adapter = MockPlannerAdapter(plan_callback=lambda p: delivered.append(p))
        plan = _committed_plan(request_id="r-1")
        adapter.script_plan("r-1", plan)
        await adapter.request_plan(_plan_request(request_id="r-1"))
        # Give async delivery time to complete
        await asyncio.sleep(0.05)
        assert len(delivered) == 1
        assert delivered[0] is plan

    @pytest.mark.asyncio
    async def test_no_delivery_without_callback(self):
        adapter = MockPlannerAdapter()  # No callback
        adapter.script_plan("r-1", _committed_plan(request_id="r-1"))
        ack = await adapter.request_plan(_plan_request(request_id="r-1"))
        assert ack.status == "ACCEPTED"
        # No crash, no delivery

    @pytest.mark.asyncio
    async def test_no_delivery_without_scripted_plan(self):
        delivered: List[CommittedPlan] = []
        adapter = MockPlannerAdapter(plan_callback=lambda p: delivered.append(p))
        await adapter.request_plan(_plan_request(request_id="r-1"))
        await asyncio.sleep(0.05)
        assert len(delivered) == 0

    @pytest.mark.asyncio
    async def test_async_callback_supported(self):
        delivered: List[CommittedPlan] = []

        async def async_cb(plan: CommittedPlan):
            delivered.append(plan)

        adapter = MockPlannerAdapter(plan_callback=async_cb)
        adapter.script_plan("r-1", _committed_plan(request_id="r-1"))
        await adapter.request_plan(_plan_request(request_id="r-1"))
        await asyncio.sleep(0.05)
        assert len(delivered) == 1


class TestMockPlannerAdapterCancelPlan:
    """6.1.10 -- cancel_plan logging."""

    @pytest.mark.asyncio
    async def test_cancel_logged(self):
        adapter = MockPlannerAdapter()
        await adapter.cancel_plan("r-1")
        assert "r-1" in adapter.cancel_log

    @pytest.mark.asyncio
    async def test_multiple_cancels_logged(self):
        adapter = MockPlannerAdapter()
        await adapter.cancel_plan("r-1")
        await adapter.cancel_plan("r-2")
        assert len(adapter.cancel_log) == 2


class TestMockPlannerAdapterMicroReplan:
    """6.1.10 -- micro_replan behavior."""

    @pytest.mark.asyncio
    async def test_scripted_micro_replan_returns_plan(self):
        adapter = MockPlannerAdapter()
        plan = _committed_plan(plan_id="p-new", request_id="mr-1")
        adapter.script_micro_replan("mr-1", plan)
        req = _micro_replan_request(request_id="mr-1")
        result = await adapter.micro_replan(req)
        assert result is plan

    @pytest.mark.asyncio
    async def test_unscripted_micro_replan_returns_none(self):
        adapter = MockPlannerAdapter()
        req = _micro_replan_request(request_id="mr-1")
        result = await adapter.micro_replan(req)
        assert result is None

    @pytest.mark.asyncio
    async def test_micro_replan_logged(self):
        adapter = MockPlannerAdapter()
        req = _micro_replan_request()
        await adapter.micro_replan(req)
        assert len(adapter.micro_replan_log) == 1
        assert adapter.micro_replan_log[0] is req


class TestMockPlannerAdapterAssertions:
    """6.1.10 -- test helper assertions."""

    @pytest.mark.asyncio
    async def test_assert_plan_requested_passes(self):
        adapter = MockPlannerAdapter()
        await adapter.request_plan(_plan_request())
        adapter.assert_plan_requested(count=1)

    @pytest.mark.asyncio
    async def test_assert_plan_requested_fails(self):
        adapter = MockPlannerAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_plan_requested(count=1)

    @pytest.mark.asyncio
    async def test_assert_cancel_requested_passes(self):
        adapter = MockPlannerAdapter()
        await adapter.cancel_plan("r-1")
        adapter.assert_cancel_requested("r-1")

    @pytest.mark.asyncio
    async def test_assert_cancel_requested_fails(self):
        adapter = MockPlannerAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_cancel_requested("r-1")

    @pytest.mark.asyncio
    async def test_assert_micro_replan_requested_passes(self):
        adapter = MockPlannerAdapter()
        await adapter.micro_replan(_micro_replan_request())
        adapter.assert_micro_replan_requested(count=1)

    @pytest.mark.asyncio
    async def test_assert_micro_replan_requested_fails(self):
        adapter = MockPlannerAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_micro_replan_requested(count=1)


class TestMockPlannerAdapterReset:
    """6.1.10 -- reset clears all state."""

    @pytest.mark.asyncio
    async def test_reset_clears_everything(self):
        adapter = MockPlannerAdapter()
        adapter.script_plan("r-1", _committed_plan())
        adapter.script_failure("r-2")
        adapter.script_micro_replan("r-3", _committed_plan(plan_id="p2", request_id="r-3"))
        await adapter.request_plan(_plan_request())
        await adapter.cancel_plan("r-1")
        await adapter.micro_replan(_micro_replan_request())
        adapter.reset()
        assert adapter.scripted_plans == {}
        assert adapter.scripted_failures == set()
        assert adapter.scripted_micro_replans == {}
        assert adapter.request_log == []
        assert adapter.cancel_log == []
        assert adapter.micro_replan_log == []
