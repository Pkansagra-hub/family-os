"""Tests for Bus Dispatcher Circuit Breaker (Issue 6.2.7).

Tests bus dispatcher circuit breaker with fallback to outbox.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from k0.pipelines.p03.ops.bus_circuit import (
    BusDispatcherCircuitBreaker,
    EmissionResult,
    EventPriority,
    create_bus_circuit_breaker,
)
from k0.pipelines.p03.ops.circuit_breaker import P03CircuitBreakerState


class TestEventPriority:
    """Tests for EventPriority enum."""

    def test_has_critical(self) -> None:
        """Test CRITICAL priority exists."""
        assert EventPriority.CRITICAL.value == "CRITICAL"

    def test_has_normal(self) -> None:
        """Test NORMAL priority exists."""
        assert EventPriority.NORMAL.value == "NORMAL"

    def test_has_low(self) -> None:
        """Test LOW priority exists."""
        assert EventPriority.LOW.value == "LOW"


class TestEmissionResult:
    """Tests for EmissionResult dataclass."""

    def test_create_success(self) -> None:
        """Test creating success result."""
        result = EmissionResult(success=True, method="direct", event_id="evt-123")
        assert result.success is True
        assert result.method == "direct"
        assert result.event_id == "evt-123"

    def test_create_fallback(self) -> None:
        """Test creating fallback result."""
        result = EmissionResult(success=True, method="outbox", event_id="evt-456")
        assert result.success is True
        assert result.method == "outbox"

    def test_create_dropped(self) -> None:
        """Test creating dropped result."""
        result = EmissionResult(success=False, method="dropped", event_id="evt-789")
        assert result.success is False
        assert result.method == "dropped"


class TestBusDispatcherCircuitBreaker:
    """Tests for BusDispatcherCircuitBreaker class."""

    @pytest.fixture
    def mock_bus_client(self) -> Mock:
        """Create mock bus client."""
        mock = Mock()
        mock.publish = AsyncMock()
        return mock

    @pytest.fixture
    def mock_outbox(self) -> Mock:
        """Create mock outbox publisher."""
        mock = Mock()
        mock.enqueue = AsyncMock()
        return mock

    @pytest.fixture
    def mock_circuit(self) -> Mock:
        """Create mock circuit breaker."""
        mock = Mock()
        mock.state = P03CircuitBreakerState.CLOSED
        mock.should_allow_request = Mock(return_value=True)
        mock.record_success = Mock()
        mock.record_failure = Mock()
        mock.reset = Mock()
        return mock

    @pytest.fixture
    def breaker(
        self, mock_bus_client: Mock, mock_outbox: Mock, mock_circuit: Mock
    ) -> BusDispatcherCircuitBreaker:
        """Create bus circuit breaker with mocks."""
        return BusDispatcherCircuitBreaker(
            bus_client=mock_bus_client,
            outbox_publisher=mock_outbox,
            circuit=mock_circuit,
            metrics=None,
        )


class TestBusProperties(TestBusDispatcherCircuitBreaker):
    """Tests for bus circuit breaker properties."""

    def test_is_open_when_closed(
        self, breaker: BusDispatcherCircuitBreaker, mock_circuit: Mock
    ) -> None:
        """Test is_open returns False when circuit closed."""
        mock_circuit.state = P03CircuitBreakerState.CLOSED
        assert breaker.is_open is False

    def test_is_open_when_open(
        self, breaker: BusDispatcherCircuitBreaker, mock_circuit: Mock
    ) -> None:
        """Test is_open returns True when circuit open."""
        mock_circuit.state = P03CircuitBreakerState.OPEN
        assert breaker.is_open is True


class TestEventPriorityClassification(TestBusDispatcherCircuitBreaker):
    """Tests for event priority classification."""

    def test_droppable_event_is_low(self, breaker: BusDispatcherCircuitBreaker) -> None:
        """Test droppable events classified as LOW."""
        priority = breaker._classify_event_priority("p03.health.heartbeat.v1")
        assert priority == EventPriority.LOW

    def test_error_event_is_critical(self, breaker: BusDispatcherCircuitBreaker) -> None:
        """Test error events classified as CRITICAL."""
        priority = breaker._classify_event_priority("p03.error.fatal.v1")
        assert priority == EventPriority.CRITICAL

    def test_complete_event_is_critical(self, breaker: BusDispatcherCircuitBreaker) -> None:
        """Test complete events classified as CRITICAL."""
        priority = breaker._classify_event_priority("p03.cycle.complete.v1")
        assert priority == EventPriority.CRITICAL

    def test_standard_event_is_normal(self, breaker: BusDispatcherCircuitBreaker) -> None:
        """Test standard events classified as NORMAL."""
        priority = breaker._classify_event_priority("p03.entity.created.v1")
        assert priority == EventPriority.NORMAL


class TestEmit(TestBusDispatcherCircuitBreaker):
    """Tests for emit method."""

    @pytest.mark.asyncio
    async def test_success_returns_direct(
        self,
        breaker: BusDispatcherCircuitBreaker,
        mock_bus_client: Mock,
    ) -> None:
        """Test successful emit returns direct method."""
        event = {"event_id": "evt-123", "event_type": "p03.test.v1"}
        result = await breaker.emit(event)

        assert result.success is True
        assert result.method == "direct"
        assert result.event_id == "evt-123"
        mock_bus_client.publish.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_success_records_success(
        self,
        breaker: BusDispatcherCircuitBreaker,
        mock_circuit: Mock,
    ) -> None:
        """Test successful emit records success."""
        event = {"event_id": "evt-123", "event_type": "p03.test.v1"}
        await breaker.emit(event)

        mock_circuit.record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_records_failure(
        self,
        breaker: BusDispatcherCircuitBreaker,
        mock_bus_client: Mock,
        mock_circuit: Mock,
    ) -> None:
        """Test failed emit records failure."""
        mock_bus_client.publish.side_effect = ConnectionError("Bus down")
        event = {"event_id": "evt-123", "event_type": "p03.test.v1"}

        await breaker.emit(event)

        mock_circuit.record_failure.assert_called_once()


class TestFallbackBehavior(TestBusDispatcherCircuitBreaker):
    """Tests for fallback behavior when circuit open."""

    @pytest.mark.asyncio
    async def test_circuit_open_normal_uses_outbox(
        self,
        breaker: BusDispatcherCircuitBreaker,
        mock_circuit: Mock,
        mock_outbox: Mock,
    ) -> None:
        """Test circuit open queues NORMAL events to outbox."""
        mock_circuit.should_allow_request.return_value = False
        event = {"event_id": "evt-123", "event_type": "p03.entity.created.v1"}

        result = await breaker.emit(event)

        assert result.success is True
        assert result.method == "outbox"
        mock_outbox.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_circuit_open_low_is_dropped(
        self,
        breaker: BusDispatcherCircuitBreaker,
        mock_circuit: Mock,
        mock_outbox: Mock,
    ) -> None:
        """Test circuit open drops LOW priority events."""
        mock_circuit.should_allow_request.return_value = False
        event = {"event_id": "evt-123", "event_type": "p03.health.heartbeat.v1"}

        result = await breaker.emit(event)

        assert result.success is False
        assert result.method == "dropped"
        mock_outbox.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_open_critical_uses_outbox(
        self,
        breaker: BusDispatcherCircuitBreaker,
        mock_circuit: Mock,
        mock_outbox: Mock,
    ) -> None:
        """Test circuit open queues CRITICAL events to outbox."""
        mock_circuit.should_allow_request.return_value = False
        event = {"event_id": "evt-123", "event_type": "p03.error.fatal.v1"}

        result = await breaker.emit(event)

        assert result.success is True
        assert result.method == "outbox"
        mock_outbox.enqueue.assert_called_once()


class TestReset(TestBusDispatcherCircuitBreaker):
    """Tests for reset method."""

    def test_reset_resets_circuit(
        self, breaker: BusDispatcherCircuitBreaker, mock_circuit: Mock
    ) -> None:
        """Test reset calls circuit reset."""
        breaker.reset()

        mock_circuit.reset.assert_called_once()


class TestCreateBusCircuitBreaker:
    """Tests for create_bus_circuit_breaker factory."""

    def test_creates_breaker(self) -> None:
        """Test factory creates bus circuit breaker."""
        mock_bus = Mock()
        mock_outbox = Mock()
        breaker = create_bus_circuit_breaker(mock_bus, mock_outbox)

        assert isinstance(breaker, BusDispatcherCircuitBreaker)

    def test_uses_bus_config(self) -> None:
        """Test factory uses bus dispatcher config."""
        mock_bus = Mock()
        mock_outbox = Mock()
        breaker = create_bus_circuit_breaker(mock_bus, mock_outbox)

        # Bus config has failure_threshold=5, reset_timeout=60
        assert breaker._circuit._config.failure_threshold == 5
        assert breaker._circuit._config.reset_timeout_seconds == 60.0
