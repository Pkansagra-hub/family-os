"""
Tests for CapabilityRegistry.

Issue 1.2.1: Create CapabilityRegistry Class
ADR: ADR-K004 Capability Mesh Architecture
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from k0.fabric import (
    CapabilityRegistry,
    RegisteredProvider,
    ResolutionStrategy,
    get_capability_registry,
    reset_capability_registry,
)
from k0.runtime.schemas import CapabilityProvider, ProviderType

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def registry() -> CapabilityRegistry:
    """Create a fresh registry for each test."""
    return CapabilityRegistry()


@pytest.fixture
def module_provider() -> CapabilityProvider:
    """Create a module provider fixture."""
    return CapabilityProvider(
        type=ProviderType.MODULE,
        module_id="salience.score",
        priority=1,
    )


@pytest.fixture
def module_provider_low_priority() -> CapabilityProvider:
    """Create a low priority module provider fixture."""
    return CapabilityProvider(
        type=ProviderType.MODULE,
        module_id="salience.score_fallback",
        priority=10,
    )


@pytest.fixture
def pipeline_provider() -> CapabilityProvider:
    """Create a pipeline provider fixture."""
    return CapabilityProvider(
        type=ProviderType.PIPELINE,
        pipeline_id="P03_CONSOLIDATION",
        request_topic="fabric.consolidation.request.v1",
        response_topic="fabric.consolidation.response.v1",
        priority=5,
    )


@pytest.fixture(autouse=True)
def reset_global_registry():
    """Reset global registry before and after each test."""
    reset_capability_registry()
    yield
    reset_capability_registry()


# -----------------------------------------------------------------------------
# Registration Tests
# -----------------------------------------------------------------------------


class TestRegistration:
    """Tests for provider registration."""

    def test_register_single_provider(
        self, registry: CapabilityRegistry, module_provider: CapabilityProvider
    ):
        """Register a single provider for a capability."""
        registry.register("score_salience", module_provider)

        assert registry.has_capability("score_salience")
        providers = registry.list_providers("score_salience")
        assert len(providers) == 1
        assert providers[0].provider.module_id == "salience.score"

    def test_register_multiple_providers_sorted_by_priority(
        self,
        registry: CapabilityRegistry,
        module_provider: CapabilityProvider,
        module_provider_low_priority: CapabilityProvider,
    ):
        """Multiple providers are sorted by priority (lower = higher priority)."""
        # Register low priority first
        registry.register("score_salience", module_provider_low_priority)
        # Register high priority second
        registry.register("score_salience", module_provider)

        providers = registry.list_providers("score_salience")
        assert len(providers) == 2
        # Higher priority (lower number) should be first
        assert providers[0].provider.module_id == "salience.score"
        assert providers[0].provider.priority == 1
        assert providers[1].provider.module_id == "salience.score_fallback"
        assert providers[1].provider.priority == 10

    def test_register_with_handler(
        self, registry: CapabilityRegistry, module_provider: CapabilityProvider
    ):
        """Register a provider with a handler function."""

        def handler(content: str) -> float:
            return 0.5

        registry.register("score_salience", module_provider, handler=handler)

        resolved = registry.resolve("score_salience")
        assert resolved is not None
        assert resolved.handler is handler
        assert resolved.handler(content="test") == 0.5

    def test_register_pipeline_provider(
        self, registry: CapabilityRegistry, pipeline_provider: CapabilityProvider
    ):
        """Register a pipeline provider."""
        registry.register("consolidate_memory", pipeline_provider)

        resolved = registry.resolve("consolidate_memory")
        assert resolved is not None
        assert resolved.provider.pipeline_id == "P03_CONSOLIDATION"
        assert resolved.provider.request_topic == "fabric.consolidation.request.v1"


# -----------------------------------------------------------------------------
# Resolution Tests
# -----------------------------------------------------------------------------


class TestResolution:
    """Tests for capability resolution."""

    def test_resolve_returns_highest_priority(
        self,
        registry: CapabilityRegistry,
        module_provider: CapabilityProvider,
        module_provider_low_priority: CapabilityProvider,
    ):
        """Resolve returns the highest priority provider."""
        registry.register("score_salience", module_provider_low_priority)
        registry.register("score_salience", module_provider)

        resolved = registry.resolve("score_salience", ResolutionStrategy.PRIORITY)
        assert resolved is not None
        assert resolved.provider.module_id == "salience.score"

    def test_resolve_first_strategy(
        self,
        registry: CapabilityRegistry,
        module_provider: CapabilityProvider,
        module_provider_low_priority: CapabilityProvider,
    ):
        """FIRST strategy returns the first registered (after sorting)."""
        registry.register("score_salience", module_provider_low_priority)
        registry.register("score_salience", module_provider)

        resolved = registry.resolve("score_salience", ResolutionStrategy.FIRST)
        assert resolved is not None
        # After sorting, high priority is first
        assert resolved.provider.module_id == "salience.score"

    def test_resolve_round_robin_cycles(
        self,
        registry: CapabilityRegistry,
        module_provider: CapabilityProvider,
        module_provider_low_priority: CapabilityProvider,
    ):
        """ROUND_ROBIN strategy cycles through providers."""
        registry.register("score_salience", module_provider)
        registry.register("score_salience", module_provider_low_priority)

        # First call - should get first provider
        r1 = registry.resolve("score_salience", ResolutionStrategy.ROUND_ROBIN)
        # Second call - should get second provider
        r2 = registry.resolve("score_salience", ResolutionStrategy.ROUND_ROBIN)
        # Third call - should cycle back to first
        r3 = registry.resolve("score_salience", ResolutionStrategy.ROUND_ROBIN)

        assert r1 is not None and r2 is not None and r3 is not None
        assert r1.provider.module_id == "salience.score"
        assert r2.provider.module_id == "salience.score_fallback"
        assert r3.provider.module_id == "salience.score"

    def test_resolve_unknown_capability_returns_none(self, registry: CapabilityRegistry):
        """Resolving an unknown capability returns None."""
        resolved = registry.resolve("nonexistent_capability")
        assert resolved is None

    def test_has_capability_false_for_unknown(self, registry: CapabilityRegistry):
        """has_capability returns False for unknown capabilities."""
        assert registry.has_capability("nonexistent") is False


# -----------------------------------------------------------------------------
# Unregistration Tests
# -----------------------------------------------------------------------------


class TestUnregistration:
    """Tests for provider unregistration."""

    def test_unregister_removes_provider(
        self, registry: CapabilityRegistry, module_provider: CapabilityProvider
    ):
        """Unregister removes a provider."""
        registry.register("score_salience", module_provider)
        assert registry.has_capability("score_salience")

        result = registry.unregister("score_salience", "salience.score")

        assert result is True
        assert not registry.has_capability("score_salience")

    def test_unregister_unknown_returns_false(self, registry: CapabilityRegistry):
        """Unregister returns False for unknown capability."""
        result = registry.unregister("nonexistent", "some_provider")
        assert result is False

    def test_unregister_unknown_provider_returns_false(
        self, registry: CapabilityRegistry, module_provider: CapabilityProvider
    ):
        """Unregister returns False for unknown provider."""
        registry.register("score_salience", module_provider)

        result = registry.unregister("score_salience", "unknown_provider")
        assert result is False
        # Original provider still there
        assert registry.has_capability("score_salience")


# -----------------------------------------------------------------------------
# Handler Binding Tests
# -----------------------------------------------------------------------------


class TestHandlerBinding:
    """Tests for late handler binding."""

    def test_bind_handler_updates_provider(
        self, registry: CapabilityRegistry, module_provider: CapabilityProvider
    ):
        """bind_handler updates an existing provider."""
        # Register without handler
        registry.register("score_salience", module_provider)

        resolved = registry.resolve("score_salience")
        assert resolved is not None
        assert resolved.handler is None

        # Bind handler later
        def handler(content: str) -> float:
            return 0.75

        result = registry.bind_handler("score_salience", "salience.score", handler)

        assert result is True
        resolved = registry.resolve("score_salience")
        assert resolved is not None
        assert resolved.handler is handler
        assert resolved.handler(content="test") == 0.75

    def test_bind_handler_unknown_provider_returns_false(
        self, registry: CapabilityRegistry, module_provider: CapabilityProvider
    ):
        """bind_handler returns False for unknown provider."""
        registry.register("score_salience", module_provider)

        def handler(content: str) -> float:
            return 0.0

        result = registry.bind_handler("score_salience", "unknown_provider", handler)
        assert result is False


# -----------------------------------------------------------------------------
# Metrics Tests
# -----------------------------------------------------------------------------


class TestMetrics:
    """Tests for call metrics recording."""

    def test_record_call_updates_metrics(
        self, registry: CapabilityRegistry, module_provider: CapabilityProvider
    ):
        """record_call updates provider metrics."""
        registry.register("score_salience", module_provider)

        # Record some calls
        registry.record_call("score_salience", "salience.score", 10.5)
        registry.record_call("score_salience", "salience.score", 15.0)
        registry.record_call("score_salience", "salience.score", 20.0, error=True)

        providers = registry.list_providers("score_salience")
        assert len(providers) == 1
        p = providers[0]
        assert p.call_count == 3
        assert p.total_latency_ms == 45.5
        assert p.error_count == 1
        assert p.avg_latency_ms == pytest.approx(15.166, rel=0.01)

    def test_get_stats_returns_summary(
        self,
        registry: CapabilityRegistry,
        module_provider: CapabilityProvider,
        pipeline_provider: CapabilityProvider,
    ):
        """get_stats returns registry statistics."""
        registry.register("score_salience", module_provider)
        registry.register("consolidate", pipeline_provider)

        registry.record_call("score_salience", "salience.score", 10.0)
        registry.record_call("score_salience", "salience.score", 10.0, error=True)

        stats = registry.get_stats()

        assert stats["capabilities_count"] == 2
        assert stats["providers_count"] == 2
        assert stats["total_calls"] == 2
        assert stats["total_errors"] == 1
        assert "score_salience" in stats["capabilities"]
        assert "consolidate" in stats["capabilities"]


# -----------------------------------------------------------------------------
# RegisteredProvider Tests
# -----------------------------------------------------------------------------


class TestRegisteredProvider:
    """Tests for RegisteredProvider dataclass."""

    def test_provider_id_returns_module_id(self, module_provider: CapabilityProvider):
        """provider_id returns module_id for module providers."""
        registered = RegisteredProvider(
            capability="test",
            provider=module_provider,
        )
        assert registered.provider_id == "salience.score"

    def test_provider_id_returns_pipeline_id(self, pipeline_provider: CapabilityProvider):
        """provider_id returns pipeline_id for pipeline providers."""
        registered = RegisteredProvider(
            capability="test",
            provider=pipeline_provider,
        )
        assert registered.provider_id == "P03_CONSOLIDATION"

    def test_avg_latency_zero_when_no_calls(self, module_provider: CapabilityProvider):
        """avg_latency_ms is 0 when no calls recorded."""
        registered = RegisteredProvider(
            capability="test",
            provider=module_provider,
        )
        assert registered.avg_latency_ms == 0.0


# -----------------------------------------------------------------------------
# Global Registry Tests
# -----------------------------------------------------------------------------


class TestGlobalRegistry:
    """Tests for global registry singleton."""

    def test_global_registry_singleton(self):
        """get_capability_registry returns singleton."""
        r1 = get_capability_registry()
        r2 = get_capability_registry()
        assert r1 is r2

    def test_reset_clears_registry(self, module_provider: CapabilityProvider):
        """reset_capability_registry clears the singleton."""
        registry = get_capability_registry()
        registry.register("test", module_provider)
        assert registry.has_capability("test")

        reset_capability_registry()

        new_registry = get_capability_registry()
        assert not new_registry.has_capability("test")

    def test_reset_creates_new_instance(self):
        """reset creates a new registry instance."""
        r1 = get_capability_registry()
        reset_capability_registry()
        r2 = get_capability_registry()
        assert r1 is not r2


# -----------------------------------------------------------------------------
# Thread Safety Tests
# -----------------------------------------------------------------------------


class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_registration(self, registry: CapabilityRegistry):
        """Concurrent registration is thread-safe."""
        results = []
        errors = []

        # Pre-create valid module IDs (pattern requires lowercase letters/underscore only before :version)
        valid_module_ids = [
            "module_a.test",
            "module_b.test",
            "module_c.test",
            "module_d.test",
            "module_e.test",
            "module_f.test",
            "module_g.test",
            "module_h.test",
            "module_i.test",
            "module_j.test",
            "module_k.test",
            "module_l.test",
            "module_m.test",
            "module_n.test",
            "module_o.test",
            "module_p.test",
            "module_q.test",
            "module_r.test",
            "module_s.test",
            "module_t.test",
        ]

        def register_provider(n: int):
            try:
                provider = CapabilityProvider(
                    type=ProviderType.MODULE,
                    module_id=valid_module_ids[n],
                    priority=n + 1,  # priority must be >= 1
                )
                registry.register("concurrent_test", provider)
                results.append(n)
            except Exception as e:
                errors.append(e)

        # Run 20 concurrent registrations
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(register_provider, i) for i in range(20)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 20
        providers = registry.list_providers("concurrent_test")
        assert len(providers) == 20

    def test_concurrent_resolution(
        self, registry: CapabilityRegistry, module_provider: CapabilityProvider
    ):
        """Concurrent resolution is thread-safe."""
        registry.register("concurrent_resolve", module_provider)

        results = []
        errors = []

        def resolve_provider():
            try:
                resolved = registry.resolve("concurrent_resolve")
                if resolved:
                    results.append(resolved.provider_id)
            except Exception as e:
                errors.append(e)

        # Run 50 concurrent resolutions
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(resolve_provider) for _ in range(50)]
            for f in futures:
                f.result()

        assert len(errors) == 0
        assert len(results) == 50
        assert all(r == "salience.score" for r in results)


# -----------------------------------------------------------------------------
# Clear Tests
# -----------------------------------------------------------------------------


class TestClear:
    """Tests for clearing the registry."""

    def test_clear_removes_all_providers(
        self,
        registry: CapabilityRegistry,
        module_provider: CapabilityProvider,
        pipeline_provider: CapabilityProvider,
    ):
        """clear() removes all registered providers."""
        registry.register("cap1", module_provider)
        registry.register("cap2", pipeline_provider)

        assert len(registry.list_capabilities()) == 2

        registry.clear()

        assert len(registry.list_capabilities()) == 0
        assert not registry.has_capability("cap1")
        assert not registry.has_capability("cap2")
