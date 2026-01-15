"""
P03 Learning Compute Budget Tracker.

Tracks learning compute budget to ensure learning operations
consume less than 5% of total cycle time per dossier requirements.

Dossier Reference: Section 15.3.4 Learning Compute Budget (<5% cycle time)
K0 Reference: k0/obs/metrics.py

Issue 6.4.8: Learning compute budget tracking for P03 operations.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge, Histogram

    from k0.obs.metrics import MetricsExporter

logger = logging.getLogger(__name__)


class LearningOperation(Enum):
    """Learning operation types in P03."""

    HEBBIAN_UPDATE = "hebbian_update"
    IMPORTANCE_SCORING = "importance_scoring"
    PATTERN_EXTRACTION = "pattern_extraction"
    EPISODE_CLUSTERING = "episode_clustering"
    DREAM_EXPLORATION = "dream_exploration"
    GAP_DETECTION = "gap_detection"


@dataclass(frozen=True, slots=True)
class LearningBudgetConfig:
    """
    Learning budget configuration.

    Attributes:
        max_cycle_ratio: Maximum learning time as ratio of cycle time (default 5%)
        warning_ratio: Warning threshold ratio (default 4%)
        per_operation_limits_ms: Per-operation time limits in ms
    """

    max_cycle_ratio: float = 0.05  # 5% of cycle time
    warning_ratio: float = 0.04  # 4% warning threshold
    per_operation_limits_ms: dict[str, float] | None = None

    def __post_init__(self) -> None:
        # Default per-operation limits if not provided
        if self.per_operation_limits_ms is None:
            object.__setattr__(
                self,
                "per_operation_limits_ms",
                {
                    "hebbian_update": 50.0,  # 50ms per batch
                    "importance_scoring": 100.0,  # 100ms per batch
                    "pattern_extraction": 200.0,  # 200ms per batch
                    "episode_clustering": 300.0,  # 300ms per batch
                    "dream_exploration": 500.0,  # 500ms per batch
                    "gap_detection": 100.0,  # 100ms per batch
                },
            )


# Default budget configuration per dossier
P03_LEARNING_BUDGET_CONFIG = LearningBudgetConfig()


@dataclass(frozen=True, slots=True)
class LearningOperationStats:
    """
    Statistics for a learning operation.

    Attributes:
        operation: Operation type
        duration_ms: Execution time in ms
        within_budget: Whether operation was within budget
        budget_ratio: Ratio of time used vs limit
    """

    operation: LearningOperation
    duration_ms: float
    within_budget: bool
    budget_ratio: float


@dataclass
class LearningBudgetSummary:
    """
    Summary of learning budget usage for a cycle.

    Attributes:
        total_learning_ms: Total time spent on learning
        cycle_duration_ms: Total cycle duration
        learning_ratio: Learning time as ratio of cycle time
        within_budget: Whether total learning is within 5% budget
        operations: Per-operation statistics
    """

    total_learning_ms: float = 0.0
    cycle_duration_ms: float = 0.0
    learning_ratio: float = 0.0
    within_budget: bool = True
    operations: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.operations is None:
            self.operations = {}


class P03LearningBudget:
    """
    P03 learning compute budget tracker.

    Ensures learning operations consume less than 5% of cycle time
    per dossier requirements. Tracks per-operation budgets and
    reports to K0 MetricsExporter.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.histogram(), gauge(), counter()

    Usage:
        metrics_exporter = MetricsExporter(namespace="p03")
        budget = P03LearningBudget(metrics_exporter)

        # Start cycle tracking
        budget.start_cycle()

        # Track learning operation
        with budget.track_operation(LearningOperation.HEBBIAN_UPDATE):
            # Perform hebbian update...
            pass

        # End cycle and check budget
        summary = budget.end_cycle(total_cycle_ms=1000.0)
        print(f"Learning ratio: {summary.learning_ratio:.1%}")
    """

    def __init__(
        self,
        metrics_exporter: MetricsExporter | None = None,
        config: LearningBudgetConfig = P03_LEARNING_BUDGET_CONFIG,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize learning budget tracker.

        Args:
            metrics_exporter: K0 MetricsExporter instance (optional)
            config: Budget configuration
            pipeline_id: Pipeline identifier for labels
        """
        self._metrics = metrics_exporter
        self._config = config
        self._pipeline_id = pipeline_id

        # Per-cycle tracking
        self._cycle_start_time: float = 0.0
        self._total_learning_ms: float = 0.0
        self._operation_times: dict[str, float] = {}
        self._operation_counts: dict[str, int] = {}

        # Prometheus metrics
        self._learning_duration_histogram: Histogram | None = None
        self._learning_ratio_gauge: Gauge | None = None
        self._learning_budget_exceeded_counter: Counter | None = None
        self._operation_duration_histogram: Histogram | None = None

        if metrics_exporter is not None:
            self._init_metrics(metrics_exporter)

    def _init_metrics(self, metrics_exporter: MetricsExporter) -> None:
        """Initialize Prometheus metrics."""
        self._learning_duration_histogram = metrics_exporter.histogram(
            name="p03_learning_duration_seconds",
            description="Total learning time per cycle in seconds",
            labelnames=["pipeline_id"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )

        self._learning_ratio_gauge = metrics_exporter.gauge(
            name="p03_learning_ratio",
            description="Learning time as ratio of cycle time (target <0.05)",
            labelnames=["pipeline_id"],
        )

        self._learning_budget_exceeded_counter = metrics_exporter.counter(
            name="p03_learning_budget_exceeded_total",
            description="Number of cycles where learning exceeded 5% budget",
            labelnames=["pipeline_id"],
        )

        self._operation_duration_histogram = metrics_exporter.histogram(
            name="p03_learning_operation_seconds",
            description="Learning operation duration in seconds",
            labelnames=["operation", "pipeline_id"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
        )

    @property
    def pipeline_id(self) -> str:
        """Get pipeline identifier."""
        return self._pipeline_id

    @property
    def config(self) -> LearningBudgetConfig:
        """Get budget configuration."""
        return self._config

    def start_cycle(self) -> None:
        """Start tracking a new cycle."""
        self._cycle_start_time = time.perf_counter()
        self._total_learning_ms = 0.0
        self._operation_times.clear()
        self._operation_counts.clear()

    def record_learning_time(
        self,
        operation: LearningOperation,
        duration_ms: float,
    ) -> LearningOperationStats:
        """
        Record learning operation time.

        Args:
            operation: Learning operation type
            duration_ms: Duration in milliseconds

        Returns:
            LearningOperationStats with budget analysis
        """
        op_name = operation.value

        # Update totals
        self._total_learning_ms += duration_ms
        self._operation_times[op_name] = self._operation_times.get(op_name, 0.0) + duration_ms
        self._operation_counts[op_name] = self._operation_counts.get(op_name, 0) + 1

        # Check per-operation budget
        limit_ms = (self._config.per_operation_limits_ms or {}).get(op_name, 100.0)
        within_budget = duration_ms <= limit_ms
        budget_ratio = duration_ms / limit_ms if limit_ms > 0 else 0.0

        # Update Prometheus metrics
        if self._operation_duration_histogram is not None:
            self._operation_duration_histogram.labels(
                operation=op_name,
                pipeline_id=self._pipeline_id,
            ).observe(duration_ms / 1000.0)

        if not within_budget:
            logger.warning(
                "Learning operation exceeded budget: %s took %.1fms (limit: %.1fms)",
                op_name,
                duration_ms,
                limit_ms,
            )

        return LearningOperationStats(
            operation=operation,
            duration_ms=duration_ms,
            within_budget=within_budget,
            budget_ratio=budget_ratio,
        )

    @contextmanager
    def track_operation(
        self,
        operation: LearningOperation,
    ) -> Iterator[None]:
        """
        Context manager for tracking learning operation.

        Args:
            operation: Learning operation type

        Yields:
            None

        Example:
            with budget.track_operation(LearningOperation.HEBBIAN_UPDATE):
                # Perform operation...
                pass
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000.0
            self.record_learning_time(operation, duration_ms)

    def end_cycle(self, total_cycle_ms: float | None = None) -> LearningBudgetSummary:
        """
        End cycle tracking and compute summary.

        Args:
            total_cycle_ms: Total cycle duration in ms (auto-calculate if None)

        Returns:
            LearningBudgetSummary with budget analysis
        """
        if total_cycle_ms is None:
            # Calculate from start time
            if self._cycle_start_time > 0:
                total_cycle_ms = (time.perf_counter() - self._cycle_start_time) * 1000.0
            else:
                total_cycle_ms = 0.0

        # Calculate ratio
        learning_ratio = self._total_learning_ms / total_cycle_ms if total_cycle_ms > 0 else 0.0
        within_budget = learning_ratio <= self._config.max_cycle_ratio

        # Update Prometheus metrics
        if self._learning_duration_histogram is not None:
            self._learning_duration_histogram.labels(
                pipeline_id=self._pipeline_id,
            ).observe(self._total_learning_ms / 1000.0)

        if self._learning_ratio_gauge is not None:
            self._learning_ratio_gauge.labels(
                pipeline_id=self._pipeline_id,
            ).set(learning_ratio)

        if not within_budget and self._learning_budget_exceeded_counter is not None:
            self._learning_budget_exceeded_counter.labels(
                pipeline_id=self._pipeline_id,
            ).inc()

        if not within_budget:
            logger.warning(
                "Learning budget exceeded: %.1f%% (limit: %.1f%%)",
                learning_ratio * 100,
                self._config.max_cycle_ratio * 100,
            )

        return LearningBudgetSummary(
            total_learning_ms=self._total_learning_ms,
            cycle_duration_ms=total_cycle_ms,
            learning_ratio=learning_ratio,
            within_budget=within_budget,
            operations=dict(self._operation_times),
        )

    def check_budget_status(
        self,
        current_cycle_ms: float,
    ) -> tuple[bool, float, str]:
        """
        Check current budget status mid-cycle.

        Args:
            current_cycle_ms: Current cycle duration so far

        Returns:
            Tuple of (within_budget, remaining_budget_ms, message)
        """
        max_learning_ms = current_cycle_ms * self._config.max_cycle_ratio
        remaining_ms = max_learning_ms - self._total_learning_ms

        if remaining_ms > 0:
            return (
                True,
                remaining_ms,
                f"Budget OK: {remaining_ms:.1f}ms remaining of {max_learning_ms:.1f}ms",
            )
        else:
            return (
                False,
                remaining_ms,
                f"Budget exceeded by {-remaining_ms:.1f}ms",
            )

    def get_operation_summary(self) -> dict[str, dict[str, float]]:
        """
        Get per-operation summary.

        Returns:
            Dict of operation -> {total_ms, count, avg_ms}
        """
        summary = {}
        for op_name, total_ms in self._operation_times.items():
            count = self._operation_counts.get(op_name, 1)
            summary[op_name] = {
                "total_ms": total_ms,
                "count": float(count),
                "avg_ms": total_ms / count if count > 0 else 0.0,
            }
        return summary

    def reset(self) -> None:
        """Reset all tracking."""
        self._cycle_start_time = 0.0
        self._total_learning_ms = 0.0
        self._operation_times.clear()
        self._operation_counts.clear()
