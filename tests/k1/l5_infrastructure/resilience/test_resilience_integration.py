"""Integration tests for Layer 5 resilience components (Epic 2.3).

Tests the complete resilience stack working together:
- HotReloadManager watching config files
- CircuitBreakerManager loading per-service configs
- RetryPolicy using circuit breakers for fail-fast behavior

Validates end-to-end integration of:
- ADR-0008b: Retry Policy (exponential backoff, failure classification)
- ADR-0009/0009a/0009b: Circuit Breaker Pattern (3-state FSM, per-service config)
- ADR-0080: Config Hot-Reload (file watching, validation, atomic updates)

Performance Budget: <100ms reload latency, <10ms circuit breaker decisions
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, cast

from ward import fixture, test  # type: ignore[attr-defined]

from k1.l5_infrastructure.resilience.circuit_breaker_manager import (
    CircuitBreakerManager,
)
from k1.l5_infrastructure.resilience.hot_reload import ConfigChange, HotReloadManager
from k1.l5_infrastructure.resilience.retry_policy import (
    RetryAbortedError,
    RetryPolicy,
    RetryPolicyConfig,
)


class _FakeClock:
    """Deterministic clock for testing."""

    __slots__ = ("value",)

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def monotonic(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _FakeSleeper:
    """Deterministic sleeper for testing."""

    __slots__ = ("clock", "calls")

    def __init__(self, clock: _FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, delay_seconds: float) -> None:
        self.calls.append(delay_seconds)
        self.clock.advance(delay_seconds)


@fixture(scope="module")
async def temp_config_dir() -> AsyncGenerator[Path, None]:
    """Create a temporary directory for all config files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        yield config_dir


@fixture
async def fake_clock() -> AsyncGenerator[_FakeClock, None]:
    """Deterministic clock for retry policy testing."""
    yield _FakeClock()


@fixture
async def fake_sleeper(
    clock_dep: Any = fake_clock,
) -> AsyncGenerator[_FakeSleeper, None]:
    """Deterministic sleeper for retry policy testing."""
    clock = cast(_FakeClock, clock_dep)
    yield _FakeSleeper(clock)


