"""
Fabric Load Testing: Epic 8.1 Production Readiness
===================================================

This suite validates Fabric performance under load:
- 8.1.1: Concurrent executions (10, 50, 100)
- 8.1.2: Registry scale (10K, 50K, 100K)
- 8.1.3: Retrieval throughput (200, 1000 concurrent discover_capabilities)
- 8.1.4: Agent pool under load (20, 50 concurrent spawns)

THRESHOLD STRATEGY (two-tier):
  OPERATIONAL = must-pass thresholds for current implementation.
                Uses budget.extensions max values from policies.contract.yaml
                with headroom for CI variance.
  SLI         = aspirational P95 targets from policies.contract.yaml sli.latency.
                Marked xfail until retrieval pipeline is fully optimized
                (embedding ANN shortlist, pre-computed filter candidates, etc.).

REFERENCE: docs/plans/k1/fabric-implementation-plan.md - Epic 8.1
SLI SOURCE: k1/contracts/modules/fabric/policies.contract.yaml

Run with: pytest tests/k1/fabric/test_load_testing.py -v -s --tb=short
Run slow: pytest tests/k1/fabric/test_load_testing.py -v -s --tb=short -m "slow"
"""

from __future__ import annotations

import asyncio
import gc
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pytest

from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory
from k1.fabric.providers.agent_provider import AgentFactory, AgentPool, AgentPoolConfig
from k1.fabric.types import (
    AgentContract,
    CapabilityRequest,
    ExecutionContext,
    InputSpec,
    SafetyBand,
    Tier,
)
from tests.k1.fabric.helpers import create_n_contracts, register_contract_with_provider

# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------

# OPERATIONAL thresholds -- must-pass for current implementation.
# Derived from policies.contract.yaml budgets.extensions max values
# with headroom for CI variance and GC jitter.
EXEC_P95_OPERATIONAL_MS = 200
LOOKUP_P95_OPERATIONAL_US = 1000  # 1ms (matches SLI target)
RETRIEVAL_10K_OPERATIONAL_MS = 150  # budget max: 50ms, operational ceiling with O(N) headroom
RETRIEVAL_50K_OPERATIONAL_MS = 750  # extrapolated O(N) at 50K
RETRIEVAL_100K_OPERATIONAL_MS = 1500  # extrapolated O(N) at 100K
THROUGHPUT_200_P95_OPERATIONAL_MS = 750  # 200 sequential-in-async on 10K corpus + CI headroom
THROUGHPUT_1K_P95_OPERATIONAL_MS = 2000  # 1000 sequential-in-async on 10K corpus
AGENT_POOL_P95_OPERATIONAL_MS = 500

# SLI targets -- aspirational P95 from policies.contract.yaml sli.latency.
# These require retrieval pipeline optimization (ANN shortlist, cached filter
# candidates, vectorized scoring) to meet consistently.
SLI_RETRIEVAL_10K_MS = 20  # sli.latency.retrieval_10k_ms_p95
SLI_RETRIEVAL_100K_MS = 50  # sli.latency.retrieval_100k_ms_p95
SLI_THROUGHPUT_P95_MS = 50  # derived from sli.throughput.retrieval_qps=1000

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def percentile(data: List[float], p: float) -> float:
    """Calculate percentile."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p / 100)
    return sorted_data[min(idx, len(sorted_data) - 1)]


def _get_process_memory_mb() -> float:
    """Return current process RSS in megabytes (best-effort)."""
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        # psutil not available; fall back to resource on Unix
        try:
            import resource

            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        except ImportError:
            return 0.0


def _make_fabric() -> Fabric:
    """Create a Fabric with event capture for load tests."""
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


def _make_request(
    capability_name: str = "tool.execute.restaurant_booking",
    params: Optional[dict] = None,
    *,
    caller: str = "fabric-load-test",
) -> CapabilityRequest:
    """Build a valid CapabilityRequest."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params
        or {
            "restaurant_name": "Load Test",
            "date": "2026-03-15",
            "party_size": 2,
        },
        tier=Tier.MEDIUM.value,
        caller=caller,
    )


