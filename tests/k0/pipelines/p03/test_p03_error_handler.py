"""Tests for P03 Error Handler (Issue 6.2.2).

Tests central error handler with DLQ/retry integration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from k0.outbox.scheduler import RetryDecision
from k0.pipelines.p03.ops.error_handler import P03ErrorContext, P03ErrorHandler


class TestP03ErrorContext:
    """Tests for P03ErrorContext dataclass."""

    def test_create_minimal(self) -> None:
        """Test creating context with required fields only."""
        ctx = P03ErrorContext(
            cycle_id="cycle-123",
            phase="R0",
        )
        assert ctx.cycle_id == "cycle-123"
        assert ctx.phase == "R0"
        assert ctx.attempt_count == 1
        assert ctx.event_id is None
        assert ctx.entity_id is None
        assert ctx.payload == {}

    def test_create_full(self) -> None:
        """Test creating context with all fields."""
        ctx = P03ErrorContext(
            cycle_id="cycle-123",
            phase="R6",
            attempt_count=2,
            event_id="evt-456",
            entity_id="entity-abc",
            tenant_id="tenant-1",
            space_id="space-1",
            max_attempts=5,
            payload={"key": "value"},
        )
        assert ctx.event_id == "evt-456"
        assert ctx.entity_id == "entity-abc"
        assert ctx.tenant_id == "tenant-1"
        assert ctx.space_id == "space-1"
        assert ctx.max_attempts == 5
        assert ctx.payload == {"key": "value"}

    def test_default_max_attempts(self) -> None:
        """Test default max_attempts is 3."""
        ctx = P03ErrorContext(cycle_id="cycle-123", phase="R0")
        assert ctx.max_attempts == 3


class TestP03ErrorHandler:
    """Tests for P03ErrorHandler class."""

    @pytest.fixture
    def mock_dlq(self) -> Mock:
        """Create mock DLQ."""
        mock = Mock()
        mock.record = AsyncMock(return_value=1)
        return mock

    @pytest.fixture
    def mock_metrics(self) -> Mock:
        """Create mock metrics exporter."""
        mock = Mock()
        mock.emit = Mock()
        return mock

    @pytest.fixture
    def handler(self, mock_dlq: Mock, mock_metrics: Mock) -> P03ErrorHandler:
        """Create handler with mocked dependencies."""
        return P03ErrorHandler(dlq=mock_dlq, metrics=mock_metrics)

    @pytest.fixture
    def context(self) -> P03ErrorContext:
        """Create test context."""
        return P03ErrorContext(
            cycle_id="cycle-test",
            phase="R0",
            attempt_count=1,
        )


class TestHandleTransientError(TestP03ErrorHandler):
    """Tests for handling transient errors."""

    @pytest.mark.asyncio
    async def test_transient_error_returns_retry(
        self, handler: P03ErrorHandler, context: P03ErrorContext
    ) -> None:
        """Test transient error returns retry decision."""
        error = ConnectionError("Connection refused")
        result = await handler.handle_error(error, context)

        assert result is not None
        assert isinstance(result, RetryDecision)
        assert result.action == "retry"

    @pytest.mark.asyncio
    async def test_transient_error_retries_field_matches_attempt(
        self, handler: P03ErrorHandler, context: P03ErrorContext
    ) -> None:
        """Test retry decision retries field matches attempt_count."""
        error = TimeoutError("Timed out")
        result = await handler.handle_error(error, context)

        assert result is not None
        assert result.retries == context.attempt_count

    @pytest.mark.asyncio
    async def test_transient_error_calculates_next_attempt(
        self, handler: P03ErrorHandler, context: P03ErrorContext
    ) -> None:
        """Test retry decision has next_attempt_ts."""
        error = ConnectionError("Network error")
        result = await handler.handle_error(error, context)

        assert result is not None
        assert result.next_attempt_ts is not None

    @pytest.mark.asyncio
    async def test_transient_error_emits_metric(
        self, handler: P03ErrorHandler, context: P03ErrorContext, mock_metrics: Mock
    ) -> None:
        """Test transient error emits error metric."""
        error = ConnectionError("test")
        await handler.handle_error(error, context)

        # Verify emit was called with p03_errors_total
        mock_metrics.emit.assert_called()
        calls = [str(c) for c in mock_metrics.emit.call_args_list]
        assert any("p03_errors_total" in c for c in calls)


class TestHandleValidationError(TestP03ErrorHandler):
    """Tests for handling validation errors."""

    @pytest.mark.asyncio
    async def test_validation_error_sends_to_dlq(
        self, handler: P03ErrorHandler, context: P03ErrorContext, mock_dlq: Mock
    ) -> None:
        """Test validation error sends to DLQ."""
        error = ValueError("Invalid input")
        await handler.handle_error(error, context)

        mock_dlq.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_validation_error_returns_none(
        self, handler: P03ErrorHandler, context: P03ErrorContext
    ) -> None:
        """Test validation error returns None (no retry)."""
        error = ValueError("Bad data")
        result = await handler.handle_error(error, context)

        assert result is None

    @pytest.mark.asyncio
    async def test_validation_error_emits_metric(
        self, handler: P03ErrorHandler, context: P03ErrorContext, mock_metrics: Mock
    ) -> None:
        """Test validation error emits error metric."""
        error = TypeError("Wrong type")
        await handler.handle_error(error, context)

        mock_metrics.emit.assert_called()
        calls = [str(c) for c in mock_metrics.emit.call_args_list]
        assert any("p03_errors_total" in c for c in calls)


class TestHandleLogicError(TestP03ErrorHandler):
    """Tests for handling logic errors."""

    @pytest.mark.asyncio
    async def test_logic_error_sends_to_dlq(
        self, handler: P03ErrorHandler, context: P03ErrorContext, mock_dlq: Mock
    ) -> None:
        """Test logic error sends to DLQ."""
        error = RuntimeError("Logic failure")
        await handler.handle_error(error, context)

        mock_dlq.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_logic_error_returns_none(
        self, handler: P03ErrorHandler, context: P03ErrorContext
    ) -> None:
        """Test logic error returns None (no retry)."""
        error = Exception("Unknown logic error")
        result = await handler.handle_error(error, context)

        assert result is None

    @pytest.mark.asyncio
    async def test_logic_error_emits_alert_metric(
        self, handler: P03ErrorHandler, context: P03ErrorContext, mock_metrics: Mock
    ) -> None:
        """Test logic error emits alert metric."""
        error = RuntimeError("Needs investigation")
        await handler.handle_error(error, context)

        mock_metrics.emit.assert_called()
        calls = [str(c) for c in mock_metrics.emit.call_args_list]
        assert any("p03_error_alert_total" in c for c in calls)


class TestHandleFatalError(TestP03ErrorHandler):
    """Tests for handling fatal errors."""

    @pytest.mark.asyncio
    async def test_fatal_error_sends_to_dlq(
        self, handler: P03ErrorHandler, context: P03ErrorContext, mock_dlq: Mock
    ) -> None:
        """Test fatal error sends to DLQ."""
        error = MemoryError("Out of memory")
        await handler.handle_error(error, context)

        mock_dlq.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_fatal_error_returns_none(
        self, handler: P03ErrorHandler, context: P03ErrorContext
    ) -> None:
        """Test fatal error returns None (abort)."""
        error = MemoryError("System overloaded")
        result = await handler.handle_error(error, context)

        assert result is None

    @pytest.mark.asyncio
    async def test_fatal_error_emits_fatal_metric(
        self, handler: P03ErrorHandler, context: P03ErrorContext, mock_metrics: Mock
    ) -> None:
        """Test fatal error emits fatal metric."""
        error = RecursionError("Stack overflow")
        await handler.handle_error(error, context)

        mock_metrics.emit.assert_called()
        calls = [str(c) for c in mock_metrics.emit.call_args_list]
        assert any("p03_error_fatal_total" in c for c in calls)


class TestRetryExhaustion(TestP03ErrorHandler):
    """Tests for retry exhaustion behavior."""

    @pytest.mark.asyncio
    async def test_exhausted_retries_sends_to_dlq(
        self, handler: P03ErrorHandler, mock_dlq: Mock
    ) -> None:
        """Test exhausted retries sends to DLQ."""
        context = P03ErrorContext(
            cycle_id="cycle-test",
            phase="R0",
            attempt_count=100,
            max_attempts=3,
        )
        error = ConnectionError("Still failing")
        await handler.handle_error(error, context)

        mock_dlq.record.assert_called()

    @pytest.mark.asyncio
    async def test_exhausted_retries_returns_none(self, handler: P03ErrorHandler) -> None:
        """Test exhausted retries returns None."""
        context = P03ErrorContext(
            cycle_id="cycle-test",
            phase="R0",
            attempt_count=100,
            max_attempts=3,
        )
        error = TimeoutError("Timeout")
        result = await handler.handle_error(error, context)

        assert result is None

    @pytest.mark.asyncio
    async def test_exhausted_retries_emits_exhausted_metric(
        self, handler: P03ErrorHandler, mock_metrics: Mock
    ) -> None:
        """Test exhausted retries emits exhausted metric."""
        context = P03ErrorContext(
            cycle_id="cycle-test",
            phase="R0",
            attempt_count=100,
            max_attempts=3,
        )
        error = TimeoutError("Timeout")
        await handler.handle_error(error, context)

        mock_metrics.emit.assert_called()
        calls = [str(c) for c in mock_metrics.emit.call_args_list]
        assert any("p03_retry_exhausted_total" in c for c in calls)


class TestDLQRecordContent(TestP03ErrorHandler):
    """Tests for DLQ record content."""

    @pytest.mark.asyncio
    async def test_dlq_record_created(
        self, handler: P03ErrorHandler, context: P03ErrorContext, mock_dlq: Mock
    ) -> None:
        """Test DLQ record is created for validation errors."""
        error = ValueError("Bad input")
        await handler.handle_error(error, context)

        assert mock_dlq.record.called


class TestDriverConstant:
    """Tests for DRIVER constant."""

    def test_driver_value(self) -> None:
        """Test DRIVER constant value."""
        assert P03ErrorHandler.DRIVER == "p03_consolidation"
