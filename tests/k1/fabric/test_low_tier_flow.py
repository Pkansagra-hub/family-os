"""
Epic 6.3.1 -- Test LOW tier execution flow (integration).

Full LOW tier pipeline through Fabric public API:
  register tool contract -> fabric.execute(tool request) ->
  verify CapabilityResult success -> verify events emitted
  (invoked + completed + learning_signal) -> verify metrics.

Tests with all three tool provider types:
  - MCP  (restaurant_booking fixture)
  - WASM (weather_api fixture)
  - BRIDGE (memory_store fixture)

MANDATORY per plan:
  1. ALL mutations/reads through fabric.execute() -- NEVER direct provider access.
  2. Uses FabricFactory.create_for_testing() with event capture.
  3. Real adapters only (test adapters are real, not mocks).
  4. Verify events via event adapter capture mode.

References:
  - fabric-implementation-plan.md Epic 6.3, Issue 6.3.1
  - No-Mock Testing Strategy (lines 1181-1300 of plan)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.events.fabric_events import (
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_INVOKED,
    TOPIC_CAPABILITY_REGISTERED,
    TOPIC_LEARNING_SIGNAL,
)
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory
from k1.fabric.types import CapabilityRequest, Tier
from tests.k1.fabric.helpers import assert_capability_result_success, wait_for_event

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _low_tier_request(
    capability_name: str,
    params: dict | None = None,
    *,
    caller: str = "test-low-tier",
) -> CapabilityRequest:
    """Build a LOW tier CapabilityRequest with valid fields."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params or {},
        tier=Tier.LOW.value,
        caller=caller,
    )


def _make_fabric() -> Fabric:
    """Create a Fabric with event capture for integration tests."""
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


# =========================================================================
# 6.3.1 -- LOW tier: MCP provider (restaurant_booking)
# =========================================================================


