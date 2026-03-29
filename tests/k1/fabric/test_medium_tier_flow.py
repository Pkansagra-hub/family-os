"""
Epic 6.3.2 -- Test MEDIUM tier execution flow (integration).

MEDIUM tier pipeline: register 2+ tool contracts, execute both via
fabric.execute_batch() with PARALLEL and SEQUENTIAL strategies.
Verify both results, verify events for each.

Tests with:
  - restaurant_booking (MCP) + weather_api (WASM)  -- mixed providers
  - PARALLEL strategy  (asyncio.gather)
  - SEQUENTIAL strategy (one-by-one, ordered)
  - Partial failure handling

MANDATORY per plan:
  1. ALL mutations/reads through fabric.execute_batch() -- NEVER direct provider access.
  2. Uses FabricFactory.create_for_testing() with event capture.
  3. Real adapters only (test adapters are real, not mocks).
  4. Verify events via event adapter capture mode.

References:
  - fabric-implementation-plan.md Epic 6.3, Issue 6.3.2
  - No-Mock Testing Strategy (lines 1181-1300 of plan)
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from k1.fabric.events.fabric_events import (
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_INVOKED,
    TOPIC_LEARNING_SIGNAL,
)
from k1.fabric.fabric import BatchStrategy, Fabric
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


def _medium_request(
    capability_name: str,
    params: dict | None = None,
    *,
    caller: str = "test-medium-tier",
) -> CapabilityRequest:
    """Build a MEDIUM tier CapabilityRequest with valid fields."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params or {},
        tier=Tier.MEDIUM.value,
        caller=caller,
    )


def _make_fabric() -> Fabric:
    """Create a Fabric with event capture for integration tests."""
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


def _two_requests() -> List[CapabilityRequest]:
    """Return two requests: MCP (restaurant_booking) + WASM (weather_api)."""
    return [
        _medium_request(
            "tool.execute.restaurant_booking",
            params={
                "restaurant_name": "Batch Restaurant",
                "date": "2026-06-01",
                "party_size": 6,
            },
        ),
        _medium_request(
            "tool.read.weather_api",
            params={"location": "New York"},
        ),
    ]


# =========================================================================
# 6.3.2 -- execute_batch PARALLEL strategy
# =========================================================================


class TestMediumTierParallel:
    """
    Test execute_batch() with PARALLEL strategy.

    Both requests execute concurrently via asyncio.gather.
    Results returned in input order regardless of completion order.
    """

    async def test_parallel_both_succeed(self) -> None:
        """PARALLEL: Both capabilities return success."""
        fabric = _make_fabric()
        requests = _two_requests()
        results = await fabric.execute_batch(requests, BatchStrategy.PARALLEL)
        assert len(results) == 2
        assert_capability_result_success(results[0], expected_provider="mcp-opentable")
        assert_capability_result_success(results[1], expected_provider="wasm-weather")

    async def test_parallel_results_match_input_order(self) -> None:
        """PARALLEL: Results[i] corresponds to requests[i]."""
        fabric = _make_fabric()
        requests = _two_requests()
        results = await fabric.execute_batch(requests, BatchStrategy.PARALLEL)
        assert results[0].request_id == requests[0].request_id
        assert results[1].request_id == requests[1].request_id

    async def test_parallel_emits_two_invoked_events(self) -> None:
        """PARALLEL: Emits invoked event for each request."""
        fabric = _make_fabric()
        requests = _two_requests()
        await fabric.execute_batch(requests, BatchStrategy.PARALLEL)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_INVOKED, min_count=2)
        assert len(events) >= 2
        names = {p["capability_name"] for _, p in events}
        assert "tool.execute.restaurant_booking" in names
        assert "tool.read.weather_api" in names

    async def test_parallel_emits_two_completed_events(self) -> None:
        """PARALLEL: Emits completed event for each successful execution."""
        fabric = _make_fabric()
        requests = _two_requests()
        await fabric.execute_batch(requests, BatchStrategy.PARALLEL)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED, min_count=2)
        assert len(events) >= 2
        providers = {p["provider_id"] for _, p in events}
        assert "mcp-opentable" in providers
        assert "wasm-weather" in providers

    async def test_parallel_emits_two_learning_signals(self) -> None:
        """PARALLEL: Emits learning signal for each execution."""
        fabric = _make_fabric()
        requests = _two_requests()
        await fabric.execute_batch(requests, BatchStrategy.PARALLEL)

        events = wait_for_event(fabric.event_port, TOPIC_LEARNING_SIGNAL, min_count=2)
        assert len(events) >= 2

    async def test_parallel_trace_ids_distinct(self) -> None:
        """Each request in a batch has its own trace_id."""
        fabric = _make_fabric()
        requests = _two_requests()
        results = await fabric.execute_batch(requests, BatchStrategy.PARALLEL)
        assert results[0].trace_id == requests[0].trace_id
        assert results[1].trace_id == requests[1].trace_id
        assert results[0].trace_id != results[1].trace_id

    async def test_parallel_empty_batch_returns_empty(self) -> None:
        """PARALLEL: Empty batch returns empty list."""
        fabric = _make_fabric()
        results = await fabric.execute_batch([], BatchStrategy.PARALLEL)
        assert results == []

    async def test_parallel_single_request(self) -> None:
        """PARALLEL: Single-item batch works correctly."""
        fabric = _make_fabric()
        requests = [_medium_request("tool.read.weather_api", params={"location": "Boston"})]
        results = await fabric.execute_batch(requests, BatchStrategy.PARALLEL)
        assert len(results) == 1
        assert_capability_result_success(results[0], expected_provider="wasm-weather")