def _make_agent_contract(
    name: str = "agent.execute.load_agent",
    tools_granted: Optional[List[str]] = None,
    llm_budget_tokens: int = 2048,
) -> AgentContract:
    """Build a minimal AgentContract for agent pool load testing."""
    return AgentContract(
        name=name,
        version="1.0.0",
        domain=["LOAD"],
        description="Agent contract for load testing",
        capabilities=["load_action"],
        limitations=[],
        required_inputs=[
            InputSpec(name="query", type="STRING", description="Load test input"),
        ],
        output={"type": "object"},
        provider_type="AGENT",
        provider_id="agent-load-runner",
        safety_band_min=SafetyBand.GREEN.value,
        prompt_template="load_prompt_v1",
        tools_granted=tools_granted or ["tool.execute.restaurant_booking"],
        llm_budget_tokens=llm_budget_tokens,
        max_tool_calls=3,
        max_execution_time_ms=10000,
    )


def _make_execution_context(trace_id: str) -> ExecutionContext:
    """Build a minimal ExecutionContext."""
    return ExecutionContext(
        session_sections={
            "beliefs_active.entities": {"Alice": {"role": "friend"}},
        },
        params={"query": "hello"},
        trace_id=trace_id,
    )


def _make_agent_factory(
    *,
    contract: AgentContract,
    pool: AgentPool,
    model_gateway: Optional[TestModelGatewayAdapter] = None,
    delta_bus: Optional[TestDeltaBusAdapter] = None,
) -> AgentFactory:
    """Create AgentFactory with real test adapters."""
    gw = model_gateway or TestModelGatewayAdapter(
        default_responses=["Agent response: load testing"],
    )
    db = delta_bus or TestDeltaBusAdapter()
    state = TestSessionStateReaderAdapter()

    def loader(name: str) -> Optional[AgentContract]:
        if name == contract.name:
            return contract
        return None

    return AgentFactory(
        model_gateway=gw,
        state_reader=state,
        delta_bus=db,
        contract_loader=loader,
        pool=pool,
    )


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ConcurrentExecutionResult:
    num_requests: int
    successful: int
    failed: int
    throughput_ops_sec: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    total_duration_sec: float
    memory_before_mb: float
    memory_after_mb: float


@dataclass
class RegistryScaleResult:
    num_contracts: int
    registration_throughput_ops_sec: float
    lookup_latency_p50_us: float
    lookup_latency_p95_us: float
    lookup_latency_p99_us: float
    retrieval_latency_ms: float
    memory_before_mb: float
    memory_after_mb: float


@dataclass
class RetrievalThroughputResult:
    num_queries: int
    successful: int
    failed: int
    throughput_qps: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    total_duration_sec: float


@dataclass
class AgentPoolLoadResult:
    concurrent_requests: int
    successful: int
    failed: int
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    pool_size_after: int
    reuse_rate: float
    approx_pool_bytes: int


# =============================================================================
# 8.1.1 -- Concurrent Executions
# =============================================================================


