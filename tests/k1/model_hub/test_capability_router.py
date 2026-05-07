"""M3 Routing & Selection -- Test CapabilityRouter [F41].

Tests the 5-step filtering pipeline: capability lookup, model filter,
circuit breaker, rate limiter, health status.

Covers:
  - EligibleProvider: construction, defaults, frozen
  - ICircuitBreakerQuery, IRateLimiterQuery, IHealthQuery: protocol compliance
  - CapabilityRouter.route(): all 5 steps, edge cases
  - Empty registry, all filtered, partial filtering
  - Invariant MH-06: Capability-aware fallback
  - Invariant MH-18: Manifest is SOLE capability truth

Uses simple stub implementations for dependency protocols.
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.manifest import ModelSpec, PlacementConfig, ProviderManifest
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.services.capability_router import (
    CapabilityRouter,
    EligibleProvider,
    ICircuitBreakerQuery,
    IHealthQuery,
    IRateLimiterQuery,
)
from k1.model_hub.services.provider_registry import ProviderInfo, ProviderRegistry
from k1.model_hub.types import (
    CapabilityType,
    CircuitState,
    HealthStatus,
    ModelTier,
    PlacementType,
    Priority,
    RequestConstraints,
)

# ===========================================================================
# Stubs for dependency protocols
# ===========================================================================


class _StubCircuitBreaker:
    """Stub: all providers CLOSED by default."""

    def __init__(self) -> None:
        self._overrides: dict[str, CircuitState] = {}

    def set_state(self, provider_id: str, state: CircuitState) -> None:
        self._overrides[provider_id] = state

    def get_state(self, provider_id: str) -> CircuitState:
        return self._overrides.get(provider_id, CircuitState.CLOSED)


class _StubRateLimiter:
    """Stub: all providers have capacity by default."""

    def __init__(self) -> None:
        self._blocked: set[str] = set()

    def block(self, provider_id: str) -> None:
        self._blocked.add(provider_id)

    def has_capacity(self, provider_id: str, token_estimate: int) -> bool:
        return provider_id not in self._blocked


class _StubHealthMonitor:
    """Stub: all providers HEALTHY by default."""

    def __init__(self) -> None:
        self._overrides: dict[str, HealthStatus] = {}

    def set_status(self, provider_id: str, status: HealthStatus) -> None:
        self._overrides[provider_id] = status

    def get_status(self, provider_id: str) -> HealthStatus:
        return self._overrides.get(provider_id, HealthStatus.HEALTHY)


class _StubPlugin:
    """Minimal plugin stub for registry."""

    async def initialize(self, manifest: ProviderManifest) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        return ProviderResponse(text="stub")

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        yield ProviderChunk(delta="stub")

    def estimate_tokens(self, text: str) -> int:
        return len(text.split())

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    async def close(self) -> None:
        pass


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def config() -> ModelHubConfig:
    return ModelHubConfig()


@pytest.fixture
def registry(config: ModelHubConfig) -> ProviderRegistry:
    return ProviderRegistry(config)


@pytest.fixture
def circuit_breaker() -> _StubCircuitBreaker:
    return _StubCircuitBreaker()


@pytest.fixture
def rate_limiter() -> _StubRateLimiter:
    return _StubRateLimiter()


@pytest.fixture
def health_monitor() -> _StubHealthMonitor:
    return _StubHealthMonitor()


@pytest.fixture
def router(
    registry: ProviderRegistry,
    circuit_breaker: _StubCircuitBreaker,
    rate_limiter: _StubRateLimiter,
    health_monitor: _StubHealthMonitor,
) -> CapabilityRouter:
    return CapabilityRouter(registry, circuit_breaker, rate_limiter, health_monitor)


def _make_constraints(
    priority: Priority = Priority.INTERACTIVE,
    timeout_ms: int = 30000,
    consumer_id: str = "concierge",
) -> RequestConstraints:
    return RequestConstraints(
        timeout_ms=timeout_ms,
        consumer_id=consumer_id,
        priority=priority,
    )


def _register_provider(
    registry: ProviderRegistry,
    provider_id: str = "openai",
    capabilities: list[CapabilityType] | None = None,
    models: list[ModelSpec] | None = None,
    placement_type: PlacementType = PlacementType.REMOTE,
) -> None:
    """Helper to register a provider with given capabilities and models."""
    caps = capabilities or [CapabilityType.CHAT]
    mdls = models or [
        ModelSpec(
            id=f"model-{provider_id}",
            capabilities=caps,
            cost_per_1m_input=2.5,
            cost_per_1m_output=10.0,
            tier=ModelTier.STANDARD,
        ),
    ]
    manifest = ProviderManifest(
        provider_id=provider_id,
        display_name=f"Test {provider_id}",
        capabilities=caps,
        models=mdls,
        placement=PlacementConfig(type=placement_type),
    )
    registry.register(manifest, _StubPlugin())


# ===========================================================================
# EligibleProvider Tests
# ===========================================================================


class TestEligibleProvider:
    """Tests for EligibleProvider dataclass."""

    def test_defaults(self) -> None:
        info = ProviderInfo(provider_id="openai")
        ep = EligibleProvider(provider_info=info)
        assert ep.provider_info.provider_id == "openai"
        assert ep.eligible_models == []
        assert ep.circuit_state == CircuitState.CLOSED
        assert ep.health_status == HealthStatus.HEALTHY

    def test_custom_values(self) -> None:
        info = ProviderInfo(provider_id="anthropic")
        model = ModelSpec(id="claude-3", capabilities=[CapabilityType.CHAT])
        ep = EligibleProvider(
            provider_info=info,
            eligible_models=[model],
            circuit_state=CircuitState.HALF_OPEN,
            health_status=HealthStatus.DEGRADED,
        )
        assert ep.eligible_models[0].id == "claude-3"
        assert ep.circuit_state == CircuitState.HALF_OPEN
        assert ep.health_status == HealthStatus.DEGRADED

    def test_frozen(self) -> None:
        info = ProviderInfo(provider_id="openai")
        ep = EligibleProvider(provider_info=info)
        with pytest.raises(AttributeError):
            ep.circuit_state = CircuitState.OPEN  # type: ignore[misc]


# ===========================================================================
# Protocol Compliance Tests
# ===========================================================================


class TestProtocolCompliance:
    """Tests for dependency protocol compliance."""

    def test_circuit_breaker_protocol(self) -> None:
        stub = _StubCircuitBreaker()
        assert isinstance(stub, ICircuitBreakerQuery)

    def test_rate_limiter_protocol(self) -> None:
        stub = _StubRateLimiter()
        assert isinstance(stub, IRateLimiterQuery)

    def test_health_monitor_protocol(self) -> None:
        stub = _StubHealthMonitor()
        assert isinstance(stub, IHealthQuery)


# ===========================================================================
# CapabilityRouter.route() Tests -- Full Pipeline
# ===========================================================================


class TestCapabilityRouterRoute:
    """Tests for the 5-step filtering pipeline."""

    def test_route_empty_registry(self, router: CapabilityRouter) -> None:
        """Step 1: No providers for capability -> empty result."""
        result = router.route(CapabilityType.CHAT, _make_constraints())
        assert result == []

    def test_route_single_provider_passes_all_filters(
        self, registry: ProviderRegistry, router: CapabilityRouter
    ) -> None:
        """All 5 steps pass for single healthy provider."""
        _register_provider(registry, "openai", [CapabilityType.CHAT])
        result = router.route(CapabilityType.CHAT, _make_constraints())

        assert len(result) == 1
        assert result[0].provider_info.provider_id == "openai"
        assert result[0].circuit_state == CircuitState.CLOSED
        assert result[0].health_status == HealthStatus.HEALTHY

    def test_route_multiple_providers(
        self, registry: ProviderRegistry, router: CapabilityRouter
    ) -> None:
        _register_provider(registry, "openai", [CapabilityType.CHAT])
        _register_provider(registry, "anthropic", [CapabilityType.CHAT])
        result = router.route(CapabilityType.CHAT, _make_constraints())

        assert len(result) == 2
        pids = {ep.provider_info.provider_id for ep in result}
        assert pids == {"openai", "anthropic"}

    def test_route_filters_by_capability(
        self, registry: ProviderRegistry, router: CapabilityRouter
    ) -> None:
        """Step 1: Only providers with matching capability returned."""
        _register_provider(registry, "openai", [CapabilityType.CHAT])
        _register_provider(registry, "embed-only", [CapabilityType.EMBED])

        result = router.route(CapabilityType.CHAT, _make_constraints())
        assert len(result) == 1
        assert result[0].provider_info.provider_id == "openai"

    def test_route_filters_circuit_open(
        self,
        registry: ProviderRegistry,
        router: CapabilityRouter,
        circuit_breaker: _StubCircuitBreaker,
    ) -> None:
        """Step 3: OPEN circuit breaker excludes provider."""
        _register_provider(registry, "openai", [CapabilityType.CHAT])
        _register_provider(registry, "anthropic", [CapabilityType.CHAT])

        circuit_breaker.set_state("openai", CircuitState.OPEN)

        result = router.route(CapabilityType.CHAT, _make_constraints())
        assert len(result) == 1
        assert result[0].provider_info.provider_id == "anthropic"

    def test_route_allows_half_open_circuit(
        self,
        registry: ProviderRegistry,
        router: CapabilityRouter,
        circuit_breaker: _StubCircuitBreaker,
    ) -> None:
        """Step 3: HALF_OPEN circuit still passes."""
        _register_provider(registry, "openai", [CapabilityType.CHAT])
        circuit_breaker.set_state("openai", CircuitState.HALF_OPEN)

        result = router.route(CapabilityType.CHAT, _make_constraints())
        assert len(result) == 1
        assert result[0].circuit_state == CircuitState.HALF_OPEN

    def test_route_filters_rate_limited(
        self,
        registry: ProviderRegistry,
        router: CapabilityRouter,
        rate_limiter: _StubRateLimiter,
    ) -> None:
        """Step 4: Rate-limited provider excluded."""
        _register_provider(registry, "openai", [CapabilityType.CHAT])
        _register_provider(registry, "anthropic", [CapabilityType.CHAT])

        rate_limiter.block("openai")

        result = router.route(CapabilityType.CHAT, _make_constraints())
        assert len(result) == 1
        assert result[0].provider_info.provider_id == "anthropic"

    def test_route_filters_unhealthy(
        self,
        registry: ProviderRegistry,
        router: CapabilityRouter,
        health_monitor: _StubHealthMonitor,
    ) -> None:
        """Step 5: UNHEALTHY provider excluded."""
        _register_provider(registry, "openai", [CapabilityType.CHAT])
        _register_provider(registry, "anthropic", [CapabilityType.CHAT])

        health_monitor.set_status("openai", HealthStatus.UNHEALTHY)

        result = router.route(CapabilityType.CHAT, _make_constraints())
        assert len(result) == 1
        assert result[0].provider_info.provider_id == "anthropic"

    def test_route_allows_degraded(
        self,
        registry: ProviderRegistry,
        router: CapabilityRouter,
        health_monitor: _StubHealthMonitor,
    ) -> None:
        """Step 5: DEGRADED provider still passes."""
        _register_provider(registry, "openai", [CapabilityType.CHAT])
        health_monitor.set_status("openai", HealthStatus.DEGRADED)

        result = router.route(CapabilityType.CHAT, _make_constraints())
        assert len(result) == 1
        assert result[0].health_status == HealthStatus.DEGRADED

    def test_route_all_filtered_returns_empty(
        self,
        registry: ProviderRegistry,
        router: CapabilityRouter,
        circuit_breaker: _StubCircuitBreaker,
    ) -> None:
        """All providers filtered -> empty list."""
        _register_provider(registry, "openai", [CapabilityType.CHAT])
        circuit_breaker.set_state("openai", CircuitState.OPEN)

        result = router.route(CapabilityType.CHAT, _make_constraints())
        assert result == []

    def test_route_model_filtering_by_capability(
        self, registry: ProviderRegistry, router: CapabilityRouter
    ) -> None:
        """Step 2: Models filtered by specific capability."""
        models = [
            ModelSpec(id="chat-model", capabilities=[CapabilityType.CHAT]),
            ModelSpec(id="embed-model", capabilities=[CapabilityType.EMBED]),
        ]
        _register_provider(
            registry,
            "multi-provider",
            capabilities=[CapabilityType.CHAT, CapabilityType.EMBED],
            models=models,
        )

        result = router.route(CapabilityType.CHAT, _make_constraints())
        assert len(result) == 1
        # Should have filtered to only CHAT-capable model
        chat_models = [
            m for m in result[0].eligible_models if CapabilityType.CHAT in m.capabilities
        ]
        assert len(chat_models) >= 1

    def test_route_with_token_estimate(
        self,
        registry: ProviderRegistry,
        router: CapabilityRouter,
        rate_limiter: _StubRateLimiter,
    ) -> None:
        """Token estimate passed to rate limiter."""
        _register_provider(registry, "openai", [CapabilityType.CHAT])

        result = router.route(
            CapabilityType.CHAT,
            _make_constraints(),
            token_estimate=5000,
        )
        assert len(result) == 1

    def test_route_combined_filters(
        self,
        registry: ProviderRegistry,
        router: CapabilityRouter,
        circuit_breaker: _StubCircuitBreaker,
        rate_limiter: _StubRateLimiter,
        health_monitor: _StubHealthMonitor,
    ) -> None:
        """Multiple providers with different filter reasons."""
        _register_provider(registry, "p1", [CapabilityType.CHAT])
        _register_provider(registry, "p2", [CapabilityType.CHAT])
        _register_provider(registry, "p3", [CapabilityType.CHAT])
        _register_provider(registry, "p4", [CapabilityType.CHAT])

        circuit_breaker.set_state("p1", CircuitState.OPEN)  # filtered by CB
        rate_limiter.block("p2")  # filtered by rate limit
        health_monitor.set_status("p3", HealthStatus.UNHEALTHY)  # filtered by health
        # p4 passes all filters

        result = router.route(CapabilityType.CHAT, _make_constraints())
        assert len(result) == 1
        assert result[0].provider_info.provider_id == "p4"


# ===========================================================================
# Static Method Tests
# ===========================================================================


class TestFilterModelsByCapability:
    """Tests for CapabilityRouter._filter_models_by_capability."""

    def test_filter_matching_models(self) -> None:
        models = [
            ModelSpec(id="chat", capabilities=[CapabilityType.CHAT]),
            ModelSpec(id="embed", capabilities=[CapabilityType.EMBED]),
            ModelSpec(id="both", capabilities=[CapabilityType.CHAT, CapabilityType.EMBED]),
        ]
        result = CapabilityRouter._filter_models_by_capability(models, CapabilityType.CHAT)
        assert len(result) == 2
        ids = {m.id for m in result}
        assert ids == {"chat", "both"}

    def test_filter_no_match(self) -> None:
        models = [
            ModelSpec(id="embed", capabilities=[CapabilityType.EMBED]),
        ]
        result = CapabilityRouter._filter_models_by_capability(models, CapabilityType.CHAT)
        assert result == []

    def test_filter_empty_models(self) -> None:
        result = CapabilityRouter._filter_models_by_capability([], CapabilityType.CHAT)
        assert result == []


# ===========================================================================
# Re-exports Test
# ===========================================================================


class TestCapabilityRouterReExports:
    """Test that services/__init__.py re-exports M3 router types."""

    def test_capability_router_reexport(self) -> None:
        from k1.model_hub.services import CapabilityRouter as Reexported

        assert Reexported is CapabilityRouter

    def test_eligible_provider_reexport(self) -> None:
        from k1.model_hub.services import EligibleProvider as Reexported

        assert Reexported is EligibleProvider

    def test_protocol_reexports(self) -> None:
        from k1.model_hub.services import ICircuitBreakerQuery as CB
        from k1.model_hub.services import IHealthQuery as H
        from k1.model_hub.services import IRateLimiterQuery as RL

        assert CB is ICircuitBreakerQuery
        assert RL is IRateLimiterQuery
        assert H is IHealthQuery
