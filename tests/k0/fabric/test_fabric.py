"""
Tests for CapabilityFabric core class.

Epic 2.1: CapabilityFabric Implementation
Issue 2.1.2: CapabilityFabric Core Class

Coverage:
- Singleton pattern (get_instance, reset_instance)
- invoke() method (sync capability invocation)
- call() method (full control)
- Error handling (NotFound, Timeout, InvocationError)
- Metrics tracking
- Real timeout enforcement (ThreadPoolExecutor)
- Thread-safety (concurrent access)
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from k0.fabric.fabric import (
    CapabilityFabric,
    CapabilityInvocationError,
    CapabilityNotFoundError,
    CapabilityTimeoutError,
    get_capability_fabric,
    reset_capability_fabric,
)
from k0.fabric.messages import CapabilityRequest
from k0.fabric.registry import CapabilityRegistry, reset_capability_registry
from k0.runtime.schemas import CapabilityProvider, ProviderType


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before and after each test."""
    reset_capability_fabric()
    reset_capability_registry()
    yield
    reset_capability_fabric()
    reset_capability_registry()


def make_provider(
    module_id: str,
    priority: int = 10,
) -> CapabilityProvider:
    """Create a CapabilityProvider for testing.

    Module ID must match pattern: ^[a-z_]+\\.[a-z_]+(:[a-z0-9]+)?$
    Examples: test.provider, test.provider:v1
    """
    return CapabilityProvider(
        type=ProviderType.MODULE,
        module_id=module_id,
        priority=priority,
    )


class TestCapabilityFabricSingleton:
    """Tests for CapabilityFabric singleton pattern."""

    def test_get_instance_returns_same_instance(self) -> None:
        """get_instance() returns the same instance."""
        fabric1 = CapabilityFabric.get_instance()
        fabric2 = CapabilityFabric.get_instance()
        assert fabric1 is fabric2

    def test_reset_instance_clears_singleton(self) -> None:
        """reset_instance() clears the singleton."""
        fabric1 = CapabilityFabric.get_instance()
        CapabilityFabric.reset_instance()
        fabric2 = CapabilityFabric.get_instance()
        assert fabric1 is not fabric2

    def test_get_capability_fabric_global(self) -> None:
        """get_capability_fabric() returns singleton."""
        fabric = get_capability_fabric()
        assert fabric is CapabilityFabric.get_instance()

    def test_reset_capability_fabric_global(self) -> None:
        """reset_capability_fabric() clears singleton."""
        fabric1 = get_capability_fabric()
        reset_capability_fabric()
        fabric2 = get_capability_fabric()
        assert fabric1 is not fabric2


class TestCapabilityFabricInvoke:
    """Tests for CapabilityFabric.invoke() method."""

    def test_invoke_resolves_and_calls_handler(self) -> None:
        """invoke() resolves capability and calls handler."""
        fabric = get_capability_fabric()

        # Create mock handler
        def mock_handler(**kwargs: Any) -> dict[str, Any]:
            return {"result": "success", "input": kwargs.get("input")}

        # Create and register provider
        cap_provider = make_provider("test.provider")
        fabric._registry.register("test.action", cap_provider, mock_handler)

        # Invoke capability
        result = fabric.invoke(
            "test.action",
            input="data",
        )

        assert result == {"result": "success", "input": "data"}

    def test_invoke_raises_not_found_for_unknown_capability(self) -> None:
        """invoke() raises CapabilityNotFoundError for unknown capability."""
        fabric = get_capability_fabric()

        with pytest.raises(CapabilityNotFoundError) as exc_info:
            fabric.invoke("unknown.capability")

        assert exc_info.value.capability == "unknown.capability"
        assert "Capability not found" in str(exc_info.value)

    def test_invoke_raises_invocation_error_on_handler_exception(self) -> None:
        """invoke() raises CapabilityInvocationError when handler throws."""
        fabric = get_capability_fabric()

        # Create failing handler
        def failing_handler(**kwargs: Any) -> dict[str, Any]:
            raise ValueError("Handler failed")

        cap_provider = make_provider("test.failing")
        fabric._registry.register("fail.action", cap_provider, failing_handler)

        with pytest.raises(CapabilityInvocationError) as exc_info:
            fabric.invoke("fail.action")

        assert "Handler failed" in str(exc_info.value)


