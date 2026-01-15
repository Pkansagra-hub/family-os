"""Tests for P08 Embedding Circuit Breaker (Issue 6.2.6).

Tests P08 embedding circuit breaker with fallback to cache.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from k0.pipelines.p03.ops.circuit_breaker import P03CircuitBreakerState
from k0.pipelines.p03.ops.p08_circuit import P08EmbeddingCircuitBreaker, create_p08_circuit_breaker


class TestP08EmbeddingCircuitBreaker:
    """Tests for P08EmbeddingCircuitBreaker class."""

    @pytest.fixture
    def mock_p08_client(self) -> Mock:
        """Create mock P08 client."""
        mock = Mock()
        mock.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
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
    def breaker(self, mock_p08_client: Mock, mock_circuit: Mock) -> P08EmbeddingCircuitBreaker:
        """Create P08 circuit breaker with mocks."""
        return P08EmbeddingCircuitBreaker(
            p08_client=mock_p08_client,
            circuit=mock_circuit,
            metrics=None,
        )


class TestP08Properties(TestP08EmbeddingCircuitBreaker):
    """Tests for P08 circuit breaker properties."""

    def test_is_open_when_closed(
        self, breaker: P08EmbeddingCircuitBreaker, mock_circuit: Mock
    ) -> None:
        """Test is_open returns False when circuit closed."""
        mock_circuit.state = P03CircuitBreakerState.CLOSED
        assert breaker.is_open is False

    def test_is_open_when_open(
        self, breaker: P08EmbeddingCircuitBreaker, mock_circuit: Mock
    ) -> None:
        """Test is_open returns True when circuit open."""
        mock_circuit.state = P03CircuitBreakerState.OPEN
        assert breaker.is_open is True

    def test_state_property(self, breaker: P08EmbeddingCircuitBreaker, mock_circuit: Mock) -> None:
        """Test state property returns circuit state."""
        mock_circuit.state = P03CircuitBreakerState.HALF_OPEN
        assert breaker.state == P03CircuitBreakerState.HALF_OPEN

    def test_pending_count_empty(self, breaker: P08EmbeddingCircuitBreaker) -> None:
        """Test pending_count starts at 0."""
        assert breaker.pending_count == 0


class TestGetEmbedding(TestP08EmbeddingCircuitBreaker):
    """Tests for get_embedding method."""

    @pytest.mark.asyncio
    async def test_success_returns_embedding(
        self,
        breaker: P08EmbeddingCircuitBreaker,
        mock_p08_client: Mock,
    ) -> None:
        """Test successful embedding retrieval."""
        result = await breaker.get_embedding("entity-123")

        assert result == [0.1, 0.2, 0.3]
        mock_p08_client.get_embedding.assert_called_once_with("entity-123")

    @pytest.mark.asyncio
    async def test_success_records_success(
        self,
        breaker: P08EmbeddingCircuitBreaker,
        mock_circuit: Mock,
    ) -> None:
        """Test successful call records success."""
        await breaker.get_embedding("entity-123")

        mock_circuit.record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_records_failure(
        self,
        breaker: P08EmbeddingCircuitBreaker,
        mock_p08_client: Mock,
        mock_circuit: Mock,
    ) -> None:
        """Test failed call records failure."""
        mock_p08_client.get_embedding.side_effect = ConnectionError("P08 down")

        await breaker.get_embedding("entity-123")

        mock_circuit.record_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_circuit_open_uses_fallback(
        self,
        breaker: P08EmbeddingCircuitBreaker,
        mock_p08_client: Mock,
        mock_circuit: Mock,
    ) -> None:
        """Test circuit open skips P08 and uses fallback."""
        mock_circuit.should_allow_request.return_value = False

        result = await breaker.get_embedding("entity-123")

        mock_p08_client.get_embedding.assert_not_called()
        assert result is None  # No connection provided, so cache returns None


class TestQueueForLater(TestP08EmbeddingCircuitBreaker):
    """Tests for pending queue functionality."""

    @pytest.mark.asyncio
    async def test_failure_without_cache_queues_entity(
        self,
        breaker: P08EmbeddingCircuitBreaker,
        mock_p08_client: Mock,
    ) -> None:
        """Test failed call without cache queues entity."""
        mock_p08_client.get_embedding.side_effect = ConnectionError("P08 down")

        await breaker.get_embedding("entity-123")

        assert breaker.pending_count == 1

    @pytest.mark.asyncio
    async def test_duplicate_entity_not_queued_twice(
        self,
        breaker: P08EmbeddingCircuitBreaker,
        mock_p08_client: Mock,
    ) -> None:
        """Test same entity not queued multiple times."""
        mock_p08_client.get_embedding.side_effect = ConnectionError("P08 down")

        await breaker.get_embedding("entity-123")
        await breaker.get_embedding("entity-123")

        assert breaker.pending_count == 1


class TestProcessPendingQueue(TestP08EmbeddingCircuitBreaker):
    """Tests for process_pending_queue method."""

    @pytest.mark.asyncio
    async def test_does_not_process_when_open(
        self,
        breaker: P08EmbeddingCircuitBreaker,
        mock_circuit: Mock,
    ) -> None:
        """Test queue not processed when circuit open."""
        mock_circuit.state = P03CircuitBreakerState.OPEN
        breaker._pending_queue.append("entity-123")

        processed = await breaker.process_pending_queue()

        assert processed == 0
        assert breaker.pending_count == 1

    @pytest.mark.asyncio
    async def test_processes_when_closed(
        self,
        breaker: P08EmbeddingCircuitBreaker,
        mock_circuit: Mock,
        mock_p08_client: Mock,
    ) -> None:
        """Test queue processed when circuit closed."""
        mock_circuit.state = P03CircuitBreakerState.CLOSED
        breaker._pending_queue.append("entity-123")
        breaker._pending_queue.append("entity-456")

        processed = await breaker.process_pending_queue()

        assert processed == 2
        assert breaker.pending_count == 0


class TestReset(TestP08EmbeddingCircuitBreaker):
    """Tests for reset method."""

    def test_reset_clears_queue(self, breaker: P08EmbeddingCircuitBreaker) -> None:
        """Test reset clears pending queue."""
        breaker._pending_queue.append("entity-123")
        breaker._pending_queue.append("entity-456")

        breaker.reset()

        assert breaker.pending_count == 0

    def test_reset_resets_circuit(
        self, breaker: P08EmbeddingCircuitBreaker, mock_circuit: Mock
    ) -> None:
        """Test reset calls circuit reset."""
        breaker.reset()

        mock_circuit.reset.assert_called_once()


class TestCreateP08CircuitBreaker:
    """Tests for create_p08_circuit_breaker factory."""

    def test_creates_breaker(self) -> None:
        """Test factory creates P08 circuit breaker."""
        mock_client = Mock()
        breaker = create_p08_circuit_breaker(mock_client)

        assert isinstance(breaker, P08EmbeddingCircuitBreaker)

    def test_uses_p08_config(self) -> None:
        """Test factory uses P08 embedding config."""
        mock_client = Mock()
        breaker = create_p08_circuit_breaker(mock_client)

        # P08 config has failure_threshold=5, reset_timeout=60
        assert breaker._circuit._config.failure_threshold == 5
        assert breaker._circuit._config.reset_timeout_seconds == 60.0