# =========================================================================
# 6.3.2 -- execute_batch SEQUENTIAL strategy
# =========================================================================


class TestMediumTierSequential:
    """
    Test execute_batch() with SEQUENTIAL strategy.

    Requests execute one-by-one in input order.
    Results returned in input order.
    """

    async def test_sequential_both_succeed(self) -> None:
        """SEQUENTIAL: Both capabilities return success."""
        fabric = _make_fabric()
        requests = _two_requests()
        results = await fabric.execute_batch(requests, BatchStrategy.SEQUENTIAL)
        assert len(results) == 2
        assert_capability_result_success(results[0], expected_provider="mcp-opentable")
        assert_capability_result_success(results[1], expected_provider="wasm-weather")

    async def test_sequential_results_match_input_order(self) -> None:
        """SEQUENTIAL: Results[i] corresponds to requests[i]."""
        fabric = _make_fabric()
        requests = _two_requests()
        results = await fabric.execute_batch(requests, BatchStrategy.SEQUENTIAL)
        assert results[0].request_id == requests[0].request_id
        assert results[1].request_id == requests[1].request_id

    async def test_sequential_emits_invoked_events(self) -> None:
        """SEQUENTIAL: Emits invoked event for each request."""
        fabric = _make_fabric()
        requests = _two_requests()
        await fabric.execute_batch(requests, BatchStrategy.SEQUENTIAL)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_INVOKED, min_count=2)
        assert len(events) >= 2

    async def test_sequential_emits_completed_events(self) -> None:
        """SEQUENTIAL: Emits completed event for each successful execution."""
        fabric = _make_fabric()
        requests = _two_requests()
        await fabric.execute_batch(requests, BatchStrategy.SEQUENTIAL)

        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED, min_count=2)
        assert len(events) >= 2

    async def test_sequential_emits_learning_signals(self) -> None:
        """SEQUENTIAL: Emits learning signal for each execution."""
        fabric = _make_fabric()
        requests = _two_requests()
        await fabric.execute_batch(requests, BatchStrategy.SEQUENTIAL)

        events = wait_for_event(fabric.event_port, TOPIC_LEARNING_SIGNAL, min_count=2)
        assert len(events) >= 2


# =========================================================================
# 6.3.2 -- Partial failure handling
# =========================================================================


class TestMediumTierPartialFailure:
    """
    Test execute_batch() partial failure semantics.

    When one request fails, other results are still returned.
    Failed requests have CapabilityResult.success=False.
    """

    async def test_partial_failure_one_bad_request(self) -> None:
        """One invalid + one valid: valid succeeds, invalid fails, both returned."""
        fabric = _make_fabric()
        requests = [
            _medium_request(
                "tool.execute.nonexistent_cap",
                params={"x": 1},
            ),
            _medium_request(
                "tool.read.weather_api",
                params={"location": "Denver"},
            ),
        ]
        results = await fabric.execute_batch(requests, BatchStrategy.PARALLEL)
        assert len(results) == 2
        # First should fail (no provider registered)
        assert results[0].success is False
        assert results[0].error is not None
        # Second should succeed
        assert_capability_result_success(results[1], expected_provider="wasm-weather")

    async def test_partial_failure_sequential(self) -> None:
        """SEQUENTIAL: First request fails, second still executes."""
        fabric = _make_fabric()
        requests = [
            _medium_request(
                "tool.execute.nonexistent_cap",
                params={"x": 1},
            ),
            _medium_request(
                "tool.read.weather_api",
                params={"location": "Denver"},
            ),
        ]
        results = await fabric.execute_batch(requests, BatchStrategy.SEQUENTIAL)
        assert len(results) == 2
        assert results[0].success is False
        assert results[1].success is True


