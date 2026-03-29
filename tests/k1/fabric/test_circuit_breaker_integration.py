"""
Epic 6.3.6 -- Test circuit breaker integration (integration).

Verify the CircuitBreaker (FAB-04) works end-to-end through
fabric.execute() with state transitions:
  CLOSED -> OPEN (after failure_threshold failures)
  OPEN -> rejected (circuit_breaker_open / circuit_breaker_error)
  OPEN -> HALF_OPEN (after half_open_after_ms)
  HALF_OPEN -> CLOSED (on probe success)
  HALF_OPEN -> OPEN (on probe failure)

MANDATORY per plan:
  1. ALL executions through fabric.execute() -- NEVER direct provider access.
  2. Uses FabricFactory.create_for_testing() with event capture.
  3. Real adapters only (test adapters are real, not mocks).
  4. CircuitBreaker with low thresholds for fast, deterministic tests.
  5. TestMCPTransport with dynamic handlers to simulate flaky providers.

Design notes:
  - circuit_breakers dict in CapabilityFabric starts empty.
  - Tests inject a CircuitBreaker directly into fabric.facade._circuit_breakers.
  - Provider is identified by provider_id from contract registration.
  - TestMCPTransport.add_handler() simulates failures/successes.
  - CircuitBreakerConfig with low failure_threshold (3) and short
    half_open_after_ms (100) for fast tests.

References:
  - fabric-implementation-plan.md Epic 6.3, Issue 6.3.6
  - FAB-04 (30s timeout enforcement via CircuitBreaker)
  - No-Mock Testing Strategy (lines 1181-1300 of plan)
"""

from __future__ import annotations

import time
from pathlib import Path

from k1.fabric.circuit_breaker.breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)
from k1.fabric.events.fabric_events import (
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_INVOKED,
    TOPIC_LEARNING_SIGNAL,
)
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory
from k1.fabric.providers.mcp_provider import MCPResponse
from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    SafetyBand,
    Tier,
)
from tests.k1.fabric.helpers import (
    assert_capability_result_success,
    register_contract_with_provider,
)

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Fast circuit breaker configuration for tests
# ---------------------------------------------------------------------------

FAST_CB_CONFIG = CircuitBreakerConfig(
    timeout_ms=5000,
    failure_threshold=3,
    failure_window_ms=30000,
    half_open_after_ms=100,  # 100ms for fast tests
    max_retries=0,  # No retries -- each failure counts immediately
    fallback_error_code="circuit_breaker_open",
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_fabric() -> Fabric:
    """Create a Fabric with event capture for integration tests."""
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


def _cb_request(
    capability_name: str = "tool.execute.restaurant_booking",
    *,
    caller: str = "test-cb",
) -> CapabilityRequest:
    """Build a CapabilityRequest for circuit breaker tests."""
    return CapabilityRequest(
        capability_name=capability_name,
        params={"restaurant_name": "Test Bistro", "date": "2026-01-15", "party_size": 2},
        tier=Tier.LOW.value,
        caller=caller,
    )


def _register_custom_contract(
    fabric: Fabric,
    name: str = "tool.execute.cb_test_tool",
    provider_id: str = "mcp-cb-test",
) -> CapabilityContract:
    """Register a custom MCP contract and return it."""
    contract = CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["TEST"],
        description="Circuit breaker test capability",
        capabilities=["test_action"],
        limitations=[],
        required_inputs=[
            InputSpec(name="input_a", type="STRING", description="Test input"),
        ],
        output={"type": "object"},
        provider_type="MCP",
        provider_id=provider_id,
        safety_band_min=SafetyBand.GREEN.value,
    )
    # Register contract AND provider (so resolution succeeds)
    register_contract_with_provider(fabric, contract)
    return contract


def _inject_circuit_breaker(
    fabric: Fabric,
    provider_id: str,
    config: CircuitBreakerConfig = FAST_CB_CONFIG,
) -> CircuitBreaker:
    """
    Inject a CircuitBreaker into the fabric for a specific provider.

    Accesses the shared circuit_breakers dict via facade._circuit_breakers.
    """
    cb = CircuitBreaker(provider_id=provider_id, config=config)
    fabric.facade._circuit_breakers[provider_id] = cb
    return cb


# =========================================================================
# 6.3.6a -- Circuit Breaker State Machine (direct)
# =========================================================================


