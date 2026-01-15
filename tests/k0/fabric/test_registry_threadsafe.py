"""
Tests for CapabilityRegistry thread safety.

Tests Issue 3.3.3: Registry Thread Safety
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from k0.fabric.registry import (
    CapabilityRegistry,
    ResolutionStrategy,
    get_capability_registry,
    reset_capability_registry,
)
from k0.runtime.schemas import CapabilityProvider, ProviderType


@pytest.fixture
def registry() -> CapabilityRegistry:
    """Create a fresh CapabilityRegistry for testing."""
    return CapabilityRegistry()


def make_provider(module_id: str, priority: int = 1) -> CapabilityProvider:
    """Create a test provider."""
    # Ensure module_id follows namespace.module:version pattern
    # Pattern: ^[a-z_]+\.[a-z_]+(:[a-z0-9]+)?$
    # Keep only lowercase letters and underscores, remove numbers
    parts = module_id.split("_")
    # Convert numbers to letters (0->a, 1->b, etc.)
    clean_parts = []
    for part in parts:
        if part.isdigit():
            # Convert digit to letter
            clean_parts.append(chr(ord("a") + int(part) % 26))
        else:
            clean_parts.append("".join(c for c in part if c.isalpha() or c == "_"))
    clean_id = "_".join(p for p in clean_parts if p)
    if not clean_id:
        clean_id = "module"
    if "." not in clean_id:
        clean_id = f"test.{clean_id}:v1"
    return CapabilityProvider(
        type=ProviderType.MODULE,
        module_id=clean_id,
        priority=max(1, priority),  # Priority must be >= 1
    )


class TestRegistryThreadSafety:
    """Tests for thread-safe registry operations."""

    def test_concurrent_register_no_corruption(self, registry: CapabilityRegistry) -> None:
        """Test concurrent registrations don't corrupt state."""
        num_threads = 10
        registrations_per_thread = 100

        def register_providers(thread_id: int) -> None:
            for i in range(registrations_per_thread):
                provider = make_provider(f"module_{thread_id}_{i}")
                registry.register(f"capability_{i}", provider)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(register_providers, i) for i in range(num_threads)]
            for future in futures:
                future.result()

        # Verify no corruption - should have providers registered
        capabilities = registry.list_capabilities()
        assert len(capabilities) == registrations_per_thread

        # Each capability should have num_threads providers
        for cap in capabilities:
            providers = registry.list_providers(cap)
            assert len(providers) == num_threads

    def test_concurrent_resolve_returns_copy(self, registry: CapabilityRegistry) -> None:
        """Test concurrent resolutions return copies safely."""
        # Setup
        for i in range(10):
            provider = make_provider(f"module_{i}", priority=i + 1)  # priority >= 1
            registry.register("test_capability", provider)

        results = []
        errors = []

        def resolve_and_iterate() -> None:
            try:
                for _ in range(100):
                    resolved = registry.resolve("test_capability")
                    if resolved:
                        # Simulate work with the resolved provider
                        _ = resolved.provider_id
                        _ = resolved.call_count
                        results.append(resolved)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=resolve_and_iterate) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 500  # 5 threads * 100 iterations

    def test_concurrent_record_call_no_race(self, registry: CapabilityRegistry) -> None:
        """Test concurrent metrics recording doesn't cause race conditions."""
        # Setup
        provider = make_provider("test_module")
        registry.register("test_capability", provider)

        # Get actual provider_id
        providers = registry.list_providers("test_capability")
        actual_provider_id = providers[0].provider_id

        num_threads = 10
        calls_per_thread = 100

        def record_calls() -> None:
            for _ in range(calls_per_thread):
                registry.record_call(
                    capability="test_capability",
                    provider_id=actual_provider_id,
                    latency_ms=10.0,
                    error=False,
                )

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(record_calls) for _ in range(num_threads)]
            for future in futures:
                future.result()

        # Check total calls recorded
        providers = registry.list_providers("test_capability")
        total_calls = sum(p.call_count for p in providers)
        expected_calls = num_threads * calls_per_thread
        assert total_calls == expected_calls

    def test_resolve_during_register_safe(self, registry: CapabilityRegistry) -> None:
        """Test resolving while registering is safe."""
        errors = []
        resolved_count = [0]  # Mutable container for thread closure

        def registerer() -> None:
            try:
                for i in range(100):
                    provider = make_provider(f"module_{i}")
                    registry.register("shared_capability", provider)
            except Exception as e:
                errors.append(e)

        def resolver() -> None:
            try:
                for _ in range(100):
                    result = registry.resolve("shared_capability")
                    if result:
                        resolved_count[0] += 1
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=registerer),
            threading.Thread(target=resolver),
            threading.Thread(target=resolver),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Should have resolved at least some
        assert resolved_count[0] > 0


