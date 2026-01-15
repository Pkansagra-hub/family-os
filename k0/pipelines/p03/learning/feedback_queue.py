"""
P03 feedback signal queue with overflow handling.

Manages learning feedback signals with sampling overflow protection.

Dossier Reference: Section 15.10 Queue Management
K0 Reference: k0/obs/metrics.py: MetricsExporter.counter()

Issue 6.4.14 - FeedbackQueue with overflow handling
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from prometheus_client import Counter

    from k0.obs.metrics import MetricsExporter


# Queue configuration from dossier Section 15.10
QUEUE_MAX_DEPTH: int = 1000
OVERFLOW_SAMPLE_RATE: float = 0.10  # Keep 10% on overflow


@dataclass
class FeedbackSignal:
    """Feedback signal for learning.

    Attributes:
        signal_id: Unique identifier for the signal
        signal_type: Type of feedback (positive, negative, etc.)
        memory_id: Associated memory identifier
        confidence: Confidence score (0.0-1.0)
        timestamp: Unix timestamp when signal was created
        metadata: Additional metadata
    """

    signal_id: str
    signal_type: str
    memory_id: str
    confidence: float
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


class FeedbackQueue:
    """
    Manage feedback signal queue with overflow handling.

    Uses sampling on overflow to preserve signal diversity.
    When the queue is full, new signals have a 10% chance of
    replacing an older signal, while 90% are discarded.

    Dossier Reference: Section 15.10 Queue Management
    K0 References:
    - k0/obs/metrics.py: MetricsExporter.counter() for overflow tracking

    Attributes:
        queue: Underlying asyncio.Queue
        max_depth: Maximum queue size
        sample_rate: Sampling rate on overflow (0.0-1.0)
        pipeline_id: Pipeline identifier for labels
        overflow_count: Total overflow events
    """

    def __init__(
        self,
        metrics: MetricsExporter,
        max_depth: int = QUEUE_MAX_DEPTH,
        sample_rate: float = OVERFLOW_SAMPLE_RATE,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize feedback queue.

        Args:
            metrics: K0 MetricsExporter instance
            max_depth: Maximum queue size (default 1000)
            sample_rate: Sampling rate on overflow (default 0.10)
            pipeline_id: Pipeline identifier for labels
        """
        self.queue: asyncio.Queue[FeedbackSignal] = asyncio.Queue(maxsize=max_depth)
        self.max_depth = max_depth
        self.sample_rate = sample_rate
        self.pipeline_id = pipeline_id
        self.overflow_count: int = 0

        # K0 metrics
        self._overflow_counter: Counter = metrics.counter(
            name="p03_learning_queue_overflow",
            description="Signals discarded due to queue overflow",
            labelnames=["space_id", "pipeline_id"],
        )
        self._depth_gauge = metrics.gauge(
            name="p03_learning_queue_depth",
            description="Current queue depth",
            labelnames=["pipeline_id"],
        )

    async def enqueue(
        self,
        signal: FeedbackSignal,
        space_id: str = "default",
    ) -> bool:
        """
        Add signal to queue, sample if full.

        When queue is full:
        - 10% chance: Replace oldest signal with new one
        - 90% chance: Discard new signal and record overflow

        Args:
            signal: Feedback signal to enqueue
            space_id: Space identifier for metrics

        Returns:
            True if enqueued, False if discarded
        """
        try:
            self.queue.put_nowait(signal)
            self._update_depth_gauge()
            return True
        except asyncio.QueueFull:
            # Queue full: Sample (keep 10%, discard 90%)
            if random.random() < self.sample_rate:
                # Discard oldest, add new
                try:
                    self.queue.get_nowait()
                    self.queue.put_nowait(signal)
                    self.overflow_count += 1
                    self._update_depth_gauge()
                    return True
                except Exception:
                    pass

            # Discarded
            self._overflow_counter.labels(
                space_id=space_id,
                pipeline_id=self.pipeline_id,
            ).inc()
            return False

    async def dequeue_batch(
        self,
        batch_size: int,
    ) -> list[FeedbackSignal]:
        """
        Dequeue up to batch_size signals.

        Non-blocking: returns immediately with available signals.

        Args:
            batch_size: Maximum signals to dequeue

        Returns:
            List of dequeued signals (may be fewer than batch_size)
        """
        batch: list[FeedbackSignal] = []
        for _ in range(batch_size):
            try:
                signal = self.queue.get_nowait()
                batch.append(signal)
            except asyncio.QueueEmpty:
                break
        self._update_depth_gauge()
        return batch

    async def dequeue_one(self, timeout: float | None = None) -> FeedbackSignal | None:
        """
        Dequeue a single signal with optional timeout.

        Args:
            timeout: Maximum seconds to wait (None = wait forever)

        Returns:
            Dequeued signal or None if timeout/empty
        """
        try:
            if timeout is not None:
                signal = await asyncio.wait_for(self.queue.get(), timeout=timeout)
            else:
                signal = await self.queue.get()
            self._update_depth_gauge()
            return signal
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None

    def _update_depth_gauge(self) -> None:
        """Update the depth gauge metric."""
        self._depth_gauge.labels(pipeline_id=self.pipeline_id).set(self.queue.qsize())

    def depth(self) -> int:
        """Current queue depth."""
        return self.queue.qsize()

    def is_full(self) -> bool:
        """Check if queue is full."""
        return self.queue.full()

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return self.queue.empty()

    def get_stats(self) -> dict[str, Any]:
        """
        Get queue statistics.

        Returns:
            Dictionary with depth, max_depth, overflow_count, etc.
        """
        return {
            "depth": self.depth(),
            "max_depth": self.max_depth,
            "overflow_count": self.overflow_count,
            "sample_rate": self.sample_rate,
            "is_full": self.is_full(),
            "is_empty": self.is_empty(),
        }