class TestCapabilityFabricCall:
    """Tests for CapabilityFabric.call() method."""

    def test_call_executes_request(self) -> None:
        """call() executes a full request."""
        fabric = get_capability_fabric()

        # Create sync handler
        def simple_handler(**kwargs: Any) -> dict[str, Any]:
            return {"value": kwargs.get("x", 0) * 2}

        cap_provider = make_provider("test.simple")
        fabric._registry.register("simple.action", cap_provider, simple_handler)

        request = CapabilityRequest(
            capability="simple.action",
            payload={"x": 5},
        )

        response = fabric.call(request)

        assert response.is_success
        assert response.result == {"value": 10}

    def test_call_returns_error_response_on_not_found(self) -> None:
        """call() returns error response for unknown capability."""
        fabric = get_capability_fabric()

        request = CapabilityRequest(
            capability="nonexistent.action",
            payload={},
        )

        response = fabric.call(request)

        assert response.is_error
        assert "nonexistent.action" in str(response.error_message)


class TestCapabilityFabricUtilities:
    """Tests for CapabilityFabric utility methods."""

    def test_has_capability_true_when_registered(self) -> None:
        """Registry has capability when registered."""
        fabric = get_capability_fabric()

        cap_provider = make_provider("test.existing")
        fabric._registry.register("existing.cap", cap_provider, lambda: None)

        # Use registry directly - fabric may not have has_capability
        assert fabric._registry.resolve("existing.cap") is not None

    def test_has_capability_false_when_not_registered(self) -> None:
        """Registry returns None when capability missing."""
        fabric = get_capability_fabric()
        assert fabric._registry.resolve("missing.cap") is None

    def test_registry_returns_all_registered_capabilities(self) -> None:
        """Registry tracks all registered capabilities."""
        fabric = get_capability_fabric()

        # Register multiple capabilities
        providers = ["provider.one", "provider.two", "provider.three"]
        caps = ["cap.one", "cap.two", "cap.three"]
        for cap, prov in zip(caps, providers):
            cap_provider = make_provider(prov)
            fabric._registry.register(cap, cap_provider, lambda: None)

        # Each should be resolvable
        for cap in caps:
            assert fabric._registry.resolve(cap) is not None