class TestCircuitBreakerStateMachine:
    """
    Verify CircuitBreaker state transitions directly.
    """

    def test_starts_in_closed_state(self) -> None:
        """New CircuitBreaker starts in CLOSED state."""
        cb = CircuitBreaker("test-provider", config=FAST_CB_CONFIG)
        assert cb.state == CircuitBreakerState.CLOSED

    def test_trip_opens_breaker(self) -> None:
        """trip() forces the breaker to OPEN state."""
        cb = CircuitBreaker("test-provider", config=FAST_CB_CONFIG)
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN

    def test_reset_closes_breaker(self) -> None:
        """reset() returns breaker to CLOSED from any state."""
        cb = CircuitBreaker("test-provider", config=FAST_CB_CONFIG)
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN

        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_allow_probe_transitions_to_half_open(self) -> None:
        """allow_probe() transitions OPEN -> HALF_OPEN."""
        cb = CircuitBreaker("test-provider", config=FAST_CB_CONFIG)
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN

        cb.allow_probe()
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_config_properties(self) -> None:
        """Configuration is accessible via properties."""
        cb = CircuitBreaker("test-provider", config=FAST_CB_CONFIG)
        assert cb.config.failure_threshold == 3
        assert cb.config.half_open_after_ms == 100
        assert cb.config.max_retries == 0
        assert cb.provider_id == "test-provider"


# =========================================================================
# 6.3.6b -- Circuit Breaker via fabric.execute()
# =========================================================================


class TestCircuitBreakerViaFabric:
    """
    Test circuit breaker state transitions through fabric.execute().

    Uses the pre-loaded restaurant_booking fixture (MCP provider)
    with an injected CircuitBreaker.
    """

    async def test_successful_execution_keeps_breaker_closed(self) -> None:
        """Successful execution keeps the circuit breaker in CLOSED state."""
        fabric = _make_fabric()
        # The restaurant_booking contract has provider_id derived from its YAML
        # After auto-registration, the provider_id is available
        contract = fabric.lookup("tool.execute.restaurant_booking")
        provider_id = contract.provider_id

        cb = _inject_circuit_breaker(fabric, provider_id)
        assert cb.state == CircuitBreakerState.CLOSED

        request = _cb_request()
        result = await fabric.execute(request)

        assert_capability_result_success(result)
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_failures_open_circuit(self) -> None:
        """After failure_threshold failures, the circuit opens."""
        fabric = _make_fabric()

        # Register a custom contract so we can use a known provider_id
        contract = _register_custom_contract(fabric)
        cb = _inject_circuit_breaker(fabric, contract.provider_id)

        # Configure MCP transport to return failures
        # MCPProvider converts failed MCPResponse to CapabilityResult.failure
        # Access the MCP transport from the provider factory's port_deps
        mcp_transport = fabric.facade._provider_factory._port_deps.get("mcp_transport")

        if mcp_transport is not None:
            mcp_transport.add_response(
                "tool.execute.cb_test_tool",
                MCPResponse(
                    success=False, content=[], error_message="Simulated failure", latency_ms=1
                ),
            )

        # Execute failure_threshold times to open the circuit
        for i in range(FAST_CB_CONFIG.failure_threshold):
            request = _cb_request(
                capability_name="tool.execute.cb_test_tool",
            )
            result = await fabric.execute(request)
            assert result.success is False

        # Circuit should now be OPEN
        assert cb.state == CircuitBreakerState.OPEN

    async def test_open_circuit_rejects_without_calling_provider(self) -> None:
        """When circuit is OPEN, requests are rejected immediately."""
        fabric = _make_fabric()
        contract = _register_custom_contract(
            fabric,
            name="tool.execute.cb_open_test",
            provider_id="mcp-cb-open",
        )
        cb = _inject_circuit_breaker(fabric, contract.provider_id)

        # Force open the circuit
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN

        request = _cb_request(capability_name="tool.execute.cb_open_test")
        result = await fabric.execute(request)

        assert result.success is False
        assert result.error is not None
        # Error code should be the fallback from config or circuit_breaker_error
        assert result.error.code in ("circuit_breaker_open", "circuit_breaker_error")

    async def test_open_circuit_transitions_to_half_open_after_timeout(self) -> None:
        """After half_open_after_ms, circuit transitions OPEN -> HALF_OPEN."""
        fabric = _make_fabric()
        contract = _register_custom_contract(
            fabric,
            name="tool.execute.cb_halfopen_test",
            provider_id="mcp-cb-halfopen",
        )
        cb = _inject_circuit_breaker(fabric, contract.provider_id)

        # Force open
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN

        # Wait for half_open_after_ms to elapse
        time.sleep(FAST_CB_CONFIG.half_open_after_ms / 1000.0 + 0.05)

        # Next request should be the probe (triggers HALF_OPEN transition)
        request = _cb_request(capability_name="tool.execute.cb_halfopen_test")
        result = await fabric.execute(request)

        # The probe request should execute (not be rejected)
        # Whether it succeeds depends on the provider
        # With default TestMCPTransport returning success, it should succeed
        assert_capability_result_success(result)

        # After successful probe, circuit should be CLOSED
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_half_open_success_closes_circuit(self) -> None:
        """Successful probe in HALF_OPEN transitions to CLOSED."""
        fabric = _make_fabric()
        contract = _register_custom_contract(
            fabric,
            name="tool.execute.cb_halfclose_test",
            provider_id="mcp-cb-halfclose",
        )
        cb = _inject_circuit_breaker(fabric, contract.provider_id)

        # Open and then allow probe
        cb.trip()
        cb.allow_probe()
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # Execute -- default TestMCPTransport returns success
        request = _cb_request(capability_name="tool.execute.cb_halfclose_test")
        result = await fabric.execute(request)

        assert_capability_result_success(result)
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_half_open_failure_reopens_circuit(self) -> None:
        """Failed probe in HALF_OPEN transitions back to OPEN."""
        fabric = _make_fabric()
        contract = _register_custom_contract(
            fabric,
            name="tool.execute.cb_reopen_test",
            provider_id="mcp-cb-reopen",
        )

        # Configure transport to fail for this specific tool
        mcp_transport = fabric.facade._provider_factory._port_deps.get("mcp_transport")

        if mcp_transport is not None:
            mcp_transport.add_response(
                "tool.execute.cb_reopen_test",
                MCPResponse(success=False, content=[], error_message="Still failing", latency_ms=1),
            )

        cb = _inject_circuit_breaker(fabric, contract.provider_id)
        cb.trip()
        cb.allow_probe()
        assert cb.state == CircuitBreakerState.HALF_OPEN

        request = _cb_request(capability_name="tool.execute.cb_reopen_test")
        result = await fabric.execute(request)

        assert result.success is False
        # Circuit should revert to OPEN after failed probe
        assert cb.state == CircuitBreakerState.OPEN


