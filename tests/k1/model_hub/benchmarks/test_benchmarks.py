"""M9 Performance Benchmarks -- Hub Overhead [Epic 9.2.1].

Targets (excluding LLM inference):
  - Request deserialization < 1ms
  - Budget check            < 1ms
  - Capability routing      < 2ms
  - Model selection         < 5ms
  - Cache lookup            < 2ms
  - Plugin dispatch         < 1ms (hub overhead only)
  - Total hub overhead      < 12ms

All services wired via ModelHubFactory.create_for_testing().
No unittest.mock imports.
"""

from __future__ import annotations

import time
from typing import AsyncIterator

from k1.model_hub.factory import ModelHubFactory
from k1.model_hub.manifest import ModelSpec, PlacementConfig, ProviderManifest
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.services.budget_enforcer import BudgetEnforcer
from k1.model_hub.services.capability_router import CapabilityRouter
from k1.model_hub.services.circuit_breaker_manager import CircuitBreakerManager
from k1.model_hub.services.model_selector import ModelSelector
from k1.model_hub.services.normalization_layer import NormalizationLayer
from k1.model_hub.services.provider_registry import ProviderRegistry
from k1.model_hub.services.rate_limiter import RateLimiter
from k1.model_hub.services.response_cache import ResponseCache
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    FinishReason,
    HealthStatus,
    HubRequest,
    Message,
    ModelTier,
    PlacementType,
    RequestConstraints,
)

# Benchmark iteration counts -- enough for stable timing, fast enough for CI
_WARMUP = 5
_ITERATIONS = 100


# ===========================================================================
# Fake Plugin (zero-overhead)
# ===========================================================================


class _InstantPlugin:
    """Plugin with near-zero latency for measuring hub overhead."""

    async def initialize(self, manifest: object) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        return ProviderResponse(
            text="bench",
            prompt_tokens=10,
            completion_tokens=5,
            model_id=request.model_id or "bench-model",
            finish_reason=FinishReason.STOP,
        )

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        yield ProviderChunk(text="bench", done=True)
        return  # noqa: B901

    def estimate_tokens(self, messages: list) -> int:
        return 10

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    async def close(self) -> None:
        pass


# ===========================================================================
# Helpers
# ===========================================================================


def _make_manifest(provider_id: str = "bench-provider") -> ProviderManifest:
    caps = [CapabilityType.CHAT, CapabilityType.TOOL_CALL]
    return ProviderManifest(
        provider_id=provider_id,
        display_name="Benchmark Provider",
        capabilities=caps,
        models=[
            ModelSpec(
                id="bench-model",
                capabilities=caps,
                cost_per_1m_input=5.0,
                cost_per_1m_output=15.0,
                max_context=128000,
                tier=ModelTier.STANDARD,
            ),
        ],
        placement=PlacementConfig(type=PlacementType.REMOTE),
    )


def _make_request(trace_id: str = "bench-trace") -> HubRequest:
    return HubRequest(
        capability=CapabilityType.CHAT,
        payload=ChatPayload(messages=[Message(role="user", content="bench")]),
        constraints=RequestConstraints(consumer_id="benchmark"),
        trace_id=trace_id,
    )


def _wire():
    """Wire hub for benchmarking."""
    plugin = _InstantPlugin()
    plugins = {"bench-provider": plugin}
    facade, adapters = ModelHubFactory.create_for_testing(overrides={"plugins": plugins})
    registry: ProviderRegistry = adapters["registry"]
    circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]
    rate_limiter: RateLimiter = adapters["rate_limiter"]

    manifest = _make_manifest()
    registry.register(manifest, plugin)
    circuit_mgr.register_provider("bench-provider")
    rate_limiter.register_provider("bench-provider", rpm=10000, tpm=100_000_000)

    return facade, adapters


def _measure_sync(fn, iterations: int = _ITERATIONS) -> float:
    """Measure average time (ms) for a sync function."""
    for _ in range(_WARMUP):
        fn()
    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    elapsed = (time.perf_counter() - start) * 1000
    return elapsed / iterations


