"""Tests for P03 Circuit Breaker (Issue 6.2.5).

Tests circuit breaker state machine and registry.
"""

from __future__ import annotations

import time

import pytest

from k0.pipelines.p03.ops.circuit_breaker import (
    BUS_DISPATCHER_CONFIG,
    FAISS_INDEX_CONFIG,
    P08_EMBEDDING_CONFIG,
    P03CircuitBreaker,
    P03CircuitBreakerConfig,
    P03CircuitBreakerRegistry,
    P03CircuitBreakerState,
    create_p03_circuit_breakers,
)


class TestP03CircuitBreakerState:
    """Tests for P03CircuitBreakerState enum."""

    def test_has_closed(self) -> None:
        """Test CLOSED state exists."""
        assert P03CircuitBreakerState.CLOSED.value == "CLOSED"

    def test_has_open(self) -> None:
        """Test OPEN state exists."""
        assert P03CircuitBreakerState.OPEN.value == "OPEN"

    def test_has_half_open(self) -> None:
        """Test HALF_OPEN state exists."""
        assert P03CircuitBreakerState.HALF_OPEN.value == "HALF_OPEN"


class TestP03CircuitBreakerConfig:
    """Tests for P03CircuitBreakerConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = P03CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.reset_timeout_seconds == 60.0
        assert config.success_threshold == 3
        assert config.half_open_max_requests == 1

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = P03CircuitBreakerConfig(
            failure_threshold=10,
            reset_timeout_seconds=120.0,
            success_threshold=5,
            half_open_max_requests=3,
        )
        assert config.failure_threshold == 10
        assert config.reset_timeout_seconds == 120.0
        assert config.success_threshold == 5
        assert config.half_open_max_requests == 3


class TestPreconfiguredConfigs:
    """Tests for pre-configured circuit breaker configs."""

    def test_p08_embedding_config(self) -> None:
        """Test P08_EMBEDDING_CONFIG exists and is valid."""
        assert P08_EMBEDDING_CONFIG is not None
        assert isinstance(P08_EMBEDDING_CONFIG, P03CircuitBreakerConfig)
        assert P08_EMBEDDING_CONFIG.failure_threshold == 5
        assert P08_EMBEDDING_CONFIG.reset_timeout_seconds == 60.0

    def test_bus_dispatcher_config(self) -> None:
        """Test BUS_DISPATCHER_CONFIG exists and is valid."""
        assert BUS_DISPATCHER_CONFIG is not None
        assert isinstance(BUS_DISPATCHER_CONFIG, P03CircuitBreakerConfig)
        assert BUS_DISPATCHER_CONFIG.failure_threshold == 5
        assert BUS_DISPATCHER_CONFIG.reset_timeout_seconds == 60.0

    def test_faiss_index_config(self) -> None:
        """Test FAISS_INDEX_CONFIG exists and is valid."""
        assert FAISS_INDEX_CONFIG is not None
        assert isinstance(FAISS_INDEX_CONFIG, P03CircuitBreakerConfig)
        assert FAISS_INDEX_CONFIG.failure_threshold == 3
        assert FAISS_INDEX_CONFIG.reset_timeout_seconds == 30.0


class TestP03CircuitBreaker:
    """Tests for P03CircuitBreaker class."""

    @pytest.fixture
    def config(self) -> P03CircuitBreakerConfig:
        """Create test config."""
        return P03CircuitBreakerConfig(
            failure_threshold=3,
            reset_timeout_seconds=0.1,  # Fast timeout for tests
            success_threshold=2,
            half_open_max_requests=2,
        )

    @pytest.fixture
    def breaker(self, config: P03CircuitBreakerConfig) -> P03CircuitBreaker:
        """Create circuit breaker with test config."""
        return P03CircuitBreaker(name="test", config=config)


class TestInitialState(TestP03CircuitBreaker):
    """Tests for initial circuit breaker state."""

    def test_starts_closed(self, breaker: P03CircuitBreaker) -> None:
        """Test breaker starts in CLOSED state."""
        assert breaker.state == P03CircuitBreakerState.CLOSED

    def test_allows_requests_when_closed(self, breaker: P03CircuitBreaker) -> None:
        """Test breaker allows requests when CLOSED."""
        assert breaker.should_allow_request() is True


class TestClosedState(TestP03CircuitBreaker):
    """Tests for CLOSED state behavior."""

    def test_success_keeps_closed(self, breaker: P03CircuitBreaker) -> None:
        """Test success keeps breaker CLOSED."""
        breaker.record_success()
        assert breaker.state == P03CircuitBreakerState.CLOSED

    def test_threshold_failures_opens(
        self, breaker: P03CircuitBreaker, config: P03CircuitBreakerConfig
    ) -> None:
        """Test reaching failure threshold opens breaker."""
        for _ in range(config.failure_threshold):
            breaker.record_failure()

        assert breaker.state == P03CircuitBreakerState.OPEN

    def test_below_threshold_stays_closed(
        self, breaker: P03CircuitBreaker, config: P03CircuitBreakerConfig
    ) -> None:
        """Test below threshold stays CLOSED."""
        for _ in range(config.failure_threshold - 1):
            breaker.record_failure()

        assert breaker.state == P03CircuitBreakerState.CLOSED


class TestOpenState(TestP03CircuitBreaker):
    """Tests for OPEN state behavior."""

    def test_blocks_requests_when_open(
        self, breaker: P03CircuitBreaker, config: P03CircuitBreakerConfig
    ) -> None:
        """Test breaker blocks requests when OPEN."""
        # Open the breaker
        for _ in range(config.failure_threshold):
            breaker.record_failure()

        assert breaker.should_allow_request() is False

    def test_transitions_to_half_open_after_timeout(
        self, breaker: P03CircuitBreaker, config: P03CircuitBreakerConfig
    ) -> None:
        """Test breaker transitions to HALF_OPEN after timeout."""
        # Open the breaker
        for _ in range(config.failure_threshold):
            breaker.record_failure()

        # Wait for recovery timeout
        time.sleep(config.reset_timeout_seconds + 0.05)

        # Check request should trigger HALF_OPEN
        assert breaker.should_allow_request() is True
        assert breaker.state == P03CircuitBreakerState.HALF_OPEN


class TestReset(TestP03CircuitBreaker):
    """Tests for reset method."""

    def test_reset_closes_breaker(
        self, breaker: P03CircuitBreaker, config: P03CircuitBreakerConfig
    ) -> None:
        """Test reset closes breaker."""
        # Open the breaker
        for _ in range(config.failure_threshold):
            breaker.record_failure()

        breaker.reset()
        assert breaker.state == P03CircuitBreakerState.CLOSED


class TestP03CircuitBreakerRegistry:
    """Tests for P03CircuitBreakerRegistry class."""

    @pytest.fixture
    def registry(self) -> P03CircuitBreakerRegistry:
        """Create empty registry."""
        return P03CircuitBreakerRegistry()

    def test_register_adds_breaker(self, registry: P03CircuitBreakerRegistry) -> None:
        """Test register adds breaker."""
        config = P03CircuitBreakerConfig()
        registry.register("test", config)

        assert registry.get("test") is not None

    def test_get_returns_breaker(self, registry: P03CircuitBreakerRegistry) -> None:
        """Test get returns registered breaker."""
        config = P03CircuitBreakerConfig()
        registry.register("test", config)

        breaker = registry.get("test")
        assert isinstance(breaker, P03CircuitBreaker)

    def test_reset_all(self, registry: P03CircuitBreakerRegistry) -> None:
        """Test reset_all resets all breakers."""
        config = P03CircuitBreakerConfig(failure_threshold=2)
        registry.register("breaker1", config)
        registry.register("breaker2", config)

        # Open both breakers
        for name in ["breaker1", "breaker2"]:
            breaker = registry.get(name)
            assert breaker is not None
            for _ in range(config.failure_threshold):
                breaker.record_failure()

        registry.reset_all()

        for name in ["breaker1", "breaker2"]:
            breaker = registry.get(name)
            assert breaker is not None
            assert breaker.state == P03CircuitBreakerState.CLOSED


class TestCreateP03CircuitBreakers:
    """Tests for create_p03_circuit_breakers factory."""

    def test_creates_registry(self) -> None:
        """Test factory creates registry."""
        registry = create_p03_circuit_breakers()
        assert isinstance(registry, P03CircuitBreakerRegistry)

    def test_includes_p08_embedding(self) -> None:
        """Test registry includes p08_embedding breaker."""
        registry = create_p03_circuit_breakers()
        assert registry.get("p08_embedding") is not None

    def test_includes_bus_dispatcher(self) -> None:
        """Test registry includes bus_dispatcher breaker."""
        registry = create_p03_circuit_breakers()
        assert registry.get("bus_dispatcher") is not None

    def test_includes_faiss_index(self) -> None:
        """Test registry includes faiss_index breaker."""
        registry = create_p03_circuit_breakers()
        assert registry.get("faiss_index") is not None
