"""
Epic 6.3.9 -- Test statelessness (FAB-03).

Covers:
  - Execute capability A, then capability B: no state carried between.
  - Fabric instance has no request-specific state after execution.
  - Execute same capability 100 times: each invocation is independent.
  - Concurrent executions do not interfere with each other.
  - CapabilityResult from each execution is self-contained.
  - Events from different executions carry different trace_ids.
  - Failed executions do not leak state to subsequent calls.

NO MOCKS -- all tests use FabricFactory.create_for_testing() with real adapters.

References:
  - fabric-implementation-plan.md Epic 6.3.9
  - fabric_discussion.md Section 15 (Statelessness)
  - FAB-03 (Fabric is stateless per request)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from k1.fabric.events import TOPIC_CAPABILITY_INVOKED
from k1.fabric.factory import FabricFactory
from k1.fabric.types import CapabilityContract, CapabilityRequest, InputSpec, Tier
from tests.k1.fabric.helpers import (
    assert_capability_result_success,
    register_contract_with_provider,
)

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fabric():
    """Create a Fabric with event capture for statelessness tests."""
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


def _request(
    capability_name: str,
    params: dict | None = None,
    *,
    caller: str = "test-stateless",
    session_id: str = "",
) -> CapabilityRequest:
    """Build a capability request."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params or {},
        tier=Tier.LOW.value,
        caller=caller,
        session_id=session_id,
    )


def _register_test_cap(
    fabric,
    name: str = "tool.execute.stateless_test",
    provider_id: str = "mcp-stateless",
) -> CapabilityContract:
    """Register a test capability and configure its MCP response."""
    contract = CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["TEST"],
        description="Statelessness test capability",
        capabilities=[name],
        provider_type="MCP",
        provider_id=provider_id,
        required_inputs=[InputSpec(name="query", type="STRING", description="Test query input")],
        output={"type": "object"},
    )
    register_contract_with_provider(fabric, contract)

    # Default TestMCPTransport returns success for any tool
    return contract


# =========================================================================
# 6.3.9a -- No state carried between invocations
# =========================================================================


class TestNoStateBetweenInvocations:
    """
    Execute capability A, then capability B: verify no state carries over.
    """

    async def test_sequential_capabilities_independent(self) -> None:
        """Execute A then B: each result is self-contained."""
        fabric = _make_fabric()

        # Register two different capabilities
        _register_test_cap(fabric, "tool.execute.cap_a", "mcp-a")
        _register_test_cap(fabric, "tool.execute.cap_b", "mcp-b")

        result_a = await fabric.execute(
            _request(
                "tool.execute.cap_a",
                {"query": "hello-a"},
            )
        )
        result_b = await fabric.execute(
            _request(
                "tool.execute.cap_b",
                {"query": "hello-b"},
            )
        )

        assert_capability_result_success(result_a, expected_provider="mcp-a")
        assert_capability_result_success(result_b, expected_provider="mcp-b")

        # Results are independent -- different request_ids
        assert result_a.request_id != result_b.request_id

    async def test_result_does_not_reference_prior_execution(self) -> None:
        """Result B has no data from result A (independent request_ids, providers)."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.first_exec", "mcp-first")
        _register_test_cap(fabric, "tool.execute.second_exec", "mcp-second")

        result_1 = await fabric.execute(_request("tool.execute.first_exec"))
        result_2 = await fabric.execute(_request("tool.execute.second_exec"))

        # Different providers, different request_ids -- independent results
        assert result_1.request_id != result_2.request_id
        assert result_1.provider_id == "mcp-first"
        assert result_2.provider_id == "mcp-second"

    async def test_different_params_yield_independent_results(self) -> None:
        """Same capability with different params: results are independent."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.param_test", "mcp-param")

        result_x = await fabric.execute(
            _request(
                "tool.execute.param_test",
                {"query": "x-data"},
            )
        )
        result_y = await fabric.execute(
            _request(
                "tool.execute.param_test",
                {"query": "y-data"},
            )
        )

        assert_capability_result_success(result_x)
        assert_capability_result_success(result_y)
        # Same provider, but independent executions
        assert result_x.request_id != result_y.request_id

    async def test_different_sessions_no_crossbleed(self) -> None:
        """Different session_ids do not cross-contaminate."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.session_test", "mcp-sess")

        result_s1 = await fabric.execute(
            _request(
                "tool.execute.session_test",
                session_id="session-alpha",
            )
        )
        result_s2 = await fabric.execute(
            _request(
                "tool.execute.session_test",
                session_id="session-beta",
            )
        )

        assert_capability_result_success(result_s1)
        assert_capability_result_success(result_s2)
        assert result_s1.request_id != result_s2.request_id


# =========================================================================
# 6.3.9b -- Fabric has no request-specific state after execution
# =========================================================================


class TestNoResidualState:
    """
    Verify Fabric instance retains no request-specific state after execution.
    """

    async def test_facade_has_no_request_state(self) -> None:
        """CapabilityFabric has no per-request attributes after execute."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.residual_test", "mcp-residual")

        await fabric.execute(_request("tool.execute.residual_test"))

        # The facade (CapabilityFabric) should have no request-specific state
        facade = fabric.facade
        assert not hasattr(facade, "_last_request")
        assert not hasattr(facade, "_last_result")
        assert not hasattr(facade, "_current_context")

    async def test_circuit_breakers_persist_but_not_request_state(self) -> None:
        """Circuit breakers are system state (ok), not request state."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.cb_state_test", "mcp-cb-state")

        await fabric.execute(_request("tool.execute.cb_state_test"))

        # circuit_breakers dict is system-level, not request-level
        cbs = fabric.facade._circuit_breakers
        assert isinstance(cbs, dict)
        # No request-specific entries leaked
        # (CBs are keyed by provider_id, not request_id)
        for key in cbs:
            assert not key.startswith("req-")

    async def test_event_port_accumulates_but_no_request_coupling(self) -> None:
        """Event port captures events, but events are independent."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.event_state_test", "mcp-evt")

        await fabric.execute(_request("tool.execute.event_state_test"))

        events = fabric.event_port.get_captured()
        assert len(events) > 0
        # Each event is a standalone (topic, payload) tuple
        for topic, payload in events:
            assert isinstance(topic, str)
            assert isinstance(payload, dict)