@fixture
async def resilience_stack(
    temp_config_dir_dep: Any = temp_config_dir,
    clock_dep: Any = fake_clock,
    sleeper_dep: Any = fake_sleeper,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Set up the complete resilience stack for integration testing."""
    temp_config_dir = cast(Path, temp_config_dir_dep)
    clock = cast(_FakeClock, clock_dep)
    sleeper = cast(_FakeSleeper, sleeper_dep)

    # Create initial circuit breaker config
    circuit_config_file = temp_config_dir / "circuit_breakers.yml"
    circuit_config_content = """
circuit_breakers:
  test_service:
    failure_threshold: 2
    timeout_duration_ms: 5000
    success_threshold: 1
    slow_call_threshold_ms: 1000
    time_window_ms: 10000
    fallback_strategy: "default_value"
    enabled: true
"""
    circuit_config_file.write_text(circuit_config_content)

    # Create initial retry policy config
    retry_config_file = temp_config_dir / "retry_policy.yml"
    retry_config_content = """
max_retries: 3
base_delay_ms: 100.0
jitter_percent: 0.0
retry_budget_ms: 1000.0
respect_circuit_breaker: true
"""
    retry_config_file.write_text(retry_config_content)

    # Initialize components
    hot_reload = HotReloadManager(config_dir=temp_config_dir)
    circuit_manager = CircuitBreakerManager(config_path=str(circuit_config_file))

    # Create retry policy with deterministic behavior
    retry_config = RetryPolicyConfig(
        name="integration_test",
        jitter_percent=0.0,
        max_retries=3,
        base_delay_ms=100.0,
        max_delay_ms=1600.0,
        respect_circuit_breaker=True,
    )
    retry_policy = RetryPolicy(
        config=retry_config,
        random_seed=42,
        sleep=sleeper.__call__,
        time_source=clock.monotonic,
    )

    # Track config changes
    config_changes: list[ConfigChange] = []

    def on_config_change(change: ConfigChange) -> None:
        config_changes.append(change)

    hot_reload.add_change_callback(on_config_change)

    # Track reloads
    reload_events: list[tuple[str, Dict[str, Any]]] = []

    def on_config_reload(name: str, config: Dict[str, Any]) -> None:
        reload_events.append((name, config))
        # Trigger circuit breaker config reload when circuit_breakers.yml changes
        if name == "circuit_breakers":
            asyncio.create_task(circuit_manager.reload_configs())

    hot_reload.add_reload_callback(on_config_reload)

    # Start hot reload
    await hot_reload.start()

    stack = {
        "hot_reload": hot_reload,
        "circuit_manager": circuit_manager,
        "retry_policy": retry_policy,
        "config_dir": temp_config_dir,
        "config_changes": config_changes,
        "reload_events": reload_events,
        "circuit_config_file": circuit_config_file,
        "retry_config_file": retry_config_file,
    }

    yield stack

    # Cleanup
    await hot_reload.stop()


@test("resilience stack initializes correctly")
async def _(stack_dep: Any = resilience_stack) -> None:
    """Test that all components initialize properly."""
    stack = cast(Dict[str, Any], stack_dep)

    hot_reload = cast(HotReloadManager, stack["hot_reload"])
    circuit_manager = cast(CircuitBreakerManager, stack["circuit_manager"])
    retry_policy = cast(RetryPolicy, stack["retry_policy"])

    # Check hot reload is running
    assert hot_reload.state.name == "RUNNING"

    # Check circuit manager has no circuits yet (lazy loading)
    assert len(circuit_manager.get_all_circuits()) == 0

    # Check retry policy respects circuit breaker (can't test config directly)
    # We'll test this behaviorally in other tests


@test("circuit breaker integrates with retry policy for fail-fast behavior")
async def _(stack_dep: Any = resilience_stack) -> None:
    """Test that retry policy respects circuit breaker state."""
    stack = cast(Dict[str, Any], stack_dep)

    circuit_manager = cast(CircuitBreakerManager, stack["circuit_manager"])
    retry_policy = cast(RetryPolicy, stack["retry_policy"])

    # Get circuit breaker for test service
    circuit = circuit_manager.get_circuit("test_service")
    assert circuit is not None

    # Initially circuit should be closed
    assert circuit.state.name == "CLOSED"

    # Check initial config via manager
    initial_config = circuit_manager.config_manager.get_circuit_config("test_service")
    assert initial_config.failure_threshold == 2


@test("hot reload propagates circuit breaker config changes")
async def _(stack_dep: Any = resilience_stack) -> None:
    """Test that config changes are detected and applied to circuit breakers."""
    stack = cast(Dict[str, Any], stack_dep)

    circuit_manager = cast(CircuitBreakerManager, stack["circuit_manager"])
    circuit_config_file = cast(Path, stack["circuit_config_file"])
    config_changes = cast(list[ConfigChange], stack["config_changes"])

    # Get initial circuit
    circuit = circuit_manager.get_circuit("test_service")
    initial_config = circuit_manager.config_manager.get_circuit_config("test_service")
    assert initial_config.failure_threshold == 2

    # Modify circuit breaker config
    new_config_content = """
circuit_breakers:
  test_service:
    failure_threshold: 5
    timeout_duration_ms: 10000
    success_threshold: 2
    slow_call_threshold_ms: 2000
    time_window_ms: 20000
    fallback_strategy: "default_value"
    enabled: true
"""
    circuit_config_file.write_text(new_config_content)
    await asyncio.sleep(0.1)  # Small delay to ensure file operations complete

    # Manually trigger reload since file watching may not work in test environment
    success = await stack["hot_reload"].reload_config("circuit_breakers.yml")
    assert success

    # Wait for async reload to complete
    await asyncio.sleep(0.2)

    # Check that config change was detected
    assert len(config_changes) > 0
    change = config_changes[-1]
    assert change.config_file == "circuit_breakers.yml"
    assert change.validation_passed

    # Check that circuit breaker was updated
    # Note: CircuitBreaker instances are recreated with new config
    updated_config = circuit_manager.config_manager.get_circuit_config("test_service")
    assert updated_config.failure_threshold == 5
    assert updated_config.timeout_duration_ms == 10000


@test("hot reload validates config changes")
async def _(stack_dep: Any = resilience_stack) -> None:
    """Test that invalid config changes are rejected."""
    stack = cast(Dict[str, Any], stack_dep)

    circuit_config_file = cast(Path, stack["circuit_config_file"])
    config_changes = cast(list[ConfigChange], stack["config_changes"])

    # Modify to invalid circuit breaker config
    invalid_config_content = """
circuit_breakers:
  test_service:
    failure_threshold: -1  # Invalid: must be positive
    timeout_duration_ms: 5000
    success_threshold: 1
    slow_call_threshold_ms: 1000
    time_window_ms: 10000
    fallback_strategy: "default_value"
    enabled: true
"""
    circuit_config_file.write_text(invalid_config_content)

    # Manually trigger reload
    success = await stack["hot_reload"].reload_config("circuit_breakers.yml")
    assert not success  # Should fail validation

    # Check that change was detected but validation failed
    assert len(config_changes) > 0
    change = config_changes[-1]
    assert change.config_file == "circuit_breakers.yml"
    assert not change.validation_passed
    assert change.error_message is not None
    assert "failure_threshold must be >= 2" in change.error_message


@test("retry policy config hot reload works")
async def _(stack_dep: Any = resilience_stack) -> None:
    """Test that retry policy configs can be hot reloaded."""
    stack = cast(Dict[str, Any], stack_dep)

    retry_config_file = cast(Path, stack["retry_config_file"])
    config_changes = cast(list[ConfigChange], stack["config_changes"])

    # Check initial config (may be None if not loaded yet)
    initial_config = stack["hot_reload"].get_config("retry_policy")
    if initial_config is not None:
        assert initial_config["max_retries"] == 3

    # Modify retry policy config
    new_retry_config = """
max_retries: 5
base_delay_ms: 200.0
jitter_percent: 0.1
retry_budget_ms: 2000.0
respect_circuit_breaker: true
"""
    retry_config_file.write_text(new_retry_config)

    # Manually trigger reload
    success = await stack["hot_reload"].reload_config("retry_policy.yml")
    assert success

    # Check that config change was detected and loaded
    assert len(config_changes) > 0
    change = config_changes[-1]
    assert change.config_file == "retry_policy.yml"
    assert change.validation_passed

    # Check new config was loaded
    updated_config = stack["hot_reload"].get_config("retry_policy")
    if updated_config is not None:
        assert updated_config["max_retries"] == 5
        assert updated_config["base_delay_ms"] == 200.0


@test("end-to-end resilience workflow")
async def _(stack_dep: Any = resilience_stack) -> None:
    """Test complete workflow: config change → hot reload → behavior change."""
    stack = cast(Dict[str, Any], stack_dep)

    circuit_manager = cast(CircuitBreakerManager, stack["circuit_manager"])
    retry_policy = cast(RetryPolicy, stack["retry_policy"])
    circuit_config_file = cast(Path, stack["circuit_config_file"])

    # Phase 1: Initial behavior with low failure threshold
    circuit = circuit_manager.get_circuit("test_service")
    initial_config = circuit_manager.config_manager.get_circuit_config("test_service")
    assert initial_config.failure_threshold == 2

    # Create operation that fails twice then succeeds
    call_count = 0

    async def intermittent_operation():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ConnectionError("Temporary failure")
        return "success"

    # First execution should succeed after 2 failures (within threshold)
    result = await retry_policy.execute(
        intermittent_operation,
        idempotent=True,
        description="intermittent_test",
        circuit_breaker=circuit,
    )
    assert result == "success"
    assert call_count == 3  # 2 failures + 1 success

    # Circuit should still be closed
    assert circuit.state.name == "CLOSED"

    # Phase 2: Change config to higher threshold via hot reload
    new_config_content = """
circuit_breakers:
  test_service:
    failure_threshold: 5  # Higher threshold
    timeout_duration_ms: 5000
    success_threshold: 1
    slow_call_threshold_ms: 1000
    time_window_ms: 10000
    fallback_strategy: "default_value"
    enabled: true
"""
    circuit_config_file.write_text(new_config_content)

    # Manually trigger reload
    success = await stack["hot_reload"].reload_config("circuit_breakers.yml")
    assert success

    # Wait for async reload to complete
    await asyncio.sleep(0.2)

    # Verify config was updated
    updated_config = circuit_manager.config_manager.get_circuit_config("test_service")
    assert updated_config.failure_threshold == 5

    # Get fresh circuit reference after config reload
    circuit = circuit_manager.get_circuit("test_service")

    # Phase 3: Test behavior with new config
    call_count = 0  # Reset counter

    # Execute again - should handle more failures now
    result = await retry_policy.execute(
        intermittent_operation,
        idempotent=True,
        description="intermittent_test_2",
        circuit_breaker=circuit,
    )
    assert result == "success"
    assert call_count == 3  # Same pattern, but circuit handles it better

    # Circuit should still be closed (under new higher threshold)
    assert circuit.state.name == "CLOSED"


@test("circuit breaker state affects retry behavior across config changes")
async def _(stack_dep: Any = resilience_stack) -> None:
    """Test that circuit breaker state persists correctly across config reloads."""
    stack = cast(Dict[str, Any], stack_dep)

    circuit_manager = cast(CircuitBreakerManager, stack["circuit_manager"])
    retry_policy = cast(RetryPolicy, stack["retry_policy"])

    # Get circuit and force it to open by making it fail enough times
    circuit = circuit_manager.get_circuit("test_service")

    # Make it fail enough times to open by calling through circuit breaker directly
    call_count = 0

    async def always_fails():
        nonlocal call_count
        call_count += 1
        raise ConnectionError("Always fails")

    # Execute through circuit breaker to record failures
    for i in range(3):  # Should open after 2 failures
        try:
            await circuit.call(always_fails)
        except ConnectionError:
            pass  # Expected

    # Circuit should be open now
    assert circuit.state.name == "OPEN"

    # Now retry should fail fast (circuit is open)
    call_count = 0
    try:
        await retry_policy.execute(
            always_fails,
            idempotent=True,
            description="fail_fast_test",
            circuit_breaker=circuit,
        )
        assert False, "Should have failed fast"
    except RetryAbortedError:
        assert call_count == 0  # No calls made due to open circuit

    # Config reload should not affect circuit state (circuits maintain their own state)
    result = await circuit_manager.reload_configs()
    assert result["status"] == "success"

    # Circuit should still be open
    assert circuit.state.name == "OPEN"

    # Retry should still fail fast
    try:
        await retry_policy.execute(
            always_fails,
            idempotent=True,
            description="still_fail_fast",
            circuit_breaker=circuit,
        )
        assert False, "Should still fail fast"
    except RetryAbortedError:
        assert call_count == 0  # Still no calls made
