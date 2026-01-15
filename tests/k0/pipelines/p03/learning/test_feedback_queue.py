"""Tests for P03 FeedbackQueue with overflow handling.

Issue 6.4.14 - FeedbackQueue with overflow handling

Tests queue operations, overflow sampling, and K0 metrics integration.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


class TestFeedbackQueue:
    """Test feedback queue with overflow handling."""

    @pytest.fixture
    def metrics_exporter(self) -> MagicMock:
        """Create mock metrics exporter."""
        mock = MagicMock()
        mock_counter = MagicMock()
        mock_counter.labels.return_value.inc = MagicMock()
        mock.counter.return_value = mock_counter
        mock_gauge = MagicMock()
        mock_gauge.labels.return_value.set = MagicMock()
        mock.gauge.return_value = mock_gauge
        return mock

    @pytest.fixture
    def queue(self, metrics_exporter: MagicMock):
        """Create feedback queue."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackQueue

        return FeedbackQueue(metrics_exporter, max_depth=10)

    @pytest.fixture
    def signal(self):
        """Create test signal."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackSignal

        return FeedbackSignal(
            signal_id="sig1",
            signal_type="positive",
            memory_id="mem1",
            confidence=0.9,
            timestamp=0.0,
        )

    @pytest.mark.asyncio
    async def test_enqueue_within_capacity(self, queue, signal) -> None:
        """Signals enqueued when capacity available."""
        result = await queue.enqueue(signal)

        assert result is True
        assert queue.depth() == 1

    @pytest.mark.asyncio
    async def test_enqueue_multiple(self, queue) -> None:
        """Multiple signals enqueued correctly."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackSignal

        for i in range(5):
            signal = FeedbackSignal(
                signal_id=f"sig{i}",
                signal_type="positive",
                memory_id=f"mem{i}",
                confidence=0.9,
                timestamp=0.0,
            )
            await queue.enqueue(signal)

        assert queue.depth() == 5

    @pytest.mark.asyncio
    async def test_dequeue_batch(self, queue) -> None:
        """Batch dequeue returns correct signals."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackSignal

        for i in range(5):
            signal = FeedbackSignal(
                signal_id=f"sig{i}",
                signal_type="positive",
                memory_id=f"mem{i}",
                confidence=0.9,
                timestamp=0.0,
            )
            await queue.enqueue(signal)

        batch = await queue.dequeue_batch(3)

        assert len(batch) == 3
        assert queue.depth() == 2

    @pytest.mark.asyncio
    async def test_dequeue_batch_partial(self, queue) -> None:
        """Batch dequeue returns available signals when fewer than requested."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackSignal

        for i in range(2):
            signal = FeedbackSignal(
                signal_id=f"sig{i}",
                signal_type="positive",
                memory_id=f"mem{i}",
                confidence=0.9,
                timestamp=0.0,
            )
            await queue.enqueue(signal)

        batch = await queue.dequeue_batch(5)

        assert len(batch) == 2
        assert queue.depth() == 0

    @pytest.mark.asyncio
    async def test_dequeue_batch_empty(self, queue) -> None:
        """Batch dequeue from empty queue returns empty list."""
        batch = await queue.dequeue_batch(5)

        assert len(batch) == 0

    @pytest.mark.asyncio
    async def test_overflow_discard(self, metrics_exporter: MagicMock) -> None:
        """Overflow discards when sample rate is 0."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackQueue, FeedbackSignal

        queue = FeedbackQueue(
            metrics_exporter,
            max_depth=5,
            sample_rate=0.0,  # Always discard on overflow
        )

        # Fill queue
        for i in range(5):
            signal = FeedbackSignal(
                signal_id=f"sig{i}",
                signal_type="positive",
                memory_id=f"mem{i}",
                confidence=0.9,
                timestamp=0.0,
            )
            await queue.enqueue(signal)

        # Overflow
        overflow_signal = FeedbackSignal(
            signal_id="overflow",
            signal_type="positive",
            memory_id="memX",
            confidence=0.9,
            timestamp=0.0,
        )
        result = await queue.enqueue(overflow_signal)

        assert result is False  # Discarded
        assert queue.depth() == 5  # Still at capacity

    @pytest.mark.asyncio
    async def test_overflow_sampling(self, metrics_exporter: MagicMock) -> None:
        """Overflow samples when sample rate is 1."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackQueue, FeedbackSignal

        queue = FeedbackQueue(
            metrics_exporter,
            max_depth=5,
            sample_rate=1.0,  # Always sample on overflow
        )

        # Fill queue
        for i in range(5):
            signal = FeedbackSignal(
                signal_id=f"sig{i}",
                signal_type="positive",
                memory_id=f"mem{i}",
                confidence=0.9,
                timestamp=0.0,
            )
            await queue.enqueue(signal)

        # Overflow - should replace oldest
        overflow_signal = FeedbackSignal(
            signal_id="overflow",
            signal_type="positive",
            memory_id="memX",
            confidence=0.9,
            timestamp=0.0,
        )
        result = await queue.enqueue(overflow_signal)

        assert result is True  # Replaced oldest
        assert queue.depth() == 5  # Still at capacity
        assert queue.overflow_count == 1

    @pytest.mark.asyncio
    async def test_dequeue_one(self, queue, signal) -> None:
        """Dequeue one returns single signal."""
        await queue.enqueue(signal)

        result = await queue.dequeue_one(timeout=0.1)

        assert result is not None
        assert result.signal_id == "sig1"
        assert queue.depth() == 0

    @pytest.mark.asyncio
    async def test_dequeue_one_empty(self, queue) -> None:
        """Dequeue one from empty queue returns None on timeout."""
        result = await queue.dequeue_one(timeout=0.01)

        assert result is None

    def test_is_full(self, queue, signal) -> None:
        """is_full returns True when at capacity."""
        assert queue.is_full() is False

        # Fill queue
        for i in range(10):
            asyncio.run(queue.enqueue(signal))

        assert queue.is_full() is True

    def test_is_empty(self, queue, signal) -> None:
        """is_empty returns True when empty."""
        assert queue.is_empty() is True

        asyncio.run(queue.enqueue(signal))

        assert queue.is_empty() is False

    def test_get_stats(self, queue) -> None:
        """get_stats returns correct values."""
        stats = queue.get_stats()

        assert stats["depth"] == 0
        assert stats["max_depth"] == 10
        assert stats["overflow_count"] == 0
        assert stats["sample_rate"] == 0.10
        assert stats["is_full"] is False
        assert stats["is_empty"] is True


