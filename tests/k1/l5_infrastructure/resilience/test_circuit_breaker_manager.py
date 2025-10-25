"""Component tests for Layer 5 circuit breaker manager (ADR-0009b).

Validates the circuit breaker registry, per-service configuration, and hot reload
for the circuit breaker manager defined in:
- ADR-0009: Circuit Breaker Pattern
- ADR-0009b: Per-Service Circuit Configuration
- ADR-0009c: Circuit Breaker Metrics & Observability
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, cast

from ward import fixture, test  # type: ignore[attr-defined]

from k1.l5_infrastructure.resilience.circuit_breaker_manager import (
    CircuitBreakerManager,
)


@fixture(scope="module")
async def temp_config_dir() -> AsyncGenerator[Path, None]:
    """Create a temporary directory for config files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        yield config_dir


@fixture
async def basic_manager(
    temp_config_dir_dep: Any = temp_config_dir,
) -> AsyncGenerator[CircuitBreakerManager, None]:
    """Create a basic circuit breaker manager."""
    temp_config_dir = cast(Path, temp_config_dir_dep)

    # Create a test config file
    config_file = temp_config_dir / "circuit_breakers.yml"
    config_content = """
circuit_breakers:
  test_service:
    failure_threshold: 3
    timeout_duration_ms: 5000
    success_threshold: 1
    slow_call_threshold_ms: 1000
    time_window_ms: 10000
    fallback_strategy: "default_value"
    enabled: true
"""
    config_file.write_text(config_content)

    manager = CircuitBreakerManager(config_path=str(config_file))
    yield manager


@test("circuit breaker manager initializes correctly")
async def _(basic_manager_dep: Any = basic_manager) -> None:
    """Test that the manager initializes with correct state."""
    manager = cast(CircuitBreakerManager, basic_manager_dep)
    assert len(manager.get_all_circuits()) == 0


@test("circuit breaker manager creates circuits on demand")
async def _(basic_manager_dep: Any = basic_manager) -> None:
    """Test that circuits are created when requested."""
    manager = cast(CircuitBreakerManager, basic_manager_dep)

    # Get circuit for service
    circuit = manager.get_circuit("test_service")
    assert circuit is not None
    assert circuit.service == "test_service"

    # Check it's cached
    circuit2 = manager.get_circuit("test_service")
    assert circuit is circuit2

    # Check stats
    stats = manager.get_circuit_stats()
    assert "test_service" in stats
    assert stats["test_service"]["state"] == "CLOSED"


@test("circuit breaker manager handles disabled circuits")
async def _(temp_config_dir_dep: Any = temp_config_dir) -> None:
    """Test that disabled circuits raise errors."""
    temp_config_dir = cast(Path, temp_config_dir_dep)

    # Create config with disabled circuit
    config_file = temp_config_dir / "circuit_breakers.yml"
    config_content = """
circuit_breakers:
  disabled_service:
    failure_threshold: 3
    timeout_duration_ms: 5000
    success_threshold: 1
    slow_call_threshold_ms: 1000
    time_window_ms: 10000
    fallback_strategy: "default_value"
    enabled: false
"""
    config_file.write_text(config_content)

    manager = CircuitBreakerManager(config_path=str(config_file))

    # Should raise error for disabled circuit
    try:
        manager.get_circuit("disabled_service")
        assert False, "Should have raised CircuitBreakerError"
    except Exception as e:
        assert "disabled" in str(e).lower()


@test("circuit breaker manager uses default config for unknown services")
async def _(basic_manager_dep: Any = basic_manager) -> None:
    """Test that unknown services get default config."""
    manager = cast(CircuitBreakerManager, basic_manager_dep)

    # Get circuit for unknown service
    circuit = manager.get_circuit("unknown_service")
    assert circuit is not None
    assert (
        circuit.service == "unknown_service"
    )  # Uses requested service name when no alternate_service configured