async def _measure_async(fn, iterations: int = _ITERATIONS) -> float:
    """Measure average time (ms) for an async function."""
    for _ in range(_WARMUP):
        await fn()
    start = time.perf_counter()
    for _ in range(iterations):
        await fn()
    elapsed = (time.perf_counter() - start) * 1000
    return elapsed / iterations


# ===========================================================================
# Budget Check < 1ms
# ===========================================================================


class TestBudgetCheckPerf:
    """Budget check overhead benchmark."""

    def test_budget_check_under_1ms(self) -> None:
        """budget_enforcer.check() < 1ms per call."""
        _, adapters = _wire()
        enforcer: BudgetEnforcer = adapters["budget_enforcer"]
        req = _make_request()

        avg_ms = _measure_sync(lambda: enforcer.check(req))
        assert avg_ms < 1.0, f"Budget check took {avg_ms:.3f}ms (target < 1ms)"

    def test_budget_check_with_spending(self) -> None:
        """Budget check < 1ms even with spending history."""
        _, adapters = _wire()
        enforcer: BudgetEnforcer = adapters["budget_enforcer"]
        enforcer._daily_spent_usd = 3.5
        req = _make_request()

        avg_ms = _measure_sync(lambda: enforcer.check(req))
        assert avg_ms < 1.0, f"Budget check took {avg_ms:.3f}ms (target < 1ms)"


# ===========================================================================
# Capability Routing < 2ms
# ===========================================================================


class TestCapabilityRoutingPerf:
    """Capability routing overhead benchmark."""

    def test_routing_under_2ms(self) -> None:
        """capability_router.route() < 2ms per call."""
        _, adapters = _wire()
        router: CapabilityRouter = adapters["capability_router"]
        constraints = RequestConstraints(consumer_id="bench")

        avg_ms = _measure_sync(lambda: router.route(CapabilityType.CHAT, constraints))
        assert avg_ms < 2.0, f"Routing took {avg_ms:.3f}ms (target < 2ms)"

    def test_routing_with_many_providers(self) -> None:
        """Routing < 2ms with 10 providers registered."""
        plugins = {f"p-{i}": _InstantPlugin() for i in range(10)}
        facade, adapters = ModelHubFactory.create_for_testing(overrides={"plugins": plugins})
        registry: ProviderRegistry = adapters["registry"]
        circuit_mgr: CircuitBreakerManager = adapters["circuit_mgr"]
        rate_limiter: RateLimiter = adapters["rate_limiter"]

        for pid, plugin in plugins.items():
            caps = [CapabilityType.CHAT]
            manifest = ProviderManifest(
                provider_id=pid,
                display_name=pid,
                capabilities=caps,
                models=[
                    ModelSpec(
                        id=f"model-{pid}",
                        capabilities=caps,
                        cost_per_1m_input=5.0,
                        cost_per_1m_output=15.0,
                        max_context=128000,
                    )
                ],
                placement=PlacementConfig(type=PlacementType.REMOTE),
            )
            registry.register(manifest, plugin)
            circuit_mgr.register_provider(pid)
            rate_limiter.register_provider(pid, rpm=10000, tpm=100_000_000)

        router: CapabilityRouter = adapters["capability_router"]
        constraints = RequestConstraints(consumer_id="bench")

        avg_ms = _measure_sync(lambda: router.route(CapabilityType.CHAT, constraints))
        assert avg_ms < 2.0, f"Routing (10 providers) took {avg_ms:.3f}ms (target < 2ms)"


# ===========================================================================
# Model Selection < 5ms
# ===========================================================================


class TestModelSelectionPerf:
    """Model selection overhead benchmark."""

    def test_selection_under_5ms(self) -> None:
        """model_selector.select() < 5ms per call."""
        _, adapters = _wire()
        selector: ModelSelector = adapters["model_selector"]
        router: CapabilityRouter = adapters["capability_router"]
        constraints = RequestConstraints(consumer_id="bench")

        eligible = router.route(CapabilityType.CHAT, constraints)
        req = _make_request()

        avg_ms = _measure_sync(lambda: selector.select(eligible, req))
        assert avg_ms < 5.0, f"Selection took {avg_ms:.3f}ms (target < 5ms)"


# ===========================================================================
# Cache Lookup < 2ms
# ===========================================================================