# =========================================================================
# 6.3.9c -- 100 independent executions
# =========================================================================


class TestBulkIndependence:
    """
    Execute same capability 100 times: each invocation is independent.
    """

    async def test_100_sequential_executions_independent(self) -> None:
        """100 sequential executions each produce unique request_ids."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.bulk_test", "mcp-bulk")

        request_ids = set()
        for i in range(100):
            result = await fabric.execute(
                _request(
                    "tool.execute.bulk_test",
                    {"query": f"iter-{i}"},
                )
            )
            assert_capability_result_success(result)
            request_ids.add(result.request_id)

        # All 100 executions have unique request_ids
        assert len(request_ids) == 100

    async def test_50_executions_all_succeed(self) -> None:
        """50 sequential executions all succeed with correct provider."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.fifty_test", "mcp-fifty")

        results = []
        for i in range(50):
            result = await fabric.execute(_request("tool.execute.fifty_test"))
            results.append(result)

        for result in results:
            assert_capability_result_success(result, expected_provider="mcp-fifty")

    async def test_bulk_events_have_unique_trace_ids(self) -> None:
        """Each execution emits events with unique trace_ids."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.trace_test", "mcp-trace")

        N = 20
        for i in range(N):
            await fabric.execute(_request("tool.execute.trace_test"))

        invoked = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
        trace_ids = {payload.get("cognitive_trace_id") for _, payload in invoked}
        # Each invocation has a unique cognitive_trace_id (FAB-09)
        assert len(trace_ids) >= N


# =========================================================================
# 6.3.9d -- Concurrent executions do not interfere
# =========================================================================


class TestConcurrencyIsolation:
    """
    Concurrent executions are isolated from each other.
    """

    async def test_concurrent_executions_independent(self) -> None:
        """Multiple concurrent executions produce independent results."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.conc_test", "mcp-conc")

        tasks = [
            fabric.execute(
                _request(
                    "tool.execute.conc_test",
                    {"query": f"concurrent-{i}"},
                )
            )
            for i in range(10)
        ]
        results = await asyncio.gather(*tasks)

        request_ids = {r.request_id for r in results}
        assert len(request_ids) == 10

        for r in results:
            assert_capability_result_success(r, expected_provider="mcp-conc")

    async def test_concurrent_different_capabilities(self) -> None:
        """Concurrent execution of DIFFERENT capabilities are isolated."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.conc_a", "mcp-conc-a")
        _register_test_cap(fabric, "tool.execute.conc_b", "mcp-conc-b")

        tasks = [
            fabric.execute(_request("tool.execute.conc_a")),
            fabric.execute(_request("tool.execute.conc_b")),
            fabric.execute(_request("tool.execute.conc_a")),
            fabric.execute(_request("tool.execute.conc_b")),
        ]
        results = await asyncio.gather(*tasks)

        for r in results:
            assert r.success is True


# =========================================================================
# 6.3.9e -- Failed executions do not leak state
# =========================================================================


class TestFailureIsolation:
    """
    Failed execution does not leak state to subsequent calls.
    """

    async def test_failure_then_success_independent(self) -> None:
        """Failed execution followed by success: success is unaffected."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.after_fail", "mcp-after-fail")

        # Execute a capability that doesn't exist (should fail)
        fail_result = await fabric.execute(_request("tool.execute.nonexistent"))
        assert fail_result.success is False

        # Execute a registered capability (should succeed)
        ok_result = await fabric.execute(_request("tool.execute.after_fail"))
        assert_capability_result_success(ok_result, expected_provider="mcp-after-fail")

    async def test_multiple_failures_dont_accumulate(self) -> None:
        """Multiple failures don't poison subsequent executions."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.post_multi_fail", "mcp-post")

        # Cause 5 failures
        for _ in range(5):
            result = await fabric.execute(_request("tool.execute.missing"))
            assert result.success is False

        # Success still works
        ok = await fabric.execute(_request("tool.execute.post_multi_fail"))
        assert_capability_result_success(ok)

    async def test_interleaved_fail_success(self) -> None:
        """Interleaved failures and successes are independent."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.interleave_ok", "mcp-interleave")

        results = []
        for i in range(10):
            if i % 2 == 0:
                r = await fabric.execute(_request("tool.execute.interleave_ok"))
            else:
                r = await fabric.execute(_request("tool.execute.nonexistent"))
            results.append(r)

        # Even indices succeed, odd indices fail
        for i, r in enumerate(results):
            if i % 2 == 0:
                assert r.success is True
            else:
                assert r.success is False