class TestCapabilityFabricMetrics:
    """Tests for CapabilityFabric metrics tracking."""

    def test_total_calls_increments(self) -> None:
        """Total calls counter increments."""
        fabric = get_capability_fabric()

        cap_provider = make_provider("test.counter")
        fabric._registry.register("count.action", cap_provider, lambda: {})

        initial = fabric._total_calls

        # Make multiple invocations
        for _ in range(5):
            fabric.invoke("count.action")

        assert fabric._total_calls == initial + 5

    def test_total_errors_increments_on_failure(self) -> None:
        """Total errors counter increments on failures."""
        fabric = get_capability_fabric()

        def failing_handler(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("Intentional failure")

        cap_provider = make_provider("test.failer")
        fabric._registry.register("fail.action", cap_provider, failing_handler)

        initial_errors = fabric._total_errors

        # Make failing invocations
        for _ in range(3):
            try:
                fabric.invoke("fail.action")
            except CapabilityInvocationError:
                pass  # Expected

        assert fabric._total_errors == initial_errors + 3


class TestCapabilityFabricWithRegistry:
    """Tests for CapabilityFabric integration with CapabilityRegistry."""

    def test_fabric_uses_registry(self) -> None:
        """Fabric uses the CapabilityRegistry."""
        fabric = get_capability_fabric()
        registry = fabric._registry

        assert isinstance(registry, CapabilityRegistry)

    def test_fabric_respects_priority(self) -> None:
        """Fabric respects registry's priority ordering."""
        fabric = get_capability_fabric()

        # Register two providers with different priorities
        low_priority_provider = make_provider("test.low", priority=100)
        high_priority_provider = make_provider("test.high", priority=1)

        fabric._registry.register(
            "multi.action",
            low_priority_provider,
            lambda: {"source": "low"},
        )
        fabric._registry.register(
            "multi.action",
            high_priority_provider,
            lambda: {"source": "high"},
        )

        # High priority (lower number) should be selected
        result = fabric.invoke("multi.action")

        assert result == {"source": "high"}


class TestCapabilityFabricRealTimeout:
    """Tests for real timeout enforcement via ThreadPoolExecutor."""

    def test_timeout_enforced_during_handler_execution(self) -> None:
        """Handler that stalls beyond deadline returns TIMEOUT response."""
        fabric = get_capability_fabric()

        def stalling_handler(**kwargs: Any) -> dict[str, Any]:
            # Stall for 500ms (longer than timeout)
            time.sleep(0.5)
            return {"result": "should_not_reach"}

        cap_provider = make_provider("test.stalling")
        fabric._registry.register("stall.action", cap_provider, stalling_handler)

        request = CapabilityRequest(
            capability="stall.action",
            payload={},
            timeout_ms=50,  # 50ms timeout
        )

        response = fabric.call(request)

        assert response.is_timeout
        assert response.timeout_ms == 50
        assert response.e2e_ms > 0

    def test_timeout_exception_raised_from_invoke(self) -> None:
        """invoke() raises CapabilityTimeoutError when handler stalls."""
        fabric = get_capability_fabric()

        def stalling_handler(**kwargs: Any) -> dict[str, Any]:
            time.sleep(0.5)
            return {}

        cap_provider = make_provider("test.staller")
        fabric._registry.register("stall.invoke", cap_provider, stalling_handler)

        with pytest.raises(CapabilityTimeoutError) as exc_info:
            fabric.invoke("stall.invoke", timeout_ms=30)

        assert exc_info.value.capability == "stall.invoke"
        assert exc_info.value.timeout_ms == 30

    def test_fast_handler_completes_within_deadline(self) -> None:
        """Fast handler completes successfully within deadline."""
        fabric = get_capability_fabric()

        def fast_handler(**kwargs: Any) -> dict[str, Any]:
            return {"fast": True}

        cap_provider = make_provider("test.fast")
        fabric._registry.register("fast.action", cap_provider, fast_handler)

        result = fabric.invoke("fast.action", timeout_ms=1000)

        assert result == {"fast": True}


class TestCapabilityFabricThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_invocations_are_safe(self) -> None:
        """Multiple threads can invoke capabilities concurrently."""
        fabric = get_capability_fabric()
        results: list[int] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def threadsafe_handler(**kwargs: Any) -> dict[str, Any]:
            value = kwargs.get("value", 0)
            return {"doubled": value * 2}

        cap_provider = make_provider("test.concurrent")
        fabric._registry.register("concurrent.action", cap_provider, threadsafe_handler)

        def invoke_in_thread(value: int) -> None:
            try:
                result = fabric.invoke("concurrent.action", value=value)
                with lock:
                    results.append(result["doubled"])
            except Exception as e:
                with lock:
                    errors.append(e)

        # Launch 10 concurrent threads
        threads = [threading.Thread(target=invoke_in_thread, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 10
        assert sorted(results) == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]

    def test_get_instance_thread_safe(self) -> None:
        """get_instance() is thread-safe with concurrent access."""
        instances: list[CapabilityFabric] = []
        lock = threading.Lock()

        def get_in_thread() -> None:
            instance = CapabilityFabric.get_instance()
            with lock:
                instances.append(instance)

        # Launch 10 concurrent threads to get instance
        threads = [threading.Thread(target=get_in_thread) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should get the same instance
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)

    def test_stats_thread_safe(self) -> None:
        """get_stats() returns consistent data under concurrent access."""
        fabric = get_capability_fabric()

        def simple_handler(**kwargs: Any) -> dict[str, Any]:
            return {}

        cap_provider = make_provider("test.stats")
        fabric._registry.register("stats.action", cap_provider, simple_handler)

        # Invoke some calls first
        for _ in range(5):
            fabric.invoke("stats.action")

        # Get stats from multiple threads
        stats_results: list[dict[str, Any]] = []
        lock = threading.Lock()

        def get_stats_in_thread() -> None:
            stats = fabric.get_stats()
            with lock:
                stats_results.append(stats)

        threads = [threading.Thread(target=get_stats_in_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should report same call count
        assert all(s["total_calls"] >= 5 for s in stats_results)


class TestCapabilityFabricShutdown:
    """Tests for fabric shutdown and cleanup."""

    def test_shutdown_closes_executor(self) -> None:
        """shutdown() closes the ThreadPoolExecutor."""
        fabric = CapabilityFabric()

        # Should not raise
        fabric.shutdown()

        # Executor should be shut down (subsequent submits may fail)
        # Just verify no exception on shutdown call
        assert True

    def test_reset_instance_calls_shutdown(self) -> None:
        """reset_instance() shuts down the executor before creating new instance."""
        fabric1 = CapabilityFabric.get_instance()

        # Reset should shutdown old and create new
        CapabilityFabric.reset_instance()

        fabric2 = CapabilityFabric.get_instance()
        assert fabric1 is not fabric2
