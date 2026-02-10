"""
Epic 6.3.12 -- Test execute_batch() semantics.

Covers:
  - PARALLEL strategy: asyncio.gather, results in input order.
  - SEQUENTIAL strategy: ordered execution, one at a time.
  - Partial failure: some succeed, some fail, no blocking.
  - Backpressure: batch > max_batch_size raises BatchSizeExceededError.
  - Empty batch returns empty list.
  - DAG strategy: dependency waves, cycle detection returns dag_cycle_detected.
  - Result ordering matches input order regardless of strategy.

NO MOCKS -- all tests use FabricFactory.create_for_testing() with real adapters.

References:
  - fabric-implementation-plan.md Epic 6.3.12
  - fabric_discussion.md Section 16 (execute_batch)
  - FabricConfig.max_batch_size (default 50)
  - BatchStrategy: PARALLEL, SEQUENTIAL, DAG
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List

import pytest

from k1.fabric.fabric import BatchSizeExceededError, BatchStrategy, FabricConfig
from k1.fabric.factory import FabricFactory
from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    CapabilityResult,
    InputSpec,
    Tier,
)
from tests.k1.fabric.helpers import (
    assert_capability_result_success,
    register_contract_with_provider,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    capability_name: str,
    *,
    request_id: str = "",
    params: dict | None = None,
    depends_on: list[str] | None = None,
) -> CapabilityRequest:
    """Build a LOW tier request with optional DAG dependencies."""
    p = params or {"query": "test"}
    if depends_on is not None:
        p = {**p, "_depends_on": depends_on}
    return CapabilityRequest(
        request_id=request_id or str(uuid.uuid4()),
        capability_name=capability_name,
        params=p,
        tier=Tier.LOW.value,
        caller="test-batch",
    )


def _make_fabric(
    *,
    max_batch_size: int = 50,
    capture_events: bool = True,
):
    """Create a test fabric with optional batch size override."""
    config = FabricConfig(max_batch_size=max_batch_size)
    return FabricFactory.create_for_testing(
        capture_events=capture_events,
        contracts_dir=str(FIXTURES_DIR),
        config=config,
    )


def _register_numbered_contracts(fabric, n: int, prefix: str = "batch_cap") -> List[str]:
    """Register N unique capabilities, return their names."""
    names = []
    for i in range(n):
        name = f"tool.execute.{prefix}_{i}"
        contract = CapabilityContract(
            name=name,
            version="1.0.0",
            domain=["TEST"],
            description=f"Batch test capability {i}",
            capabilities=[name],
            provider_type="MCP",
            provider_id=f"mcp-batch-{i}",
            required_inputs=[InputSpec(name="query", type="STRING", description="Test input")],
            output={"type": "object"},
        )
        register_contract_with_provider(fabric, contract)
        names.append(name)
    return names


# =========================================================================
# 6.3.12a -- PARALLEL strategy
# =========================================================================


class TestParallelBatch:
    """
    BatchStrategy.PARALLEL: all requests execute concurrently.
    Results in input order.
    """

    async def test_parallel_all_succeed(self) -> None:
        """10 capabilities in parallel: all succeed."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 10)

        requests = [_make_request(name) for name in cap_names]
        results = await fabric.execute_batch(requests, strategy=BatchStrategy.PARALLEL)

        assert len(results) == 10
        for r in results:
            assert_capability_result_success(r)

    async def test_parallel_results_in_input_order(self) -> None:
        """Results match input request order (by request_id)."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 5, "par_order")

        request_ids = [f"req-{i}" for i in range(5)]
        requests = [_make_request(cap_names[i], request_id=request_ids[i]) for i in range(5)]

        results = await fabric.execute_batch(requests, strategy=BatchStrategy.PARALLEL)

        assert len(results) == 5
        for i, result in enumerate(results):
            assert result.request_id == request_ids[i]

    async def test_parallel_single_item(self) -> None:
        """Single-item batch works fine."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 1, "par_single")

        results = await fabric.execute_batch(
            [_make_request(cap_names[0])],
            strategy=BatchStrategy.PARALLEL,
        )

        assert len(results) == 1
        assert_capability_result_success(results[0])

    async def test_parallel_fixture_contracts(self) -> None:
        """Parallel batch with YAML fixture contracts."""
        fabric = _make_fabric()

        requests = [
            _make_request("tool.execute.restaurant_booking"),
            _make_request("tool.read.weather_api"),
        ]
        results = await fabric.execute_batch(requests, strategy=BatchStrategy.PARALLEL)

        assert len(results) == 2
        for r in results:
            assert_capability_result_success(r)


