"""
P03 Database Query Optimization Metrics.

Tracks PostgreSQL query performance including execution times,
query counts, slow queries, and optimization opportunities.

Dossier Reference: Section 15.3.3 Resource Utilization, Section 5 PostgreSQL
K0 Reference: k0/obs/metrics.py

Issue 6.4.7: Database query optimization metrics for P03 operations.
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


class QueryType(Enum):
    """Database query types for P03."""

    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    BATCH_INSERT = "batch_insert"
    UPSERT = "upsert"


@dataclass(frozen=True, slots=True)
class QueryThresholds:
    """
    Query performance thresholds.

    Attributes:
        fast_ms: Threshold for fast queries
        normal_ms: Threshold for normal queries
        slow_ms: Threshold for slow queries
        critical_ms: Threshold for critical queries
    """

    fast_ms: float = 10.0
    normal_ms: float = 50.0
    slow_ms: float = 200.0
    critical_ms: float = 1000.0


# Default thresholds per dossier
P03_QUERY_THRESHOLDS = QueryThresholds()

# Histogram buckets for query duration (in seconds)
QUERY_DURATION_BUCKETS: tuple[float, ...] = (
    0.001,  # 1ms
    0.005,  # 5ms
    0.01,  # 10ms
    0.025,  # 25ms
    0.05,  # 50ms
    0.1,  # 100ms
    0.2,  # 200ms
    0.5,  # 500ms
    1.0,  # 1s
    2.5,  # 2.5s
    5.0,  # 5s
)


@dataclass(frozen=True, slots=True)
class QueryStats:
    """
    Query execution statistics.

    Attributes:
        query_type: Type of query
        table: Target table
        duration_ms: Execution time in ms
        rows_affected: Number of rows affected
        is_slow: Whether query exceeded slow threshold
    """

    query_type: QueryType
    table: str
    duration_ms: float
    rows_affected: int
    is_slow: bool


@dataclass
class QuerySummary:
    """
    Summary of query metrics for a cycle.

    Attributes:
        total_queries: Total queries executed
        slow_queries: Number of slow queries
        avg_duration_ms: Average query duration
        total_duration_ms: Total time in queries
        queries_by_type: Breakdown by query type
        queries_by_table: Breakdown by table
    """

    total_queries: int = 0
    slow_queries: int = 0
    avg_duration_ms: float = 0.0
    total_duration_ms: float = 0.0
    queries_by_type: dict[str, int] | None = None
    queries_by_table: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.queries_by_type is None:
            self.queries_by_type = {}
        if self.queries_by_table is None:
            self.queries_by_table = {}


class P03QueryMetrics:
    """
    P03 database query optimization metrics.

    Tracks query execution times, slow queries, and provides
    optimization insights using K0 MetricsExporter.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.histogram(), counter(), gauge()

    Usage:
        metrics_exporter = MetricsExporter(namespace="p03")
        query_metrics = P03QueryMetrics(metrics_exporter)

        # Record query execution
        query_metrics.record_query(
            query_type=QueryType.SELECT,
            table="st_hipp_events",
            duration_ms=25.0,
            rows_affected=100,
        )

        # Use context manager
        with query_metrics.time_query(QueryType.INSERT, "st_epi") as ctx:
            # Execute query...
            ctx.rows_affected = 50
    """

    def __init__(
        self,
        metrics_exporter: MetricsExporter | None = None,
        thresholds: QueryThresholds = P03_QUERY_THRESHOLDS,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize query metrics.

        Args:
            metrics_exporter: K0 MetricsExporter instance (optional)
            thresholds: Query performance thresholds
            pipeline_id: Pipeline identifier for labels
        """
        self._metrics = metrics_exporter
        self._thresholds = thresholds
        self._pipeline_id = pipeline_id

        # Internal tracking for cycle summary
        self._query_count: int = 0
        self._slow_query_count: int = 0
        self._total_duration_ms: float = 0.0
        self._queries_by_type: dict[str, int] = {}
        self._queries_by_table: dict[str, int] = {}

        # Prometheus metrics
        self._duration_histogram: Histogram | None = None
        self._query_counter: Counter | None = None
        self._slow_query_counter: Counter | None = None
        self._active_queries_gauge: Gauge | None = None

        if metrics_exporter is not None:
            self._init_metrics(metrics_exporter)

    def _init_metrics(self, metrics_exporter: MetricsExporter) -> None:
        """Initialize Prometheus metrics."""
        self._duration_histogram = metrics_exporter.histogram(
            name="p03_query_duration_seconds",
            description="P03 database query duration in seconds",
            labelnames=["query_type", "table", "pipeline_id"],
            buckets=QUERY_DURATION_BUCKETS,
        )

        self._query_counter = metrics_exporter.counter(
            name="p03_queries_total",
            description="Total database queries executed",
            labelnames=["query_type", "table", "pipeline_id"],
        )

        self._slow_query_counter = metrics_exporter.counter(
            name="p03_slow_queries_total",
            description="Slow database queries (>200ms)",
            labelnames=["query_type", "table", "pipeline_id"],
        )

        self._active_queries_gauge = metrics_exporter.gauge(
            name="p03_active_queries",
            description="Currently executing queries",
            labelnames=["pipeline_id"],
        )

    @property
    def pipeline_id(self) -> str:
        """Get pipeline identifier."""
        return self._pipeline_id

    @property
    def thresholds(self) -> QueryThresholds:
        """Get query thresholds."""
        return self._thresholds

    def record_query(
        self,
        query_type: QueryType,
        table: str,
        duration_ms: float,
        rows_affected: int = 0,
    ) -> QueryStats:
        """
        Record a query execution.

        Args:
            query_type: Type of query
            table: Target table
            duration_ms: Execution time in ms
            rows_affected: Number of rows affected

        Returns:
            QueryStats with execution details
        """
        is_slow = duration_ms > self._thresholds.slow_ms

        # Update internal tracking
        self._query_count += 1
        self._total_duration_ms += duration_ms
        self._queries_by_type[query_type.value] = self._queries_by_type.get(query_type.value, 0) + 1
        self._queries_by_table[table] = self._queries_by_table.get(table, 0) + 1

        if is_slow:
            self._slow_query_count += 1
            logger.warning(
                "Slow query: type=%s, table=%s, duration_ms=%.2f",
                query_type.value,
                table,
                duration_ms,
            )

        # Update Prometheus metrics
        duration_seconds = duration_ms / 1000.0

        if self._duration_histogram is not None:
            self._duration_histogram.labels(
                query_type=query_type.value,
                table=table,
                pipeline_id=self._pipeline_id,
            ).observe(duration_seconds)

        if self._query_counter is not None:
            self._query_counter.labels(
                query_type=query_type.value,
                table=table,
                pipeline_id=self._pipeline_id,
            ).inc()

        if is_slow and self._slow_query_counter is not None:
            self._slow_query_counter.labels(
                query_type=query_type.value,
                table=table,
                pipeline_id=self._pipeline_id,
            ).inc()

        return QueryStats(
            query_type=query_type,
            table=table,
            duration_ms=duration_ms,
            rows_affected=rows_affected,
            is_slow=is_slow,
        )

    @contextmanager
    def time_query(
        self,
        query_type: QueryType,
        table: str,
    ) -> Iterator["QueryContext"]:
        """
        Context manager for timing a query.

        Args:
            query_type: Type of query
            table: Target table

        Yields:
            QueryContext for setting rows_affected

        Example:
            with query_metrics.time_query(QueryType.INSERT, "st_epi") as ctx:
                # Execute query...
                ctx.rows_affected = 50
        """
        ctx = QueryContext()

        if self._active_queries_gauge is not None:
            self._active_queries_gauge.labels(
                pipeline_id=self._pipeline_id,
            ).inc()

        start_time = time.perf_counter()
        try:
            yield ctx
        finally:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000.0

            if self._active_queries_gauge is not None:
                self._active_queries_gauge.labels(
                    pipeline_id=self._pipeline_id,
                ).dec()

            self.record_query(
                query_type=query_type,
                table=table,
                duration_ms=duration_ms,
                rows_affected=ctx.rows_affected,
            )

    def get_summary(self) -> QuerySummary:
        """
        Get query summary for current cycle.

        Returns:
            QuerySummary with aggregated metrics
        """
        avg_duration = self._total_duration_ms / self._query_count if self._query_count > 0 else 0.0

        return QuerySummary(
            total_queries=self._query_count,
            slow_queries=self._slow_query_count,
            avg_duration_ms=avg_duration,
            total_duration_ms=self._total_duration_ms,
            queries_by_type=dict(self._queries_by_type),
            queries_by_table=dict(self._queries_by_table),
        )

    def check_query_health(self) -> tuple[bool, str]:
        """
        Check overall query health for cycle.

        Returns:
            Tuple of (is_healthy, message)
        """
        if self._query_count == 0:
            return True, "No queries executed"

        slow_ratio = self._slow_query_count / self._query_count

        if slow_ratio > 0.1:  # More than 10% slow
            return (
                False,
                f"High slow query ratio: {slow_ratio:.1%} ({self._slow_query_count}/{self._query_count})",
            )
        elif slow_ratio > 0.05:  # More than 5% slow
            return True, f"Warning: Elevated slow queries: {slow_ratio:.1%}"
        else:
            return True, f"Query health OK: {slow_ratio:.1%} slow"

    def reset_cycle_metrics(self) -> None:
        """Reset per-cycle metrics."""
        self._query_count = 0
        self._slow_query_count = 0
        self._total_duration_ms = 0.0
        self._queries_by_type.clear()
        self._queries_by_table.clear()


class QueryContext:
    """Context for query timing that allows setting rows_affected."""

    def __init__(self) -> None:
        self.rows_affected: int = 0