class TestFeedbackSignal:
    """Test FeedbackSignal dataclass."""

    def test_signal_creation(self) -> None:
        """Signal created with required fields."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackSignal

        signal = FeedbackSignal(
            signal_id="sig1",
            signal_type="positive",
            memory_id="mem1",
            confidence=0.9,
            timestamp=1234567890.0,
        )

        assert signal.signal_id == "sig1"
        assert signal.signal_type == "positive"
        assert signal.memory_id == "mem1"
        assert signal.confidence == 0.9
        assert signal.timestamp == 1234567890.0

    def test_signal_with_metadata(self) -> None:
        """Signal created with optional metadata."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackSignal

        signal = FeedbackSignal(
            signal_id="sig1",
            signal_type="positive",
            memory_id="mem1",
            confidence=0.9,
            timestamp=0.0,
            metadata={"source": "user", "action": "like"},
        )

        assert signal.metadata["source"] == "user"
        assert signal.metadata["action"] == "like"


class TestQueueConstants:
    """Test queue configuration constants."""

    def test_max_depth_default(self) -> None:
        """Default max depth is 1000."""
        from k0.pipelines.p03.learning.feedback_queue import QUEUE_MAX_DEPTH

        assert QUEUE_MAX_DEPTH == 1000

    def test_sample_rate_default(self) -> None:
        """Default sample rate is 0.10."""
        from k0.pipelines.p03.learning.feedback_queue import OVERFLOW_SAMPLE_RATE

        assert OVERFLOW_SAMPLE_RATE == 0.10


class TestMetricsIntegration:
    """Test K0 metrics integration."""

    def test_metrics_registered(self) -> None:
        """Metrics registered on init."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackQueue

        mock_metrics = MagicMock()
        mock_metrics.counter.return_value = MagicMock()
        mock_metrics.gauge.return_value = MagicMock()

        FeedbackQueue(mock_metrics)

        # 1 counter and 1 gauge should be registered
        assert mock_metrics.counter.call_count == 1
        assert mock_metrics.gauge.call_count == 1

    def test_overflow_counter_name(self) -> None:
        """Overflow counter has correct name."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackQueue

        mock_metrics = MagicMock()
        mock_metrics.counter.return_value = MagicMock()
        mock_metrics.gauge.return_value = MagicMock()

        FeedbackQueue(mock_metrics)

        counter_call = mock_metrics.counter.call_args
        assert counter_call[1]["name"] == "p03_learning_queue_overflow"

    def test_depth_gauge_name(self) -> None:
        """Depth gauge has correct name."""
        from k0.pipelines.p03.learning.feedback_queue import FeedbackQueue

        mock_metrics = MagicMock()
        mock_metrics.counter.return_value = MagicMock()
        mock_metrics.gauge.return_value = MagicMock()

        FeedbackQueue(mock_metrics)

        gauge_call = mock_metrics.gauge.call_args
        assert gauge_call[1]["name"] == "p03_learning_queue_depth"