# =========================================================================
# 6.3.12b -- SEQUENTIAL strategy
# =========================================================================


class TestSequentialBatch:
    """
    BatchStrategy.SEQUENTIAL: requests executed one at a time, in order.
    """

    async def test_sequential_all_succeed(self) -> None:
        """5 capabilities in sequential: all succeed."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 5, "seq")

        requests = [_make_request(name) for name in cap_names]
        results = await fabric.execute_batch(requests, strategy=BatchStrategy.SEQUENTIAL)

        assert len(results) == 5
        for r in results:
            assert_capability_result_success(r)

    async def test_sequential_results_in_input_order(self) -> None:
        """Sequential results match input order by request_id."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 3, "seq_order")

        request_ids = [f"seq-{i}" for i in range(3)]
        requests = [_make_request(cap_names[i], request_id=request_ids[i]) for i in range(3)]

        results = await fabric.execute_batch(requests, strategy=BatchStrategy.SEQUENTIAL)

        for i, result in enumerate(results):
            assert result.request_id == request_ids[i]

    async def test_sequential_fixture_contracts(self) -> None:
        """Sequential batch with YAML fixture contracts."""
        fabric = _make_fabric()

        requests = [
            _make_request("tool.execute.restaurant_booking"),
            _make_request("tool.read.weather_api"),
        ]
        results = await fabric.execute_batch(requests, strategy=BatchStrategy.SEQUENTIAL)

        assert len(results) == 2
        for r in results:
            assert_capability_result_success(r)


# =========================================================================
# 6.3.12c -- Partial failure
# =========================================================================


class TestPartialFailure:
    """
    Some requests succeed while others fail: no blocking.
    """

    async def test_mix_valid_invalid_capabilities(self) -> None:
        """Mix of valid + unresolvable capabilities: valid succeed, invalid fail."""
        fabric = _make_fabric()

        requests = [
            _make_request("tool.execute.restaurant_booking"),
            _make_request("tool.execute.nonexistent_cap_99"),
            _make_request("tool.read.weather_api"),
            _make_request("tool.execute.nonexistent_cap_100"),
        ]

        results = await fabric.execute_batch(requests, strategy=BatchStrategy.PARALLEL)

        assert len(results) == 4
        # Index 0: valid
        assert_capability_result_success(results[0])
        # Index 1: invalid
        assert results[1].success is False
        # Index 2: valid
        assert_capability_result_success(results[2])
        # Index 3: invalid
        assert results[3].success is False

    async def test_partial_failure_sequential(self) -> None:
        """Sequential: failed request does NOT block subsequent requests."""
        fabric = _make_fabric()

        requests = [
            _make_request("tool.execute.nonexistent_cap_A"),
            _make_request("tool.execute.restaurant_booking"),
        ]

        results = await fabric.execute_batch(requests, strategy=BatchStrategy.SEQUENTIAL)

        assert len(results) == 2
        # First fails
        assert results[0].success is False
        # Second still succeeds
        assert_capability_result_success(results[1])

    async def test_partial_failure_results_in_order(self) -> None:
        """Result indices match request indices even with failures."""
        fabric = _make_fabric()

        request_ids = ["ok-1", "fail-1", "ok-2"]
        requests = [
            _make_request("tool.execute.restaurant_booking", request_id="ok-1"),
            _make_request("tool.execute.nonexistent_xyz", request_id="fail-1"),
            _make_request("tool.read.weather_api", request_id="ok-2"),
        ]

        results = await fabric.execute_batch(requests, strategy=BatchStrategy.PARALLEL)

        assert results[0].request_id == "ok-1"
        assert results[1].request_id == "fail-1"
        assert results[2].request_id == "ok-2"


