"""Tests for Partial Failure Handling (Issue 6.2.9).

Tests COMMIT_PARTIAL, ROLLBACK_ALL, and QUARANTINE_BATCH strategies.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from k0.pipelines.p03.ops.partial_failure import (
    ORDERING_CRITICAL_PHASES,
    QUARANTINE_THRESHOLD,
    P03BatchResult,
    P03EventResult,
    P03PartialFailureStrategy,
    PartialFailureHandler,
    PartialFailureOutcome,
    create_partial_failure_handler,
)


class TestP03PartialFailureStrategy:
    """Tests for P03PartialFailureStrategy enum."""

    def test_has_commit_partial(self) -> None:
        """Test COMMIT_PARTIAL strategy exists."""
        assert P03PartialFailureStrategy.COMMIT_PARTIAL.value == "COMMIT_PARTIAL"

    def test_has_rollback_all(self) -> None:
        """Test ROLLBACK_ALL strategy exists."""
        assert P03PartialFailureStrategy.ROLLBACK_ALL.value == "ROLLBACK_ALL"

    def test_has_quarantine_batch(self) -> None:
        """Test QUARANTINE_BATCH strategy exists."""
        assert P03PartialFailureStrategy.QUARANTINE_BATCH.value == "QUARANTINE_BATCH"


class TestP03EventResult:
    """Tests for P03EventResult dataclass."""

    def test_create_success_result(self) -> None:
        """Test creating successful event result."""
        result = P03EventResult(
            event_id="evt-123",
            success=True,
            phase="R3",
        )
        assert result.event_id == "evt-123"
        assert result.success is True
        assert result.error is None

    def test_create_failure_result(self) -> None:
        """Test creating failed event result."""
        error = RuntimeError("processing failed")
        result = P03EventResult(
            event_id="evt-456",
            success=False,
            error=error,
            phase="R4",
        )
        assert result.success is False
        assert result.error is error


class TestP03BatchResult:
    """Tests for P03BatchResult dataclass."""

    @pytest.fixture
    def batch_result(self) -> P03BatchResult:
        """Create sample batch result."""
        return P03BatchResult(
            cycle_id="cycle-001",
            phase="R3",
            tenant_id="tenant-1",
            space_id="space-1",
            total_count=10,
            results=[
                P03EventResult(event_id="e1", success=True),
                P03EventResult(event_id="e2", success=True),
                P03EventResult(event_id="e3", success=False, error=RuntimeError("fail")),
            ],
        )

    def test_success_count(self, batch_result: P03BatchResult) -> None:
        """Test success_count property."""
        assert batch_result.success_count == 2

    def test_failure_count(self, batch_result: P03BatchResult) -> None:
        """Test failure_count property."""
        assert batch_result.failure_count == 1

    def test_failure_rate(self, batch_result: P03BatchResult) -> None:
        """Test failure_rate calculation."""
        assert batch_result.failure_rate == 0.1  # 1 failure / 10 total

    def test_failure_rate_empty_batch(self) -> None:
        """Test failure_rate with empty batch."""
        result = P03BatchResult(
            cycle_id="c1",
            phase="R3",
            tenant_id="t1",
            space_id="s1",
            total_count=0,
        )
        assert result.failure_rate == 0.0

    def test_successful_events(self, batch_result: P03BatchResult) -> None:
        """Test successful_events filter."""
        successful = batch_result.successful_events
        assert len(successful) == 2
        assert all(e.success for e in successful)

    def test_failed_events(self, batch_result: P03BatchResult) -> None:
        """Test failed_events filter."""
        failed = batch_result.failed_events
        assert len(failed) == 1
        assert all(not e.success for e in failed)


class TestSelectStrategy:
    """Tests for strategy selection logic."""

    @pytest.fixture
    def handler(self) -> PartialFailureHandler:
        """Create handler with default config."""
        return PartialFailureHandler()

    def test_force_strategy_overrides(self, handler: PartialFailureHandler) -> None:
        """Test force_strategy takes precedence."""
        batch = P03BatchResult(
            cycle_id="c1",
            phase="R3",
            tenant_id="t1",
            space_id="s1",
            total_count=10,
            results=[P03EventResult(event_id="e1", success=False)],
        )
        strategy = handler.select_strategy(
            batch, force_strategy=P03PartialFailureStrategy.ROLLBACK_ALL
        )
        assert strategy == P03PartialFailureStrategy.ROLLBACK_ALL

    def test_high_failure_rate_quarantine(self, handler: PartialFailureHandler) -> None:
        """Test high failure rate triggers QUARANTINE_BATCH."""
        batch = P03BatchResult(
            cycle_id="c1",
            phase="R3",
            tenant_id="t1",
            space_id="s1",
            total_count=10,
            results=[
                P03EventResult(event_id=f"e{i}", success=False)
                for i in range(3)  # 30% failure rate > 20% threshold
            ],
        )
        strategy = handler.select_strategy(batch)
        assert strategy == P03PartialFailureStrategy.QUARANTINE_BATCH

    def test_r7_failure_rollback(self, handler: PartialFailureHandler) -> None:
        """Test R7 phase with failure triggers ROLLBACK_ALL."""
        batch = P03BatchResult(
            cycle_id="c1",
            phase="R7",
            tenant_id="t1",
            space_id="s1",
            total_count=10,
            results=[P03EventResult(event_id="e1", success=False)],
        )
        strategy = handler.select_strategy(batch)
        assert strategy == P03PartialFailureStrategy.ROLLBACK_ALL

    def test_r8_failure_rollback(self, handler: PartialFailureHandler) -> None:
        """Test R8 phase with failure triggers ROLLBACK_ALL."""
        batch = P03BatchResult(
            cycle_id="c1",
            phase="R8",
            tenant_id="t1",
            space_id="s1",
            total_count=10,
            results=[P03EventResult(event_id="e1", success=False)],
        )
        strategy = handler.select_strategy(batch)
        assert strategy == P03PartialFailureStrategy.ROLLBACK_ALL

    def test_default_commit_partial(self, handler: PartialFailureHandler) -> None:
        """Test default strategy is COMMIT_PARTIAL."""
        batch = P03BatchResult(
            cycle_id="c1",
            phase="R3",
            tenant_id="t1",
            space_id="s1",
            total_count=10,
            results=[
                P03EventResult(event_id="e1", success=True),
                P03EventResult(event_id="e2", success=False),  # 10% failure
            ],
        )
        strategy = handler.select_strategy(batch)
        assert strategy == P03PartialFailureStrategy.COMMIT_PARTIAL

    def test_no_failures_commit_partial(self, handler: PartialFailureHandler) -> None:
        """Test no failures uses COMMIT_PARTIAL."""
        batch = P03BatchResult(
            cycle_id="c1",
            phase="R3",
            tenant_id="t1",
            space_id="s1",
            total_count=10,
            results=[P03EventResult(event_id="e1", success=True)],
        )
        strategy = handler.select_strategy(batch)
        assert strategy == P03PartialFailureStrategy.COMMIT_PARTIAL


class TestHandlePartial:
    """Tests for handle_partial method."""

    @pytest.fixture
    def handler(self) -> PartialFailureHandler:
        """Create handler."""
        return PartialFailureHandler()

    @pytest.fixture
    def success_batch(self) -> P03BatchResult:
        """Create batch with all success."""
        return P03BatchResult(
            cycle_id="c1",
            phase="R3",
            tenant_id="t1",
            space_id="s1",
            total_count=3,
            results=[
                P03EventResult(event_id="e1", success=True),
                P03EventResult(event_id="e2", success=True),
                P03EventResult(event_id="e3", success=True),
            ],
        )

    @pytest.fixture
    def mixed_batch(self) -> P03BatchResult:
        """Create batch with mixed success/failure."""
        return P03BatchResult(
            cycle_id="c1",
            phase="R3",
            tenant_id="t1",
            space_id="s1",
            total_count=10,
            results=[
                P03EventResult(event_id="e1", success=True),
                P03EventResult(event_id="e2", success=False, error=RuntimeError("fail")),
            ],
        )

    @pytest.mark.asyncio
    async def test_commit_partial_returns_outcome(
        self, handler: PartialFailureHandler, mixed_batch: P03BatchResult
    ) -> None:
        """Test COMMIT_PARTIAL returns correct outcome."""
        with patch.object(handler, "_record_to_dlq", new_callable=AsyncMock):
            outcome = await handler.handle_partial(
                mixed_batch,
                strategy=P03PartialFailureStrategy.COMMIT_PARTIAL,
            )

        assert isinstance(outcome, PartialFailureOutcome)
        assert outcome.strategy == P03PartialFailureStrategy.COMMIT_PARTIAL
        assert outcome.committed_count == 1
        assert outcome.dlq_count == 1
        assert outcome.offset_advanced is True

    @pytest.mark.asyncio
    async def test_rollback_all_returns_outcome(
        self, handler: PartialFailureHandler, mixed_batch: P03BatchResult
    ) -> None:
        """Test ROLLBACK_ALL returns correct outcome."""
        outcome = await handler.handle_partial(
            mixed_batch,
            strategy=P03PartialFailureStrategy.ROLLBACK_ALL,
        )

        assert outcome.strategy == P03PartialFailureStrategy.ROLLBACK_ALL
        assert outcome.committed_count == 0
        assert outcome.dlq_count == 0
        assert outcome.offset_advanced is False

    @pytest.mark.asyncio
    async def test_quarantine_batch_returns_outcome(
        self, handler: PartialFailureHandler, mixed_batch: P03BatchResult
    ) -> None:
        """Test QUARANTINE_BATCH returns correct outcome."""
        with patch.object(handler, "_record_to_dlq", new_callable=AsyncMock):
            outcome = await handler.handle_partial(
                mixed_batch,
                strategy=P03PartialFailureStrategy.QUARANTINE_BATCH,
            )

        assert outcome.strategy == P03PartialFailureStrategy.QUARANTINE_BATCH
        assert outcome.committed_count == 0
        assert outcome.dlq_count == 2  # Both events go to DLQ
        assert outcome.offset_advanced is True


class TestConstants:
    """Tests for module constants."""

    def test_ordering_critical_phases(self) -> None:
        """Test ordering critical phases include R7 and R8."""
        assert "R7" in ORDERING_CRITICAL_PHASES
        assert "R8" in ORDERING_CRITICAL_PHASES

    def test_quarantine_threshold(self) -> None:
        """Test quarantine threshold is 20%."""
        assert QUARANTINE_THRESHOLD == 0.20


class TestCreatePartialFailureHandler:
    """Tests for create_partial_failure_handler factory."""

    def test_creates_handler(self) -> None:
        """Test factory creates handler."""
        handler = create_partial_failure_handler()
        assert isinstance(handler, PartialFailureHandler)

    def test_custom_threshold(self) -> None:
        """Test factory accepts custom threshold."""
        handler = create_partial_failure_handler(quarantine_threshold=0.30)
        assert handler._quarantine_threshold == 0.30

    def test_accepts_metrics(self) -> None:
        """Test factory accepts metrics."""
        mock_metrics = Mock()
        handler = create_partial_failure_handler(metrics=mock_metrics)
        assert handler._metrics is mock_metrics