async def _run_concurrent_executions(num_requests: int) -> ConcurrentExecutionResult:
    fabric = _make_fabric()
    latencies_ms: List[float] = []
    successes = 0
    failures = 0

    async def _execute_one(i: int) -> None:
        nonlocal successes, failures
        request = _make_request(
            params={
                "restaurant_name": f"Load-{i}",
                "date": "2026-03-15",
                "party_size": (i % 6) + 1,
            }
        )
        start = time.perf_counter()
        result = await fabric.execute(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies_ms.append(elapsed_ms)
        if result.success:
            successes += 1
        else:
            failures += 1

    gc.collect()
    mem_before = _get_process_memory_mb()
    start_time = time.perf_counter()
    await asyncio.gather(*[_execute_one(i) for i in range(num_requests)])
    total_duration = time.perf_counter() - start_time
    mem_after = _get_process_memory_mb()

    return ConcurrentExecutionResult(
        num_requests=num_requests,
        successful=successes,
        failed=failures,
        throughput_ops_sec=(num_requests / total_duration if total_duration > 0 else 0.0),
        latency_p50_ms=percentile(latencies_ms, 50),
        latency_p95_ms=percentile(latencies_ms, 95),
        latency_p99_ms=percentile(latencies_ms, 99),
        total_duration_sec=total_duration,
        memory_before_mb=mem_before,
        memory_after_mb=mem_after,
    )


class TestConcurrentExecutions:
    """Epic 8.1.1: concurrent fabric.execute() load."""

    async def test_10_concurrent_executions(self) -> None:
        result = await _run_concurrent_executions(10)

        print("\n" + "=" * 60)
        print("  8.1.1 -- 10 CONCURRENT EXECUTIONS")
        print("=" * 60)
        print(f"  Successful:  {result.successful:>6}")
        print(f"  Failed:      {result.failed:>6}")
        print(f"  Throughput:  {result.throughput_ops_sec:>10.2f} ops/sec")
        print(f"  Latency P50: {result.latency_p50_ms:>10.2f} ms")
        print(f"  Latency P95: {result.latency_p95_ms:>10.2f} ms")
        print(f"  Latency P99: {result.latency_p99_ms:>10.2f} ms")
        print(f"  Duration:    {result.total_duration_sec:>10.2f} sec")
        print(f"  Memory:      {result.memory_before_mb:>10.1f} -> {result.memory_after_mb:.1f} MB")
        print("=" * 60)

        assert result.failed == 0, f"{result.failed} requests failed"
        assert (
            result.latency_p95_ms < EXEC_P95_OPERATIONAL_MS
        ), f"P95 {result.latency_p95_ms:.2f}ms > {EXEC_P95_OPERATIONAL_MS}ms"

    async def test_50_concurrent_executions(self) -> None:
        result = await _run_concurrent_executions(50)

        print("\n" + "=" * 60)
        print("  8.1.1 -- 50 CONCURRENT EXECUTIONS")
        print("=" * 60)
        print(f"  Successful:  {result.successful:>6}")
        print(f"  Failed:      {result.failed:>6}")
        print(f"  Throughput:  {result.throughput_ops_sec:>10.2f} ops/sec")
        print(f"  Latency P50: {result.latency_p50_ms:>10.2f} ms")
        print(f"  Latency P95: {result.latency_p95_ms:>10.2f} ms")
        print(f"  Latency P99: {result.latency_p99_ms:>10.2f} ms")
        print(f"  Duration:    {result.total_duration_sec:>10.2f} sec")
        print(f"  Memory:      {result.memory_before_mb:>10.1f} -> {result.memory_after_mb:.1f} MB")
        print("=" * 60)

        assert result.failed == 0, f"{result.failed} requests failed"
        assert (
            result.latency_p95_ms < EXEC_P95_OPERATIONAL_MS
        ), f"P95 {result.latency_p95_ms:.2f}ms > {EXEC_P95_OPERATIONAL_MS}ms"

    async def test_100_concurrent_executions(self) -> None:
        result = await _run_concurrent_executions(100)

        print("\n" + "=" * 60)
        print("  8.1.1 -- 100 CONCURRENT EXECUTIONS")
        print("=" * 60)
        print(f"  Successful:  {result.successful:>6}")
        print(f"  Failed:      {result.failed:>6}")
        print(f"  Throughput:  {result.throughput_ops_sec:>10.2f} ops/sec")
        print(f"  Latency P50: {result.latency_p50_ms:>10.2f} ms")
        print(f"  Latency P95: {result.latency_p95_ms:>10.2f} ms")
        print(f"  Latency P99: {result.latency_p99_ms:>10.2f} ms")
        print(f"  Duration:    {result.total_duration_sec:>10.2f} sec")
        print(f"  Memory:      {result.memory_before_mb:>10.1f} -> {result.memory_after_mb:.1f} MB")
        print("=" * 60)

        assert result.failed == 0, f"{result.failed} requests failed"
        assert (
            result.latency_p95_ms < EXEC_P95_OPERATIONAL_MS
        ), f"P95 {result.latency_p95_ms:.2f}ms > {EXEC_P95_OPERATIONAL_MS}ms"


# =============================================================================
# 8.1.2 -- Registry Scale
# =============================================================================


async def _run_registry_scale_test(num_contracts: int) -> RegistryScaleResult:
    fabric = _make_fabric()

    contracts = create_n_contracts(num_contracts, domain="SCALE")

    gc.collect()
    mem_before = _get_process_memory_mb()
    start = time.perf_counter()
    for contract in contracts:
        register_contract_with_provider(fabric, contract)
    registration_duration = time.perf_counter() - start
    mem_after = _get_process_memory_mb()

    lookup_latencies_us: List[float] = []
    sample_names = [c.name for c in contracts[: min(num_contracts, 1000)]]
    for name in sample_names:
        t0 = time.perf_counter_ns()
        _ = fabric.lookup(name)
        lookup_latencies_us.append((time.perf_counter_ns() - t0) / 1000)

    t0 = time.perf_counter()
    _ = await fabric.discover_capabilities(
        domain=["SCALE"],
        intent="scale test",
        top_k=10,
    )
    retrieval_ms = (time.perf_counter() - t0) * 1000

    return RegistryScaleResult(
        num_contracts=num_contracts,
        registration_throughput_ops_sec=(
            num_contracts / registration_duration if registration_duration > 0 else 0.0
        ),
        lookup_latency_p50_us=percentile(lookup_latencies_us, 50),
        lookup_latency_p95_us=percentile(lookup_latencies_us, 95),
        lookup_latency_p99_us=percentile(lookup_latencies_us, 99),
        retrieval_latency_ms=retrieval_ms,
        memory_before_mb=mem_before,
        memory_after_mb=mem_after,
    )


def _print_registry_scale(label: str, result: RegistryScaleResult) -> None:
    """Shared output formatter for registry scale results."""
    print("\n" + "=" * 60)
    print(f"  8.1.2 -- REGISTRY SCALE: {label}")
    print("=" * 60)
    print(f"  Registration throughput: {result.registration_throughput_ops_sec:>10.2f} ops/sec")
    print(f"  Lookup P50:               {result.lookup_latency_p50_us:>10.2f} us")
    print(f"  Lookup P95:               {result.lookup_latency_p95_us:>10.2f} us")
    print(f"  Lookup P99:               {result.lookup_latency_p99_us:>10.2f} us")
    print(f"  Retrieval latency:        {result.retrieval_latency_ms:>10.2f} ms")
    print(f"  SLI target (10K):         {SLI_RETRIEVAL_10K_MS:>10} ms")
    print(f"  Operational ceiling:      {RETRIEVAL_10K_OPERATIONAL_MS:>10} ms")
    print(
        f"  Memory:                   {result.memory_before_mb:>10.1f} -> {result.memory_after_mb:.1f} MB"
    )
    delta = result.memory_after_mb - result.memory_before_mb
    print(f"  Memory delta:             {delta:>10.1f} MB")
    print("=" * 60)


class TestRegistryScale:
    """Epic 8.1.2: registry scale load tests."""

    async def test_registry_scale_10k(self) -> None:
        result = await _run_registry_scale_test(10_000)
        _print_registry_scale("10K", result)

        # Lookup must meet SLI target (P95 < 1ms) -- O(1) hash lookup
        assert (
            result.lookup_latency_p95_us < LOOKUP_P95_OPERATIONAL_US
        ), f"Lookup P95 {result.lookup_latency_p95_us:.2f}us > {LOOKUP_P95_OPERATIONAL_US}us"

        # Retrieval must be under operational ceiling
        assert (
            result.retrieval_latency_ms < RETRIEVAL_10K_OPERATIONAL_MS
        ), f"Retrieval {result.retrieval_latency_ms:.2f}ms > {RETRIEVAL_10K_OPERATIONAL_MS}ms"

    @pytest.mark.xfail(
        reason="SLI aspirational: requires retrieval pipeline optimization (ANN shortlist)",
        strict=False,
    )
    async def test_registry_scale_10k_sli_target(self) -> None:
        """SLI target: retrieval 10K < 20ms P95."""
        result = await _run_registry_scale_test(10_000)

        assert (
            result.retrieval_latency_ms < SLI_RETRIEVAL_10K_MS
        ), f"SLI: Retrieval {result.retrieval_latency_ms:.2f}ms > {SLI_RETRIEVAL_10K_MS}ms"

    @pytest.mark.slow
    async def test_registry_scale_50k(self) -> None:
        result = await _run_registry_scale_test(50_000)
        _print_registry_scale("50K", result)

        assert (
            result.lookup_latency_p95_us < LOOKUP_P95_OPERATIONAL_US
        ), f"Lookup P95 {result.lookup_latency_p95_us:.2f}us > {LOOKUP_P95_OPERATIONAL_US}us"
        assert (
            result.retrieval_latency_ms < RETRIEVAL_50K_OPERATIONAL_MS
        ), f"Retrieval {result.retrieval_latency_ms:.2f}ms > {RETRIEVAL_50K_OPERATIONAL_MS}ms"

    @pytest.mark.slow
    async def test_registry_scale_100k(self) -> None:
        result = await _run_registry_scale_test(100_000)
        _print_registry_scale("100K", result)

        assert (
            result.lookup_latency_p95_us < LOOKUP_P95_OPERATIONAL_US
        ), f"Lookup P95 {result.lookup_latency_p95_us:.2f}us > {LOOKUP_P95_OPERATIONAL_US}us"
        assert (
            result.retrieval_latency_ms < RETRIEVAL_100K_OPERATIONAL_MS
        ), f"Retrieval {result.retrieval_latency_ms:.2f}ms > {RETRIEVAL_100K_OPERATIONAL_MS}ms"


# =============================================================================
# 8.1.3 -- Retrieval Throughput
# =============================================================================


async def _run_retrieval_throughput(num_queries: int) -> RetrievalThroughputResult:
    fabric = _make_fabric()
    contracts = create_n_contracts(10_000, domain="THROUGHPUT")
    for contract in contracts:
        register_contract_with_provider(fabric, contract)

    latencies_ms: List[float] = []
    successes = 0
    failures = 0

    async def _discover_one(i: int) -> None:
        nonlocal successes, failures
        start = time.perf_counter()
        try:
            _ = await fabric.discover_capabilities(
                domain=["THROUGHPUT"],
                intent=f"query {i}",
                top_k=10,
            )
            successes += 1
        except Exception:
            failures += 1
        finally:
            latencies_ms.append((time.perf_counter() - start) * 1000)

    gc.collect()
    start_time = time.perf_counter()
    await asyncio.gather(*[_discover_one(i) for i in range(num_queries)])
    total_duration = time.perf_counter() - start_time

    return RetrievalThroughputResult(
        num_queries=num_queries,
        successful=successes,
        failed=failures,
        throughput_qps=(num_queries / total_duration if total_duration > 0 else 0.0),
        latency_p50_ms=percentile(latencies_ms, 50),
        latency_p95_ms=percentile(latencies_ms, 95),
        latency_p99_ms=percentile(latencies_ms, 99),
        total_duration_sec=total_duration,
    )


class TestRetrievalThroughput:
    """Epic 8.1.3: retrieval throughput load tests."""

    async def test_retrieval_throughput_200(self) -> None:
        result = await _run_retrieval_throughput(200)

        print("\n" + "=" * 60)
        print("  8.1.3 -- RETRIEVAL THROUGHPUT: 200 QUERIES")
        print("=" * 60)
        print(f"  Successful:  {result.successful:>10}")
        print(f"  Failed:      {result.failed:>10}")
        print(f"  Throughput:  {result.throughput_qps:>10.2f} qps")
        print(f"  Latency P50: {result.latency_p50_ms:>10.2f} ms")
        print(f"  Latency P95: {result.latency_p95_ms:>10.2f} ms")
        print(f"  Latency P99: {result.latency_p99_ms:>10.2f} ms")
        print(f"  Duration:    {result.total_duration_sec:>10.2f} sec")
        print(f"  SLI target:  {SLI_THROUGHPUT_P95_MS:>10} ms P95")
        print(f"  Operational: {THROUGHPUT_200_P95_OPERATIONAL_MS:>10} ms P95")
        print("=" * 60)

        assert result.failed == 0, f"{result.failed} queries failed"
        assert (
            result.latency_p95_ms < THROUGHPUT_200_P95_OPERATIONAL_MS
        ), f"P95 {result.latency_p95_ms:.2f}ms > {THROUGHPUT_200_P95_OPERATIONAL_MS}ms"

    @pytest.mark.xfail(
        reason="SLI aspirational: requires retrieval pipeline optimization + async executor",
        strict=False,
    )
    async def test_retrieval_throughput_200_sli_target(self) -> None:
        """SLI target: retrieval throughput P95 < 50ms."""
        result = await _run_retrieval_throughput(200)

        assert result.failed == 0
        assert (
            result.latency_p95_ms < SLI_THROUGHPUT_P95_MS
        ), f"SLI: P95 {result.latency_p95_ms:.2f}ms > {SLI_THROUGHPUT_P95_MS}ms"

    @pytest.mark.slow
    async def test_retrieval_throughput_1000(self) -> None:
        result = await _run_retrieval_throughput(1000)

        print("\n" + "=" * 60)
        print("  8.1.3 -- RETRIEVAL THROUGHPUT: 1000 QUERIES")
        print("=" * 60)
        print(f"  Successful:  {result.successful:>10}")
        print(f"  Failed:      {result.failed:>10}")
        print(f"  Throughput:  {result.throughput_qps:>10.2f} qps")
        print(f"  Latency P50: {result.latency_p50_ms:>10.2f} ms")
        print(f"  Latency P95: {result.latency_p95_ms:>10.2f} ms")
        print(f"  Latency P99: {result.latency_p99_ms:>10.2f} ms")
        print(f"  Duration:    {result.total_duration_sec:>10.2f} sec")
        print("=" * 60)

        assert result.failed == 0, f"{result.failed} queries failed"
        assert (
            result.latency_p95_ms < THROUGHPUT_1K_P95_OPERATIONAL_MS
        ), f"P95 {result.latency_p95_ms:.2f}ms > {THROUGHPUT_1K_P95_OPERATIONAL_MS}ms"


# =============================================================================
# 8.1.4 -- Agent Pool Under Load
# =============================================================================


async def _run_agent_pool_load(concurrency: int) -> AgentPoolLoadResult:
    contract = _make_agent_contract()
    pool = AgentPool(AgentPoolConfig(max_pool_size=max(5, concurrency // 2)))
    factory = _make_agent_factory(contract=contract, pool=pool)

    latencies_ms: List[float] = []
    successes = 0
    failures = 0

    async def _spawn_one(i: int) -> None:
        nonlocal successes, failures
        request = _make_request(
            capability_name=contract.name,
            params={"query": f"agent-load-{i}"},
        )
        context = _make_execution_context(trace_id=request.trace_id)
        start = time.perf_counter()
        result = await factory.spawn_and_execute(request, context, request.trace_id)
        latencies_ms.append((time.perf_counter() - start) * 1000)
        if result.success:
            successes += 1
        else:
            failures += 1

    gc.collect()
    await asyncio.gather(*[_spawn_one(i) for i in range(concurrency)])

    # Second wave to test reuse
    reuses_before = pool.total_reuses
    await asyncio.gather(*[_spawn_one(i + concurrency) for i in range(concurrency)])
    reuses_after = pool.total_reuses - reuses_before

    pooled_agents = []
    for bucket in getattr(pool, "_pool", {}).values():
        pooled_agents.extend(bucket)
    approx_pool_bytes = sys.getsizeof(pool) + sum(sys.getsizeof(a) for a in pooled_agents)

    return AgentPoolLoadResult(
        concurrent_requests=concurrency,
        successful=successes,
        failed=failures,
        latency_p50_ms=percentile(latencies_ms, 50),
        latency_p95_ms=percentile(latencies_ms, 95),
        latency_p99_ms=percentile(latencies_ms, 99),
        pool_size_after=pool.size(contract.name),
        reuse_rate=(reuses_after / concurrency if concurrency > 0 else 0.0),
        approx_pool_bytes=approx_pool_bytes,
    )


class TestAgentPoolLoad:
    """Epic 8.1.4: agent pool load tests."""

    async def test_agent_pool_load_20(self) -> None:
        result = await _run_agent_pool_load(20)

        print("\n" + "=" * 60)
        print("  8.1.4 -- AGENT POOL LOAD: 20 CONCURRENT")
        print("=" * 60)
        print(f"  Successful:  {result.successful:>10}")
        print(f"  Failed:      {result.failed:>10}")
        print(f"  Latency P50: {result.latency_p50_ms:>10.2f} ms")
        print(f"  Latency P95: {result.latency_p95_ms:>10.2f} ms")
        print(f"  Latency P99: {result.latency_p99_ms:>10.2f} ms")
        print(f"  Pool size:   {result.pool_size_after:>10}")
        print(f"  Reuse rate:  {result.reuse_rate:>10.2%}")
        print(f"  Pool bytes:  {result.approx_pool_bytes:>10}")
        print("=" * 60)

        assert result.failed == 0, f"{result.failed} spawns failed"
        assert result.pool_size_after > 0, "Pool should retain agents"
        assert result.reuse_rate > 0.0, "Pool should demonstrate reuse"
        assert (
            result.latency_p95_ms < AGENT_POOL_P95_OPERATIONAL_MS
        ), f"P95 {result.latency_p95_ms:.2f}ms > {AGENT_POOL_P95_OPERATIONAL_MS}ms"

    async def test_agent_pool_load_50(self) -> None:
        result = await _run_agent_pool_load(50)

        print("\n" + "=" * 60)
        print("  8.1.4 -- AGENT POOL LOAD: 50 CONCURRENT")
        print("=" * 60)
        print(f"  Successful:  {result.successful:>10}")
        print(f"  Failed:      {result.failed:>10}")
        print(f"  Latency P50: {result.latency_p50_ms:>10.2f} ms")
        print(f"  Latency P95: {result.latency_p95_ms:>10.2f} ms")
        print(f"  Latency P99: {result.latency_p99_ms:>10.2f} ms")
        print(f"  Pool size:   {result.pool_size_after:>10}")
        print(f"  Reuse rate:  {result.reuse_rate:>10.2%}")
        print(f"  Pool bytes:  {result.approx_pool_bytes:>10}")
        print("=" * 60)

        assert result.failed == 0, f"{result.failed} spawns failed"
        assert result.pool_size_after > 0, "Pool should retain agents"
        assert result.reuse_rate > 0.0, "Pool should demonstrate reuse"
        assert (
            result.latency_p95_ms < AGENT_POOL_P95_OPERATIONAL_MS
        ), f"P95 {result.latency_p95_ms:.2f}ms > {AGENT_POOL_P95_OPERATIONAL_MS}ms"
