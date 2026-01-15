"""Tests for FAISS Index Circuit Breaker (Issue 6.2.8).

Tests FAISS circuit breaker with fallback to brute-force search.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from k0.pipelines.p03.ops.circuit_breaker import P03CircuitBreakerState
from k0.pipelines.p03.ops.faiss_circuit import (
    FAISSCircuitBreaker,
    SimilarityResult,
    create_faiss_circuit_breaker,
)


class TestSimilarityResult:
    """Tests for SimilarityResult dataclass."""

    def test_create_faiss_result(self) -> None:
        """Test creating FAISS search result."""
        result = SimilarityResult(
            entity_id="entity-123",
            similarity=0.95,
            method="faiss",
        )
        assert result.entity_id == "entity-123"
        assert result.similarity == 0.95
        assert result.method == "faiss"

    def test_create_brute_force_result(self) -> None:
        """Test creating brute-force search result."""
        result = SimilarityResult(
            entity_id="entity-456",
            similarity=0.87,
            method="brute_force",
        )
        assert result.method == "brute_force"


class TestFAISSCircuitBreaker:
    """Tests for FAISSCircuitBreaker class."""

    @pytest.fixture
    def mock_faiss_index(self) -> Mock:
        """Create mock FAISS index."""
        mock = Mock()
        mock.search = AsyncMock(
            return_value=[
                {"entity_id": "e1", "similarity": 0.95},
                {"entity_id": "e2", "similarity": 0.90},
            ]
        )
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
    def breaker(self, mock_faiss_index: Mock, mock_circuit: Mock) -> FAISSCircuitBreaker:
        """Create FAISS circuit breaker with mocks."""
        return FAISSCircuitBreaker(
            faiss_index=mock_faiss_index,
            circuit=mock_circuit,
            metrics=None,
        )


class TestFAISSProperties(TestFAISSCircuitBreaker):
    """Tests for FAISS circuit breaker properties."""

    def test_is_open_when_closed(self, breaker: FAISSCircuitBreaker, mock_circuit: Mock) -> None:
        """Test is_open returns False when circuit closed."""
        mock_circuit.state = P03CircuitBreakerState.CLOSED
        assert breaker.is_open is False

    def test_is_open_when_open(self, breaker: FAISSCircuitBreaker, mock_circuit: Mock) -> None:
        """Test is_open returns True when circuit open."""
        mock_circuit.state = P03CircuitBreakerState.OPEN
        assert breaker.is_open is True

    def test_rebuild_requested_initially_false(self, breaker: FAISSCircuitBreaker) -> None:
        """Test rebuild_requested starts as False."""
        assert breaker.rebuild_requested is False


class TestSearch(TestFAISSCircuitBreaker):
    """Tests for search method."""

    @pytest.fixture
    def query_vec(self):
        """Create test query vector."""
        import numpy as np

        return np.array([0.1, 0.2, 0.3])

    @pytest.mark.asyncio
    async def test_success_returns_results(
        self,
        breaker: FAISSCircuitBreaker,
        mock_faiss_index: Mock,
        query_vec,
    ) -> None:
        """Test successful search returns results."""
        results = await breaker.search(query_vec, top_k=10, space_id="space-1")

        assert len(results) == 2
        assert results[0].entity_id == "e1"
        assert results[0].similarity == 0.95
        assert results[0].method == "faiss"

    @pytest.mark.asyncio
    async def test_success_records_success(
        self,
        breaker: FAISSCircuitBreaker,
        mock_circuit: Mock,
        query_vec,
    ) -> None:
        """Test successful search records success."""
        await breaker.search(query_vec, top_k=10, space_id="space-1")

        mock_circuit.record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_records_failure(
        self,
        breaker: FAISSCircuitBreaker,
        mock_faiss_index: Mock,
        mock_circuit: Mock,
        query_vec,
    ) -> None:
        """Test failed search records failure."""
        mock_faiss_index.search.side_effect = RuntimeError("FAISS error")

        await breaker.search(query_vec, top_k=10, space_id="space-1")

        mock_circuit.record_failure.assert_called_once()


class TestFallbackBehavior(TestFAISSCircuitBreaker):
    """Tests for fallback to brute-force search."""

    @pytest.fixture
    def query_vec(self):
        """Create test query vector."""
        import numpy as np

        return np.array([0.1, 0.2, 0.3])

    @pytest.mark.asyncio
    async def test_circuit_open_uses_fallback(
        self,
        breaker: FAISSCircuitBreaker,
        mock_faiss_index: Mock,
        mock_circuit: Mock,
        query_vec,
    ) -> None:
        """Test circuit open skips FAISS and uses fallback."""
        mock_circuit.should_allow_request.return_value = False

        results = await breaker.search(query_vec, top_k=10, space_id="space-1")

        mock_faiss_index.search.assert_not_called()
        # No connection provided, so fallback returns empty
        assert results == []

    @pytest.mark.asyncio
    async def test_failure_triggers_rebuild_request(
        self,
        breaker: FAISSCircuitBreaker,
        mock_faiss_index: Mock,
        query_vec,
    ) -> None:
        """Test failure triggers index rebuild request."""
        mock_faiss_index.search.side_effect = RuntimeError("FAISS corrupted")

        await breaker.search(query_vec, top_k=10, space_id="space-1")

        assert breaker.rebuild_requested is True


class TestRebuildFlag(TestFAISSCircuitBreaker):
    """Tests for rebuild flag management."""

    def test_clear_rebuild_flag(self, breaker: FAISSCircuitBreaker) -> None:
        """Test clear_rebuild_flag clears the flag."""
        breaker._rebuild_requested = True

        breaker.clear_rebuild_flag()

        assert breaker.rebuild_requested is False


class TestReset(TestFAISSCircuitBreaker):
    """Tests for reset method."""

    def test_reset_clears_rebuild_flag(self, breaker: FAISSCircuitBreaker) -> None:
        """Test reset clears rebuild flag."""
        breaker._rebuild_requested = True

        breaker.reset()

        assert breaker.rebuild_requested is False

    def test_reset_resets_circuit(self, breaker: FAISSCircuitBreaker, mock_circuit: Mock) -> None:
        """Test reset calls circuit reset."""
        breaker.reset()

        mock_circuit.reset.assert_called_once()


class TestCreateFAISSCircuitBreaker:
    """Tests for create_faiss_circuit_breaker factory."""

    def test_creates_breaker(self) -> None:
        """Test factory creates FAISS circuit breaker."""
        mock_index = Mock()
        breaker = create_faiss_circuit_breaker(mock_index)

        assert isinstance(breaker, FAISSCircuitBreaker)

    def test_uses_faiss_config(self) -> None:
        """Test factory uses FAISS index config."""
        mock_index = Mock()
        breaker = create_faiss_circuit_breaker(mock_index)

        # FAISS config has failure_threshold=3, reset_timeout=30
        assert breaker._circuit._config.failure_threshold == 3
        assert breaker._circuit._config.reset_timeout_seconds == 30.0