# =========================================================================
# 6.3.12d -- Backpressure: max_batch_size
# =========================================================================


class TestBackpressure:
    """
    Batch size exceeds max raises BatchSizeExceededError.
    """

    async def test_exceeds_max_raises_error(self) -> None:
        """Batch of 6 with max_batch_size=5 raises BatchSizeExceededError."""
        fabric = _make_fabric(max_batch_size=5)
        cap_names = _register_numbered_contracts(fabric, 6, "bp")

        requests = [_make_request(name) for name in cap_names]

        with pytest.raises(BatchSizeExceededError) as exc_info:
            await fabric.execute_batch(requests, strategy=BatchStrategy.PARALLEL)

        assert exc_info.value.actual == 6
        assert exc_info.value.maximum == 5

    async def test_at_max_succeeds(self) -> None:
        """Batch exactly at max_batch_size succeeds."""
        fabric = _make_fabric(max_batch_size=5)
        cap_names = _register_numbered_contracts(fabric, 5, "bp_ok")

        requests = [_make_request(name) for name in cap_names]
        results = await fabric.execute_batch(requests, strategy=BatchStrategy.PARALLEL)

        assert len(results) == 5

    async def test_empty_batch_returns_empty(self) -> None:
        """Empty batch returns empty list, no error."""
        fabric = _make_fabric()

        results = await fabric.execute_batch([], strategy=BatchStrategy.PARALLEL)
        assert results == []

    async def test_default_max_batch_size_is_50(self) -> None:
        """Default max_batch_size is 50."""
        config = FabricConfig()
        assert config.max_batch_size == 50

    async def test_custom_max_batch_size_respected(self) -> None:
        """Custom max_batch_size=3 enforced."""
        fabric = _make_fabric(max_batch_size=3)
        cap_names = _register_numbered_contracts(fabric, 4, "bp_custom")

        requests = [_make_request(name) for name in cap_names]

        with pytest.raises(BatchSizeExceededError) as exc_info:
            await fabric.execute_batch(requests)

        assert exc_info.value.actual == 4
        assert exc_info.value.maximum == 3


# =========================================================================
# 6.3.12e -- DAG strategy
# =========================================================================


