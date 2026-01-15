"""
P03 Adaptive Batch Sizer.

Provides K0-aware batch size optimization based on scheduler contention,
memory budget, and time budget constraints. Uses P03SchedulerIntegration
for contention factor calculation.

Dossier Reference: Section 15.4 Batch Size Optimization
K0 Reference: k0/qos/scheduler.py, k0/pipelines/p03/qos/scheduler_integration.py

Issue 6.4.3: Adaptive batch sizing for P03 operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from k0.pipelines.p03.qos.scheduler_integration import P03SchedulerIntegration

logger = logging.getLogger(__name__)


class BatchSizeCategory(IntEnum):
    """Batch size categories per dossier Section 15.4."""

    SMALL = 100
    MEDIUM = 1000
    LARGE = 10000


@dataclass(frozen=True, slots=True)
class BatchSizeProfile:
    """
    Batch size profile with resource characteristics.

    Per dossier Section 15.4, each batch size category has expected
    latency, memory, and token cost characteristics.

    Attributes:
        size: Batch size (event count)
        latency_seconds: Expected processing latency
        memory_mb: Expected memory usage
        token_cost: Scheduler token cost
        description: Human-readable description
    """

    size: int
    latency_seconds: float
    memory_mb: int
    token_cost: int
    description: str


# Batch size profiles from dossier Section 15.4
BATCH_SIZE_PROFILES: dict[BatchSizeCategory, BatchSizeProfile] = {
    BatchSizeCategory.SMALL: BatchSizeProfile(
        size=100,
        latency_seconds=5.0,
        memory_mb=50,
        token_cost=10,
        description="Small batch - fast, low memory",
    ),
    BatchSizeCategory.MEDIUM: BatchSizeProfile(
        size=1000,
        latency_seconds=30.0,
        memory_mb=200,
        token_cost=100,
        description="Medium batch - balanced",
    ),
    BatchSizeCategory.LARGE: BatchSizeProfile(
        size=10000,
        latency_seconds=300.0,
        memory_mb=1024,
        token_cost=1000,
        description="Large batch - high throughput",
    ),
}

# Default constraints for batch sizing
DEFAULT_MEMORY_BUDGET_MB: int = 512
DEFAULT_TIME_BUDGET_SECONDS: float = 60.0
DEFAULT_MIN_BATCH_SIZE: int = 100
DEFAULT_MAX_BATCH_SIZE: int = 10000


@dataclass(frozen=True, slots=True)
class BatchSizeResult:
    """
    Result of batch size optimization.

    Attributes:
        size: Recommended batch size
        reason: Explanation of the recommendation
        contention_factor: Current scheduler contention (0.5-1.0)
        memory_constrained: Whether memory budget limited the size
        time_constrained: Whether time budget limited the size
        expected_latency_seconds: Expected processing time
        expected_memory_mb: Expected memory usage
    """

    size: int
    reason: str
    contention_factor: float
    memory_constrained: bool
    time_constrained: bool
    expected_latency_seconds: float
    expected_memory_mb: int


class P03AdaptiveBatchSizer:
    """
    K0-aware adaptive batch sizer for P03 consolidation.

    Computes optimal batch size based on:
    - K0 scheduler contention (via P03SchedulerIntegration)
    - Memory budget constraints
    - Time budget constraints

    K0 References:
    - k0/qos/scheduler.py: Scheduler.active_tokens()
    - k0/pipelines/p03/qos/scheduler_integration.py: get_contention_factor()

    Usage:
        scheduler_integration = P03SchedulerIntegration(scheduler)
        batch_sizer = P03AdaptiveBatchSizer(scheduler_integration)

        result = batch_sizer.compute_optimal_batch_size(
            pending_count=5000,
            memory_budget_mb=256,
            time_budget_seconds=30.0,
        )
        print(f"Recommended batch size: {result.size}")
    """

    def __init__(
        self,
        scheduler_integration: P03SchedulerIntegration | None = None,
        min_batch_size: int = DEFAULT_MIN_BATCH_SIZE,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
    ) -> None:
        """
        Initialize adaptive batch sizer.

        Args:
            scheduler_integration: P03SchedulerIntegration for contention
            min_batch_size: Minimum allowed batch size
            max_batch_size: Maximum allowed batch size
        """
        self._scheduler_integration = scheduler_integration
        self._min_batch_size = min_batch_size
        self._max_batch_size = max_batch_size

    @property
    def min_batch_size(self) -> int:
        """Get minimum batch size."""
        return self._min_batch_size

    @property
    def max_batch_size(self) -> int:
        """Get maximum batch size."""
        return self._max_batch_size

    def compute_optimal_batch_size(
        self,
        pending_count: int,
        memory_budget_mb: int = DEFAULT_MEMORY_BUDGET_MB,
        time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
    ) -> BatchSizeResult:
        """
        Compute optimal batch size based on constraints.

        Algorithm:
        1. Get contention factor from K0 scheduler (1.0/0.75/0.5)
        2. Start with MEDIUM profile (1000 events) as baseline
        3. Apply contention factor: baseline * contention_factor
        4. Constrain by memory budget: scale down if memory exceeded
        5. Constrain by time budget: scale down if latency exceeded
        6. Clamp to [min_batch_size, max_batch_size]
        7. Don't exceed pending_count

        Args:
            pending_count: Number of pending events to process
            memory_budget_mb: Available memory budget in MB
            time_budget_seconds: Available time budget in seconds

        Returns:
            BatchSizeResult with recommended size and explanation
        """
        # Step 1: Get contention factor from scheduler
        contention_factor = self._get_contention_factor()

        # Step 2: Start with MEDIUM profile as baseline
        baseline = BATCH_SIZE_PROFILES[BatchSizeCategory.MEDIUM]
        adjusted_size = int(baseline.size * contention_factor)

        reasons: list[str] = []
        memory_constrained = False
        time_constrained = False

        # Step 3: Apply contention adjustment
        if contention_factor < 1.0:
            reasons.append(f"Contention adjusted: {contention_factor:.2f}")

        # Step 4: Memory constraint
        memory_ratio = memory_budget_mb / baseline.memory_mb
        if memory_ratio < 1.0:
            memory_adjusted_size = int(baseline.size * memory_ratio)
            if memory_adjusted_size < adjusted_size:
                adjusted_size = memory_adjusted_size
                memory_constrained = True
                reasons.append(f"Memory limited: {memory_budget_mb}MB budget")

        # Step 5: Time constraint
        time_ratio = time_budget_seconds / baseline.latency_seconds
        if time_ratio < 1.0:
            time_adjusted_size = int(baseline.size * time_ratio)
            if time_adjusted_size < adjusted_size:
                adjusted_size = time_adjusted_size
                time_constrained = True
                reasons.append(f"Time limited: {time_budget_seconds}s budget")

        # Step 6: Clamp to bounds
        adjusted_size = max(self._min_batch_size, min(self._max_batch_size, adjusted_size))

        # Step 7: Don't exceed pending count
        if adjusted_size > pending_count:
            adjusted_size = max(self._min_batch_size, pending_count)
            reasons.append(f"Capped to pending: {pending_count}")

        # Calculate expected metrics based on final size
        expected_latency, expected_memory = self._estimate_resources(adjusted_size)

        if not reasons:
            reasons.append("Default batch size")

        logger.debug(
            "Batch size computed: size=%d, contention=%.2f, memory=%dMB, time=%.1fs",
            adjusted_size,
            contention_factor,
            memory_budget_mb,
            time_budget_seconds,
        )

        return BatchSizeResult(
            size=adjusted_size,
            reason="; ".join(reasons),
            contention_factor=contention_factor,
            memory_constrained=memory_constrained,
            time_constrained=time_constrained,
            expected_latency_seconds=expected_latency,
            expected_memory_mb=expected_memory,
        )

    def get_profile_for_size(self, batch_size: int) -> BatchSizeProfile:
        """
        Get the closest profile for a given batch size.

        Args:
            batch_size: Target batch size

        Returns:
            Closest BatchSizeProfile
        """
        if batch_size <= BatchSizeCategory.SMALL:
            return BATCH_SIZE_PROFILES[BatchSizeCategory.SMALL]
        elif batch_size <= BatchSizeCategory.MEDIUM:
            return BATCH_SIZE_PROFILES[BatchSizeCategory.MEDIUM]
        else:
            return BATCH_SIZE_PROFILES[BatchSizeCategory.LARGE]

    def estimate_batch_count(
        self,
        pending_count: int,
        batch_size: int,
    ) -> int:
        """
        Estimate number of batches needed.

        Args:
            pending_count: Total pending events
            batch_size: Size of each batch

        Returns:
            Number of batches (rounded up)
        """
        if batch_size <= 0:
            return 0
        return (pending_count + batch_size - 1) // batch_size

    def _get_contention_factor(self) -> float:
        """
        Get contention factor from scheduler integration.

        Returns 1.0 if no scheduler integration available.
        """
        if self._scheduler_integration is None:
            return 1.0
        return self._scheduler_integration.get_contention_factor()

    def _estimate_resources(
        self,
        batch_size: int,
    ) -> tuple[float, int]:
        """
        Estimate latency and memory for a batch size.

        Linear interpolation between profiles.

        Args:
            batch_size: Batch size to estimate for

        Returns:
            Tuple of (latency_seconds, memory_mb)
        """
        small = BATCH_SIZE_PROFILES[BatchSizeCategory.SMALL]
        medium = BATCH_SIZE_PROFILES[BatchSizeCategory.MEDIUM]
        large = BATCH_SIZE_PROFILES[BatchSizeCategory.LARGE]

        if batch_size <= small.size:
            return small.latency_seconds, small.memory_mb
        elif batch_size <= medium.size:
            # Interpolate between small and medium
            ratio = (batch_size - small.size) / (medium.size - small.size)
            latency = small.latency_seconds + ratio * (
                medium.latency_seconds - small.latency_seconds
            )
            memory = int(small.memory_mb + ratio * (medium.memory_mb - small.memory_mb))
            return latency, memory
        elif batch_size <= large.size:
            # Interpolate between medium and large
            ratio = (batch_size - medium.size) / (large.size - medium.size)
            latency = medium.latency_seconds + ratio * (
                large.latency_seconds - medium.latency_seconds
            )
            memory = int(medium.memory_mb + ratio * (large.memory_mb - medium.memory_mb))
            return latency, memory
        else:
            return large.latency_seconds, large.memory_mb