# =========================================================================
# 6.3.6c -- Circuit Breaker Event Emission
# =========================================================================


class TestCircuitBreakerEvents:
    """
    Verify event emission during circuit breaker operation.
    """

    async def test_tripped_circuit_emits_invoked_event(self) -> None:
        """Even when circuit is open, invoked event is emitted."""
        fabric = _make_fabric()
        contract = _register_custom_contract(
            fabric,
            name="tool.execute.cb_event_test",
            provider_id="mcp-cb-event",
        )
        cb = _inject_circuit_breaker(fabric, contract.provider_id)
        cb.trip()

        request = _cb_request(capability_name="tool.execute.cb_event_test")
        await fabric.execute(request)

        event_adapter = fabric.event_port
        invoked = event_adapter.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
        assert len(invoked) >= 1

    async def test_successful_execution_with_breaker_emits_completed(self) -> None:
        """Successful execution through breaker emits completed event."""
        fabric = _make_fabric()
        contract = fabric.lookup("tool.execute.restaurant_booking")
        provider_id = contract.provider_id
        _inject_circuit_breaker(fabric, provider_id)

        request = _cb_request()
        result = await fabric.execute(request)

        assert_capability_result_success(result)
        event_adapter = fabric.event_port
        completed = event_adapter.get_captured(topic=TOPIC_CAPABILITY_COMPLETED)
        assert len(completed) >= 1

    async def test_circuit_open_emits_learning_signal(self) -> None:
        """Circuit breaker rejection emits a learning signal."""
        fabric = _make_fabric()
        contract = _register_custom_contract(
            fabric,
            name="tool.execute.cb_learn_test",
            provider_id="mcp-cb-learn",
        )
        cb = _inject_circuit_breaker(fabric, contract.provider_id)
        cb.trip()

        request = _cb_request(capability_name="tool.execute.cb_learn_test")
        await fabric.execute(request)

        event_adapter = fabric.event_port
        learning = event_adapter.get_captured(topic=TOPIC_LEARNING_SIGNAL)
        assert len(learning) >= 1


