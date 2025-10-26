"""
Shared test fixtures for K1 L5 Infrastructure tests.

This conftest.py ensures proper initialization order for shared resources
like the K1MetricsCollector singleton, preventing Prometheus registry conflicts.
"""

from prometheus_client import REGISTRY
from ward import Scope, fixture

from k1.l5_infrastructure.observability.metrics import get_k1_metrics

# ==============================================================================
# Global Fixtures - Initialized Once Per Test Session
# ==============================================================================


@fixture(scope=Scope.Global)
def k1_metrics_collector():
    """
    Provide singleton K1MetricsCollector for ALL L5 infrastructure tests.

    Initialized once at test session start to prevent Prometheus duplicate
    metric registration errors. Uses Scope.Global to share instance across
    all test modules.

    **Why Global Scope:**
    - Ward loads all fixtures before running tests
    - Multiple modules importing get_k1_metrics() would create multiple instances
    - Prometheus CollectorRegistry is a global singleton
    - Re-registering metrics causes ValueError

    **Solution:**
    - Initialize ONCE in global-scoped fixture
    - All tests share same K1MetricsCollector instance
    - Prometheus registry stays clean throughout test session
    - Cleanup happens automatically at process exit

    Returns:
        K1MetricsCollector: Singleton metrics collector instance
    """
    return get_k1_metrics()


@fixture(scope=Scope.Module)
def reset_prometheus_registry():
    """
    Tears down Prometheus metrics after each test module completes.

    This fixture uses Ward's generator-based teardown mechanism to ensure
    proper cleanup of Prometheus metrics between test modules. The teardown
    phase runs after ALL tests in a module have completed.

    **How it works:**
    1. Setup phase (before yield): No-op, just marks fixture as active
    2. Tests run in the module
    3. Teardown phase (after yield): Unregister all Prometheus collectors

    **Why this is needed:**
    - Prometheus CollectorRegistry is a global singleton
    - Metrics registered in one module persist across modules
    - Without cleanup, subsequent modules hit duplicate registration errors

    **Usage:**
    Import this fixture in any test module that creates metrics:
    ```python
    from tests.k1.l5_infrastructure.conftest import reset_prometheus_registry

    @test("some test", _=reset_prometheus_registry)
    def _():
        # Your test here
    ```

    Yields:
        None: Yield control to tests, then cleanup in teardown phase
    """
    # Setup phase: no-op (could initialize custom registry here if needed)
    yield

    # Teardown phase: Unregister all collectors from global registry
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except (KeyError, ValueError):
            # Collector already unregistered or not found
            # This is fine - continue cleanup without failing tests
            pass