class TestDAGBatch:
    """
    BatchStrategy.DAG: dependency-aware execution with topological waves.
    """

    async def test_dag_no_dependencies(self) -> None:
        """DAG with no _depends_on behaves like parallel."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 3, "dag_nodep")

        requests = [_make_request(name) for name in cap_names]
        results = await fabric.execute_batch(requests, strategy=BatchStrategy.DAG)

        assert len(results) == 3
        for r in results:
            assert_capability_result_success(r)

    async def test_dag_linear_chain(self) -> None:
        """DAG: A -> B -> C linear dependency chain."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 3, "dag_chain")

        req_a = _make_request(cap_names[0], request_id="a")
        req_b = _make_request(cap_names[1], request_id="b", depends_on=["a"])
        req_c = _make_request(cap_names[2], request_id="c", depends_on=["b"])

        results = await fabric.execute_batch(
            [req_a, req_b, req_c],
            strategy=BatchStrategy.DAG,
        )

        assert len(results) == 3
        # All succeed (wave 1: A, wave 2: B, wave 3: C)
        for r in results:
            assert_capability_result_success(r)

        # Results in INPUT order (not execution order)
        assert results[0].request_id == "a"
        assert results[1].request_id == "b"
        assert results[2].request_id == "c"

    async def test_dag_parallel_then_join(self) -> None:
        """DAG: A and B parallel, then C depends on both."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 3, "dag_join")

        req_a = _make_request(cap_names[0], request_id="join-a")
        req_b = _make_request(cap_names[1], request_id="join-b")
        req_c = _make_request(
            cap_names[2],
            request_id="join-c",
            depends_on=["join-a", "join-b"],
        )

        results = await fabric.execute_batch(
            [req_a, req_b, req_c],
            strategy=BatchStrategy.DAG,
        )

        assert len(results) == 3
        for r in results:
            assert_capability_result_success(r)

    async def test_dag_cycle_detected(self) -> None:
        """DAG: circular dependency returns dag_cycle_detected error."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 2, "dag_cycle")

        # A depends on B, B depends on A -> cycle!
        req_a = _make_request(cap_names[0], request_id="cyc-a", depends_on=["cyc-b"])
        req_b = _make_request(cap_names[1], request_id="cyc-b", depends_on=["cyc-a"])

        results = await fabric.execute_batch(
            [req_a, req_b],
            strategy=BatchStrategy.DAG,
        )

        assert len(results) == 2
        for r in results:
            assert r.success is False
            assert r.error is not None
            assert r.error.code == "dag_cycle_detected"

    async def test_dag_self_reference_cycle(self) -> None:
        """DAG: request depends on itself -> cycle detected."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 1, "dag_self")

        req = _make_request(cap_names[0], request_id="self-ref", depends_on=["self-ref"])

        results = await fabric.execute_batch([req], strategy=BatchStrategy.DAG)

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error.code == "dag_cycle_detected"

    async def test_dag_results_in_input_order(self) -> None:
        """DAG results match input order regardless of wave execution."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 4, "dag_order")

        # Wave 1: d0, d2 (no deps)
        # Wave 2: d1 (depends on d0), d3 (depends on d2)
        req_0 = _make_request(cap_names[0], request_id="d0")
        req_1 = _make_request(cap_names[1], request_id="d1", depends_on=["d0"])
        req_2 = _make_request(cap_names[2], request_id="d2")
        req_3 = _make_request(cap_names[3], request_id="d3", depends_on=["d2"])

        results = await fabric.execute_batch(
            [req_0, req_1, req_2, req_3],
            strategy=BatchStrategy.DAG,
        )

        assert len(results) == 4
        assert results[0].request_id == "d0"
        assert results[1].request_id == "d1"
        assert results[2].request_id == "d2"
        assert results[3].request_id == "d3"

    async def test_dag_unknown_dependency_ignored(self) -> None:
        """DAG: dependency on non-existent request_id is ignored."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 1, "dag_unk")

        req = _make_request(
            cap_names[0],
            request_id="dep-unk",
            depends_on=["nonexistent-id"],
        )

        results = await fabric.execute_batch([req], strategy=BatchStrategy.DAG)

        # Unknown dep is filtered out, so request has no real deps
        assert len(results) == 1
        assert_capability_result_success(results[0])


# =========================================================================
# 6.3.12f -- Cross-strategy invariants
# =========================================================================


class TestBatchInvariants:
    """
    Properties that must hold across ALL batch strategies.
    """

    @pytest.mark.parametrize(
        "strategy",
        [BatchStrategy.PARALLEL, BatchStrategy.SEQUENTIAL, BatchStrategy.DAG],
        ids=["parallel", "sequential", "dag"],
    )
    async def test_result_count_matches_request_count(self, strategy) -> None:
        """Result list length always matches request list length."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 4, f"inv_{strategy.value.lower()}")

        requests = [_make_request(name) for name in cap_names]
        results = await fabric.execute_batch(requests, strategy=strategy)

        assert len(results) == len(requests)

    @pytest.mark.parametrize(
        "strategy",
        [BatchStrategy.PARALLEL, BatchStrategy.SEQUENTIAL, BatchStrategy.DAG],
        ids=["parallel", "sequential", "dag"],
    )
    async def test_all_results_are_capability_results(self, strategy) -> None:
        """All results are CapabilityResult instances."""
        fabric = _make_fabric()
        cap_names = _register_numbered_contracts(fabric, 2, f"type_{strategy.value.lower()}")

        requests = [_make_request(name) for name in cap_names]
        results = await fabric.execute_batch(requests, strategy=strategy)

        for r in results:
            assert isinstance(r, CapabilityResult)

    @pytest.mark.parametrize(
        "strategy",
        [BatchStrategy.PARALLEL, BatchStrategy.SEQUENTIAL, BatchStrategy.DAG],
        ids=["parallel", "sequential", "dag"],
    )
    async def test_empty_batch_all_strategies(self, strategy) -> None:
        """Empty batch returns empty list for all strategies."""
        fabric = _make_fabric()
        results = await fabric.execute_batch([], strategy=strategy)
        assert results == []