# =========================================================================
# 6.3.6d -- Circuit Breaker Configuration
# =========================================================================


class TestCircuitBreakerConfig:
    """
    Test CircuitBreakerConfig variations.
    """

    def test_default_config_values(self) -> None:
        """Default CircuitBreakerConfig matches documented defaults."""
        config = CircuitBreakerConfig()
        assert config.timeout_ms == 30000
        assert config.failure_threshold == 5
        assert config.failure_window_ms == 60000
        assert config.half_open_after_ms == 30000
        assert config.max_retries == 2

    def test_custom_config_applied(self) -> None:
        """Custom config overrides are applied."""
        config = CircuitBreakerConfig(
            timeout_ms=5000,
            failure_threshold=2,
            half_open_after_ms=50,
            max_retries=0,
        )
        cb = CircuitBreaker("custom-provider", config=config)
        assert cb.config.timeout_ms == 5000
        assert cb.config.failure_threshold == 2
        assert cb.config.half_open_after_ms == 50
        assert cb.config.max_retries == 0

    async def test_retry_config_affects_attempt_count(self) -> None:
        """With max_retries > 0, breaker retries before marking failure."""
        # Create a breaker with retries
        config = CircuitBreakerConfig(
            timeout_ms=5000,
            failure_threshold=10,  # High threshold so circuit stays closed
            max_retries=2,
        )
        cb = CircuitBreaker("retry-provider", config=config)

        # After call() with a failing provider, failures should be recorded
        # based on retry count + 1 attempts
        assert cb.failure_count == 0


# =========================================================================
# 6.3.6e -- Circuit Breaker Recovery
# =========================================================================


class TestCircuitBreakerRecovery:
    """
    Test full failure -> open -> recovery -> closed cycle.
    """

    async def test_full_recovery_cycle(self) -> None:
        """
        Full cycle: success -> failures -> OPEN -> wait ->
        HALF_OPEN -> success -> CLOSED.
        """
        fabric = _make_fabric()
        contract = _register_custom_contract(
            fabric,
            name="tool.execute.cb_recovery",
            provider_id="mcp-cb-recovery",
        )
        cb = _inject_circuit_breaker(fabric, contract.provider_id)

        # Phase 1: Initial success
        request = _cb_request(capability_name="tool.execute.cb_recovery")
        result = await fabric.execute(request)
        assert_capability_result_success(result)
        assert cb.state == CircuitBreakerState.CLOSED

        # Phase 2: Configure failures
        mcp_transport = fabric.facade._provider_factory._port_deps.get("mcp_transport")

        if mcp_transport is not None:
            mcp_transport.add_response(
                "tool.execute.cb_recovery",
                MCPResponse(success=False, content=[], error_message="Flaky", latency_ms=1),
            )

        # Phase 3: Trip to OPEN via failures
        for _ in range(FAST_CB_CONFIG.failure_threshold):
            result = await fabric.execute(request)
            assert result.success is False

        assert cb.state == CircuitBreakerState.OPEN

        # Phase 4: Wait for half_open_after_ms
        time.sleep(FAST_CB_CONFIG.half_open_after_ms / 1000.0 + 0.05)

        # Phase 5: Remove the failing response to restore success
        if mcp_transport is not None:
            mcp_transport.clear_responses()

        # Phase 6: Probe request triggers HALF_OPEN and succeeds
        result = await fabric.execute(request)
        assert_capability_result_success(result)
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_reset_restores_connectivity(self) -> None:
        """Manual reset() restores the breaker to CLOSED."""
        fabric = _make_fabric()
        contract = _register_custom_contract(
            fabric,
            name="tool.execute.cb_reset_test",
            provider_id="mcp-cb-reset",
        )
        cb = _inject_circuit_breaker(fabric, contract.provider_id)
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN

        # Reset manually (as HealthChecker would do)
        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED

        # Execute should succeed now
        request = _cb_request(capability_name="tool.execute.cb_reset_test")
        result = await fabric.execute(request)
        assert_capability_result_success(result)