class TestLowTierMCPExecution:
    """
    LOW tier execution through MCP provider (restaurant_booking).

    Pipeline exercised:
      request -> emit_invoked -> resolve(mcp-opentable) -> build_context ->
      instantiate MCPProvider -> execute via TestMCPTransport ->
      validate_output -> emit_completed -> emit_learning_signal -> result
    """

    async def test_mcp_execute_returns_success(self) -> None:
        """Execute MCP capability and verify CapabilityResult success."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={
                "restaurant_name": "Chez Alice",
                "date": "2026-03-15",
                "party_size": 4,
            },
        )
        result = await fabric.execute(request)
        assert_capability_result_success(result, expected_provider="mcp-opentable")

    async def test_mcp_result_has_data(self) -> None:
        """MCP result data contains provider response."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-03-15", "party_size": 2},
        )
        result = await fabric.execute(request)
        assert result.data is not None
        assert isinstance(result.data, dict)

    async def test_mcp_result_has_timing(self) -> None:
        """Result includes duration_ms (pipeline overhead)."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-03-15", "party_size": 2},
        )
        result = await fabric.execute(request)
        assert result.duration_ms >= 0

    async def test_mcp_emits_invoked_event(self) -> None:
        """fabric.execute() emits TOPIC_CAPABILITY_INVOKED event."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-03-15", "party_size": 2},
        )
        await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_INVOKED)
        assert len(events) >= 1
        topic, payload = events[0]
        assert topic == TOPIC_CAPABILITY_INVOKED
        assert payload["capability_name"] == "tool.execute.restaurant_booking"

    async def test_mcp_emits_completed_event(self) -> None:
        """Successful execution emits TOPIC_CAPABILITY_COMPLETED event."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-03-15", "party_size": 2},
        )
        await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED)
        assert len(events) >= 1
        topic, payload = events[0]
        assert topic == TOPIC_CAPABILITY_COMPLETED
        assert payload["capability_name"] == "tool.execute.restaurant_booking"
        assert payload["provider_id"] == "mcp-opentable"
        assert "duration_ms" in payload

    async def test_mcp_emits_learning_signal(self) -> None:
        """Successful execution emits TOPIC_LEARNING_SIGNAL for K0 P09 feedback."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-03-15", "party_size": 2},
        )
        await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_LEARNING_SIGNAL)
        assert len(events) >= 1
        topic, payload = events[0]
        assert topic == TOPIC_LEARNING_SIGNAL
        assert payload["capability_name"] == "tool.execute.restaurant_booking"
        assert payload["success"] is True
        assert payload["provider_id"] == "mcp-opentable"

    async def test_mcp_invoked_event_has_trace_id(self) -> None:
        """FAB-09: All events carry cognitive_trace_id."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-03-15", "party_size": 2},
        )
        result = await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_INVOKED)
        _, payload = events[0]
        assert "cognitive_trace_id" in payload
        assert payload["cognitive_trace_id"] == request.trace_id

    async def test_mcp_completed_event_has_trace_id(self) -> None:
        """FAB-09: Completed event has cognitive_trace_id matching request."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-03-15", "party_size": 2},
        )
        await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED)
        _, payload = events[0]
        assert payload["cognitive_trace_id"] == request.trace_id

    async def test_mcp_result_trace_id_matches_request(self) -> None:
        """Result trace_id matches the request trace_id."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-03-15", "party_size": 2},
        )
        result = await fabric.execute(request)
        assert result.trace_id == request.trace_id

    async def test_mcp_result_request_id_matches(self) -> None:
        """Result request_id matches the request."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-03-15", "party_size": 2},
        )
        result = await fabric.execute(request)
        assert result.request_id == request.request_id

    async def test_mcp_full_event_sequence(self) -> None:
        """Full event sequence: invoked -> completed -> learning_signal."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-03-15", "party_size": 2},
        )
        await fabric.execute(request)

        invoked = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_INVOKED)
        completed = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED)
        learning = wait_for_event(fabric.event_port, TOPIC_LEARNING_SIGNAL)

        assert len(invoked) >= 1
        assert len(completed) >= 1
        assert len(learning) >= 1


# =========================================================================
# 6.3.1 -- LOW tier: WASM provider (weather_api)
# =========================================================================


class TestLowTierWASMExecution:
    """
    LOW tier execution through WASM provider (weather_api).

    Pipeline exercised:
      request -> emit_invoked -> resolve(wasm-weather) -> build_context ->
      instantiate WASMProvider -> execute via TestWASMRuntime ->
      validate_output -> emit_completed -> emit_learning_signal -> result
    """

    async def test_wasm_execute_returns_success(self) -> None:
        """Execute WASM capability and verify CapabilityResult success."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.read.weather_api",
            params={"location": "San Francisco"},
        )
        result = await fabric.execute(request)
        assert_capability_result_success(result, expected_provider="wasm-weather")

    async def test_wasm_result_has_data(self) -> None:
        """WASM result data contains provider response."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.read.weather_api",
            params={"location": "Portland"},
        )
        result = await fabric.execute(request)
        assert result.data is not None
        assert isinstance(result.data, dict)

    async def test_wasm_emits_invoked_event(self) -> None:
        """fabric.execute() emits invoked event for WASM capability."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.read.weather_api",
            params={"location": "Portland"},
        )
        await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_INVOKED)
        assert len(events) >= 1
        _, payload = events[0]
        assert payload["capability_name"] == "tool.read.weather_api"

    async def test_wasm_emits_completed_event(self) -> None:
        """Successful WASM execution emits completed event."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.read.weather_api",
            params={"location": "Portland"},
        )
        await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED)
        assert len(events) >= 1
        _, payload = events[0]
        assert payload["capability_name"] == "tool.read.weather_api"
        assert payload["provider_id"] == "wasm-weather"

    async def test_wasm_emits_learning_signal(self) -> None:
        """WASM execution emits learning signal."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.read.weather_api",
            params={"location": "Portland"},
        )
        await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_LEARNING_SIGNAL)
        assert len(events) >= 1
        _, payload = events[0]
        assert payload["capability_name"] == "tool.read.weather_api"
        assert payload["success"] is True

    async def test_wasm_trace_id_propagated(self) -> None:
        """FAB-09: Trace ID propagated through WASM pipeline."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.read.weather_api",
            params={"location": "Portland"},
        )
        result = await fabric.execute(request)
        assert result.trace_id == request.trace_id

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED)
        _, payload = events[0]
        assert payload["cognitive_trace_id"] == request.trace_id


# =========================================================================
# 6.3.1 -- LOW tier: BRIDGE provider (memory_store)
# =========================================================================


class TestLowTierBridgeExecution:
    """
    LOW tier execution through Bridge provider (memory_store).

    Pipeline exercised:
      request -> emit_invoked -> resolve(bridge-k0-memory) -> build_context ->
      instantiate BridgeProvider -> execute via TestBridgeAdapter ->
      validate_output -> emit_completed -> emit_learning_signal -> result
    """

    async def test_bridge_execute_returns_success(self) -> None:
        """Execute bridge capability and verify success."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.memory_store",
            params={"key": "greeting", "value": "hello world"},
        )
        result = await fabric.execute(request)
        assert_capability_result_success(result, expected_provider="bridge-k0-memory")

    async def test_bridge_result_has_data(self) -> None:
        """Bridge result contains response data from TestBridgeAdapter."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.memory_store",
            params={"key": "test-key", "value": "test-val"},
        )
        result = await fabric.execute(request)
        assert result.data is not None
        assert isinstance(result.data, dict)

    async def test_bridge_emits_invoked_event(self) -> None:
        """Bridge execution emits invoked event."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.memory_store",
            params={"key": "k", "value": "v"},
        )
        await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_INVOKED)
        assert len(events) >= 1
        _, payload = events[0]
        assert payload["capability_name"] == "tool.execute.memory_store"

    async def test_bridge_emits_completed_event(self) -> None:
        """Bridge execution emits completed event with provider_id."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.memory_store",
            params={"key": "k", "value": "v"},
        )
        await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED)
        assert len(events) >= 1
        _, payload = events[0]
        assert payload["capability_name"] == "tool.execute.memory_store"
        assert payload["provider_id"] == "bridge-k0-memory"

    async def test_bridge_emits_learning_signal(self) -> None:
        """Bridge execution emits learning signal."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.memory_store",
            params={"key": "k", "value": "v"},
        )
        await fabric.execute(request)

        events = wait_for_event(fabric.event_port, TOPIC_LEARNING_SIGNAL)
        assert len(events) >= 1
        _, payload = events[0]
        assert payload["capability_name"] == "tool.execute.memory_store"
        assert payload["success"] is True

    async def test_bridge_trace_id_propagated(self) -> None:
        """FAB-09: Trace ID propagated through bridge pipeline."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.memory_store",
            params={"key": "k", "value": "v"},
        )
        result = await fabric.execute(request)
        assert result.trace_id == request.trace_id

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED)
        _, payload = events[0]
        assert payload["cognitive_trace_id"] == request.trace_id


# =========================================================================
# 6.3.1 -- LOW tier: Cross-provider shared behaviors
# =========================================================================


class TestLowTierCrossProvider:
    """
    Verify behaviors shared across all LOW tier provider types.

    Uses different providers to confirm the pipeline is consistent:
    same event sequence, same result shape, same trace_id propagation.
    """

    @pytest.mark.parametrize(
        "capability_name,params,expected_provider",
        [
            (
                "tool.execute.restaurant_booking",
                {"restaurant_name": "Test", "date": "2026-01-01", "party_size": 2},
                "mcp-opentable",
            ),
            (
                "tool.read.weather_api",
                {"location": "Seattle"},
                "wasm-weather",
            ),
            (
                "tool.execute.memory_store",
                {"key": "k", "value": "v"},
                "bridge-k0-memory",
            ),
        ],
        ids=["MCP", "WASM", "BRIDGE"],
    )
    async def test_all_providers_return_success(
        self,
        capability_name: str,
        params: dict,
        expected_provider: str,
    ) -> None:
        """All provider types return successful CapabilityResult."""
        fabric = _make_fabric()
        request = _low_tier_request(capability_name, params)
        result = await fabric.execute(request)
        assert_capability_result_success(result, expected_provider=expected_provider)

    @pytest.mark.parametrize(
        "capability_name,params",
        [
            (
                "tool.execute.restaurant_booking",
                {"restaurant_name": "Test", "date": "2026-01-01", "party_size": 2},
            ),
            ("tool.read.weather_api", {"location": "Seattle"}),
            ("tool.execute.memory_store", {"key": "k", "value": "v"}),
        ],
        ids=["MCP", "WASM", "BRIDGE"],
    )
    async def test_all_providers_emit_full_event_sequence(
        self,
        capability_name: str,
        params: dict,
    ) -> None:
        """All providers emit invoked + completed + learning_signal."""
        fabric = _make_fabric()
        request = _low_tier_request(capability_name, params)
        await fabric.execute(request)

        invoked = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_INVOKED)
        completed = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED)
        learning = wait_for_event(fabric.event_port, TOPIC_LEARNING_SIGNAL)

        assert len(invoked) >= 1
        assert len(completed) >= 1
        assert len(learning) >= 1

    async def test_unregistered_capability_fails_gracefully(self) -> None:
        """Executing an unregistered capability returns a failure result, not an exception."""
        fabric = _make_fabric()
        request = _low_tier_request(
            "tool.execute.nonexistent_capability",
            params={"a": 1},
        )
        result = await fabric.execute(request)
        assert result.success is False
        assert result.error is not None

    async def test_registered_events_emitted_during_construction(self) -> None:
        """FabricFactory emits TOPIC_CAPABILITY_REGISTERED for auto-loaded fixtures."""
        fabric = _make_fabric()
        events = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_REGISTERED)
        # At least the 7 YAML fixtures should have emitted registration events
        assert len(events) >= 3, f"Expected at least 3 registration events, got {len(events)}"

    async def test_multiple_sequential_executions(self) -> None:
        """FAB-03: Execute same capability twice, both succeed independently."""
        fabric = _make_fabric()
        r1 = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "A", "date": "2026-01-01", "party_size": 2},
        )
        r2 = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "B", "date": "2026-02-01", "party_size": 4},
        )
        result1 = await fabric.execute(r1)
        result2 = await fabric.execute(r2)
        assert result1.success is True
        assert result2.success is True
        assert result1.request_id != result2.request_id

    async def test_different_provider_types_same_fabric(self) -> None:
        """Single Fabric instance handles MCP, WASM, and BRIDGE sequentially."""
        fabric = _make_fabric()

        r_mcp = _low_tier_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Test", "date": "2026-01-01", "party_size": 2},
        )
        r_wasm = _low_tier_request(
            "tool.read.weather_api",
            params={"location": "Denver"},
        )
        r_bridge = _low_tier_request(
            "tool.execute.memory_store",
            params={"key": "k1", "value": "v1"},
        )

        res_mcp = await fabric.execute(r_mcp)
        res_wasm = await fabric.execute(r_wasm)
        res_bridge = await fabric.execute(r_bridge)

        assert res_mcp.success is True
        assert res_mcp.provider_id == "mcp-opentable"
        assert res_wasm.success is True
        assert res_wasm.provider_id == "wasm-weather"
        assert res_bridge.success is True
        assert res_bridge.provider_id == "bridge-k0-memory"