# =========================================================================
# 6.3.2 -- Batch size limits (backpressure)
# =========================================================================


class TestMediumTierBackpressure:
    """
    Test execute_batch() backpressure: batch > max_batch_size rejected.
    """

    async def test_batch_exceeds_max_size(self) -> None:
        """Batch size exceeding max_batch_size raises BatchSizeExceededError."""
        from k1.fabric.fabric import BatchSizeExceededError

        fabric = _make_fabric()
        # Create more requests than the default max_batch_size (50)
        requests = [
            _medium_request(
                "tool.read.weather_api",
                params={"location": f"City_{i}"},
            )
            for i in range(51)
        ]
        with pytest.raises(BatchSizeExceededError):
            await fabric.execute_batch(requests, BatchStrategy.PARALLEL)


# =========================================================================
# 6.3.2 -- Mixed provider batch
# =========================================================================


class TestMediumTierMixedProviders:
    """
    Test execute_batch() with 3 provider types in a single batch:
    MCP + WASM + BRIDGE.
    """

    async def test_three_provider_batch_parallel(self) -> None:
        """PARALLEL: MCP + WASM + BRIDGE all succeed in a single batch."""
        fabric = _make_fabric()
        requests = [
            _medium_request(
                "tool.execute.restaurant_booking",
                params={
                    "restaurant_name": "Mix",
                    "date": "2026-07-01",
                    "party_size": 3,
                },
            ),
            _medium_request(
                "tool.read.weather_api",
                params={"location": "Chicago"},
            ),
            _medium_request(
                "tool.execute.memory_store",
                params={"key": "batch_k", "value": "batch_v"},
            ),
        ]
        results = await fabric.execute_batch(requests, BatchStrategy.PARALLEL)
        assert len(results) == 3
        assert_capability_result_success(results[0], expected_provider="mcp-opentable")
        assert_capability_result_success(results[1], expected_provider="wasm-weather")
        assert_capability_result_success(results[2], expected_provider="bridge-k0-memory")

    async def test_three_provider_batch_sequential(self) -> None:
        """SEQUENTIAL: MCP + WASM + BRIDGE all succeed in a single batch."""
        fabric = _make_fabric()
        requests = [
            _medium_request(
                "tool.execute.restaurant_booking",
                params={
                    "restaurant_name": "Mix",
                    "date": "2026-07-01",
                    "party_size": 3,
                },
            ),
            _medium_request(
                "tool.read.weather_api",
                params={"location": "Chicago"},
            ),
            _medium_request(
                "tool.execute.memory_store",
                params={"key": "batch_k", "value": "batch_v"},
            ),
        ]
        results = await fabric.execute_batch(requests, BatchStrategy.SEQUENTIAL)
        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is True
        assert results[2].success is True

    async def test_batch_events_for_all_three(self) -> None:
        """All three providers emit full event sequence in batch."""
        fabric = _make_fabric()
        requests = [
            _medium_request(
                "tool.execute.restaurant_booking",
                params={
                    "restaurant_name": "Mix",
                    "date": "2026-07-01",
                    "party_size": 3,
                },
            ),
            _medium_request(
                "tool.read.weather_api",
                params={"location": "Chicago"},
            ),
            _medium_request(
                "tool.execute.memory_store",
                params={"key": "batch_k", "value": "batch_v"},
            ),
        ]
        await fabric.execute_batch(requests, BatchStrategy.PARALLEL)

        invoked = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_INVOKED, min_count=3)
        completed = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED, min_count=3)
        learning = wait_for_event(fabric.event_port, TOPIC_LEARNING_SIGNAL, min_count=3)

        assert len(invoked) >= 3
        assert len(completed) >= 3
        assert len(learning) >= 3