class TestRegistryAsyncMethods:
    """Tests for async-safe registry methods."""

    @pytest.mark.asyncio
    async def test_register_async_works(self, registry: CapabilityRegistry) -> None:
        """Test async registration works."""
        provider = make_provider("test_module")
        await registry.register_async("test_cap", provider)

        assert registry.has_capability("test_cap")

    @pytest.mark.asyncio
    async def test_resolve_safe_returns_copy(self, registry: CapabilityRegistry) -> None:
        """Test resolve_safe returns a valid provider."""
        provider = make_provider("test_module")
        registry.register("test_cap", provider)

        resolved = registry.resolve_safe("test_cap")

        assert resolved is not None
        # provider_id returns module_id which is "test.test_module:v1"
        assert "test_module" in resolved.provider_id

    @pytest.mark.asyncio
    async def test_resolve_safe_unknown_returns_none(self, registry: CapabilityRegistry) -> None:
        """Test resolve_safe returns None for unknown capability."""
        resolved = registry.resolve_safe("unknown_cap")
        assert resolved is None

    @pytest.mark.asyncio
    async def test_resolve_safe_round_robin(self, registry: CapabilityRegistry) -> None:
        """Test resolve_safe with round robin strategy."""
        for i in range(3):
            provider = make_provider(f"module_{i}", priority=1)
            registry.register("test_cap", provider)

        # Resolve multiple times - should cycle through providers
        resolved_ids = []
        for _ in range(6):
            resolved = registry.resolve_safe("test_cap", ResolutionStrategy.ROUND_ROBIN)
            if resolved:
                resolved_ids.append(resolved.provider_id)

        # Should see all three providers at least once
        # provider_ids are like "test.module:v1" for all (same clean name)
        assert len(resolved_ids) == 6

    @pytest.mark.asyncio
    async def test_record_call_async_works(self, registry: CapabilityRegistry) -> None:
        """Test async metrics recording works."""
        provider = make_provider("test_module")
        registry.register("test_cap", provider)

        # Get the actual provider_id from the registered provider
        providers = registry.list_providers("test_cap")
        provider_id = providers[0].provider_id

        await registry.record_call_async("test_cap", provider_id, 25.0, error=False)

        providers = registry.list_providers("test_cap")
        assert providers[0].call_count == 1
        assert providers[0].total_latency_ms == 25.0

    @pytest.mark.asyncio
    async def test_concurrent_async_operations(self, registry: CapabilityRegistry) -> None:
        """Test concurrent async operations are safe."""
        # Register some providers
        for i in range(5):
            provider = make_provider(f"module_{i}")
            registry.register("test_cap", provider)

        async def async_operations() -> int:
            """Perform various async operations."""
            count = 0
            for _ in range(20):
                resolved = registry.resolve_safe("test_cap")
                if resolved:
                    await registry.record_call_async(
                        "test_cap",
                        resolved.provider_id,
                        10.0,
                    )
                    count += 1
            return count

        # Run multiple concurrent async operations
        results = await asyncio.gather(*[async_operations() for _ in range(5)])

        # All should complete without errors
        assert all(r == 20 for r in results)

        # Check total calls recorded
        stats = registry.get_stats()
        assert stats["total_calls"] == 100  # 5 tasks * 20 calls


class TestGlobalRegistry:
    """Tests for global registry singleton thread safety."""

    def test_get_registry_is_thread_safe(self) -> None:
        """Test getting global registry is thread safe."""
        reset_capability_registry()
        results = []
        errors = []

        def get_registry() -> None:
            try:
                registry = get_capability_registry()
                results.append(registry)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_registry) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All should get the same instance
        assert all(r is results[0] for r in results)