class TestCacheLookupPerf:
    """Response cache lookup overhead benchmark."""

    def test_cache_miss_under_2ms(self) -> None:
        """Cache miss lookup < 2ms."""
        _, adapters = _wire()
        cache: ResponseCache = adapters["response_cache"]
        req = _make_request()

        key = ResponseCache.build_cache_key(
            CapabilityType.CHAT,
            req.payload,
            "bench-model",
            0.7,
        )

        avg_ms = _measure_sync(lambda: cache.get(key))
        assert avg_ms < 2.0, f"Cache miss took {avg_ms:.3f}ms (target < 2ms)"

    async def test_cache_hit_under_2ms(self) -> None:
        """Cache hit lookup < 2ms (after populating)."""
        facade, adapters = _wire()
        cache: ResponseCache = adapters["response_cache"]

        # Populate cache via request
        await facade.execute(_make_request())

        key = ResponseCache.build_cache_key(
            CapabilityType.CHAT,
            _make_request().payload,
            "bench-model",
            0.7,
        )

        avg_ms = _measure_sync(lambda: cache.get(key))
        assert avg_ms < 2.0, f"Cache hit took {avg_ms:.3f}ms (target < 2ms)"


# ===========================================================================
# Normalization < 1ms
# ===========================================================================


class TestNormalizationPerf:
    """Normalization layer overhead benchmark."""

    def test_normalize_under_1ms(self) -> None:
        """NormalizationLayer.normalize() < 1ms."""
        _, adapters = _wire()
        normalization: NormalizationLayer = adapters["normalization"]
        req = _make_request()

        avg_ms = _measure_sync(lambda: normalization.normalize(req, "bench-provider"))
        assert avg_ms < 1.0, f"Normalize took {avg_ms:.3f}ms (target < 1ms)"


# ===========================================================================
# Full Pipeline < 12ms (hub overhead)
# ===========================================================================


class TestFullPipelinePerf:
    """End-to-end hub overhead benchmark (excludes LLM inference)."""

    async def test_full_pipeline_under_12ms(self) -> None:
        """Full hub pipeline overhead < 12ms (InstantPlugin has ~0ms inference)."""
        facade, _ = _wire()
        req = _make_request()

        # Warmup
        for i in range(_WARMUP):
            await facade.execute(_make_request(trace_id=f"warmup-{i}"))

        # Measure
        times = []
        for i in range(_ITERATIONS):
            r = _make_request(trace_id=f"bench-{i}")
            start = time.perf_counter()
            await facade.execute(r)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg_ms = sum(times) / len(times)
        p99_ms = sorted(times)[int(len(times) * 0.99)]

        assert avg_ms < 12.0, f"Avg pipeline took {avg_ms:.3f}ms (target < 12ms)"
        # P99 can be higher due to GC/OS jitter, but should still be reasonable
        assert p99_ms < 50.0, f"P99 pipeline took {p99_ms:.3f}ms (target < 50ms)"

    async def test_streaming_pipeline_overhead(self) -> None:
        """Streaming pipeline overhead is comparable to non-streaming."""
        facade, _ = _wire()

        times = []
        for i in range(50):
            r = _make_request(trace_id=f"stream-bench-{i}")
            start = time.perf_counter()
            chunks = []
            async for chunk in facade.stream_execute(r):
                chunks.append(chunk)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg_ms = sum(times) / len(times)
        assert avg_ms < 15.0, f"Avg stream pipeline took {avg_ms:.3f}ms (target < 15ms)"

    async def test_concurrent_requests_throughput(self) -> None:
        """Hub handles 10 concurrent requests within reasonable time."""
        import asyncio

        facade, _ = _wire()

        async def single_req(i: int) -> float:
            r = _make_request(trace_id=f"concurrent-{i}")
            start = time.perf_counter()
            await facade.execute(r)
            return (time.perf_counter() - start) * 1000

        # Run 10 concurrent requests
        tasks = [single_req(i) for i in range(10)]
        times = await asyncio.gather(*tasks)

        avg_ms = sum(times) / len(times)
        max_ms = max(times)
        assert avg_ms < 20.0, f"Avg concurrent took {avg_ms:.3f}ms (target < 20ms)"
        assert max_ms < 100.0, f"Max concurrent took {max_ms:.3f}ms (target < 100ms)"
