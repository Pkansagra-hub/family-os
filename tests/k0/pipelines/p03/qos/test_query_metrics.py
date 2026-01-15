"""Tests for P03 Query Metrics.

Issue 6.4.7: Database query optimization metrics for P03 operations.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.qos.query_metrics import (
    P03_QUERY_THRESHOLDS,
    QUERY_DURATION_BUCKETS,
    P03QueryMetrics,
    QueryContext,
    QueryStats,
    QuerySummary,
    QueryThresholds,
    QueryType,
)


class TestQueryType:
    """Test query type enumeration."""

    def test_all_types_defined(self) -> None:
        """All query types defined."""
        types = list(QueryType)
        assert QueryType.SELECT in types
        assert QueryType.INSERT in types
        assert QueryType.UPDATE in types
        assert QueryType.DELETE in types
        assert QueryType.BATCH_INSERT in types
        assert QueryType.UPSERT in types

    def test_type_values(self) -> None:
        """Query types have lowercase string values."""
        assert QueryType.SELECT.value == "select"
        assert QueryType.BATCH_INSERT.value == "batch_insert"


class TestQueryThresholds:
    """Test query threshold definitions."""

    def test_default_thresholds_defined(self) -> None:
        """Default thresholds are defined."""
        thresholds = P03_QUERY_THRESHOLDS
        assert thresholds.fast_ms == 10.0
        assert thresholds.normal_ms == 50.0
        assert thresholds.slow_ms == 200.0
        assert thresholds.critical_ms == 1000.0

    def test_thresholds_ascending(self) -> None:
        """Thresholds in ascending order."""
        th = P03_QUERY_THRESHOLDS
        assert th.fast_ms < th.normal_ms < th.slow_ms < th.critical_ms

    def test_custom_thresholds(self) -> None:
        """Create custom thresholds."""
        custom = QueryThresholds(
            fast_ms=5.0,
            normal_ms=25.0,
            slow_ms=100.0,
            critical_ms=500.0,
        )
        assert custom.fast_ms == 5.0


class TestQueryDurationBuckets:
    """Test histogram bucket configuration."""

    def test_buckets_defined(self) -> None:
        """Duration buckets defined."""
        assert isinstance(QUERY_DURATION_BUCKETS, tuple)
        assert len(QUERY_DURATION_BUCKETS) > 5

    def test_buckets_ascending(self) -> None:
        """Buckets in ascending order."""
        prev = 0.0
        for bucket in QUERY_DURATION_BUCKETS:
            assert bucket > prev
            prev = bucket


class TestP03QueryMetrics:
    """Test query metrics tracking."""

    @pytest.fixture
    def query_metrics(self) -> P03QueryMetrics:
        """Create query metrics without exporter."""
        return P03QueryMetrics()

    def test_init_without_exporter(self, query_metrics: P03QueryMetrics) -> None:
        """Initialize without metrics exporter."""
        assert query_metrics.pipeline_id == "p03_consolidation"
        assert query_metrics._duration_histogram is None

    def test_record_query(self, query_metrics: P03QueryMetrics) -> None:
        """Record query duration."""
        stats = query_metrics.record_query(QueryType.SELECT, "memo_table", 15.0)

        assert isinstance(stats, QueryStats)
        assert stats.query_type == QueryType.SELECT
        assert stats.table == "memo_table"
        assert stats.duration_ms == 15.0
        assert stats.is_slow is False

    def test_record_slow_query(self, query_metrics: P03QueryMetrics) -> None:
        """Record slow query (>200ms)."""
        stats = query_metrics.record_query(QueryType.SELECT, "big_table", 250.0)

        assert stats.is_slow is True

    def test_record_multiple_queries(self, query_metrics: P03QueryMetrics) -> None:
        """Record multiple queries."""
        query_metrics.record_query(QueryType.SELECT, "memo", 10.0)
        query_metrics.record_query(QueryType.SELECT, "memo", 20.0)
        query_metrics.record_query(QueryType.INSERT, "memo", 5.0)

        summary = query_metrics.get_summary()
        assert summary.total_queries == 3
        assert summary.total_duration_ms == 35.0


class TestTimeQueryContextManager:
    """Test time_query context manager."""

    def test_time_query_basic(self) -> None:
        """Basic timing with context manager."""
        metrics = P03QueryMetrics()

        with metrics.time_query(QueryType.SELECT, "test_table") as ctx:
            time.sleep(0.01)  # ~10ms

        summary = metrics.get_summary()
        assert summary.total_queries == 1

    def test_time_query_exception(self) -> None:
        """Context manager records on exception."""
        metrics = P03QueryMetrics()

        with pytest.raises(ValueError):
            with metrics.time_query(QueryType.UPDATE, "test"):
                raise ValueError("Test error")

        # Query still recorded despite exception
        summary = metrics.get_summary()
        assert summary.total_queries == 1

    def test_time_query_rows_affected(self) -> None:
        """Context manager allows setting rows_affected."""
        metrics = P03QueryMetrics()

        with metrics.time_query(QueryType.INSERT, "test") as ctx:
            ctx.rows_affected = 100
            time.sleep(0.001)

        # rows_affected should be recorded
        assert ctx.rows_affected == 100


class TestQueryContext:
    """Test QueryContext class."""

    def test_context_defaults(self) -> None:
        """QueryContext has default values."""
        ctx = QueryContext()
        assert ctx.rows_affected == 0

    def test_context_rows_affected(self) -> None:
        """Can set rows_affected on context."""
        ctx = QueryContext()
        ctx.rows_affected = 50
        assert ctx.rows_affected == 50


class TestQuerySummary:
    """Test query summary generation."""

    @pytest.fixture
    def query_metrics(self) -> P03QueryMetrics:
        """Create populated metrics."""
        metrics = P03QueryMetrics()
        metrics.record_query(QueryType.SELECT, "t1", 15.0)
        metrics.record_query(QueryType.SELECT, "t1", 25.0)
        metrics.record_query(QueryType.INSERT, "t2", 5.0)
        metrics.record_query(QueryType.UPDATE, "t3", 300.0)  # Slow
        return metrics

    def test_get_summary(self, query_metrics: P03QueryMetrics) -> None:
        """Get query summary."""
        summary = query_metrics.get_summary()

        assert isinstance(summary, QuerySummary)
        assert summary.total_queries == 4
        assert summary.total_duration_ms == 345.0
        assert summary.slow_queries == 1

    def test_summary_queries_by_type(self, query_metrics: P03QueryMetrics) -> None:
        """Summary includes stats by type."""
        summary = query_metrics.get_summary()

        assert "select" in summary.queries_by_type
        assert summary.queries_by_type["select"] == 2
        assert "insert" in summary.queries_by_type

    def test_summary_queries_by_table(self, query_metrics: P03QueryMetrics) -> None:
        """Summary includes stats by table."""
        summary = query_metrics.get_summary()

        assert "t1" in summary.queries_by_table
        assert summary.queries_by_table["t1"] == 2

    def test_summary_avg_duration(self, query_metrics: P03QueryMetrics) -> None:
        """Average duration calculated correctly."""
        summary = query_metrics.get_summary()
        expected_avg = 345.0 / 4
        assert abs(summary.avg_duration_ms - expected_avg) < 0.01


class TestQueryHealth:
    """Test query health checking."""

    def test_healthy_queries(self) -> None:
        """All fast queries are healthy."""
        metrics = P03QueryMetrics()
        for i in range(10):
            metrics.record_query(QueryType.SELECT, f"t{i}", 5.0)

        is_healthy, message = metrics.check_query_health()
        assert is_healthy
        assert "OK" in message

    def test_slow_query_warning(self) -> None:
        """Slow queries above 10% trigger warning."""
        metrics = P03QueryMetrics()
        # 2 slow out of 10 = 20%
        for i in range(8):
            metrics.record_query(QueryType.SELECT, f"t{i}", 5.0)
        metrics.record_query(QueryType.SELECT, "slow1", 300.0)
        metrics.record_query(QueryType.SELECT, "slow2", 300.0)

        is_healthy, message = metrics.check_query_health()
        assert not is_healthy
        assert "slow" in message.lower() or "High" in message

    def test_no_queries(self) -> None:
        """No queries returns healthy."""
        metrics = P03QueryMetrics()

        is_healthy, message = metrics.check_query_health()
        assert is_healthy
        assert "No queries" in message


class TestResetMetrics:
    """Test metrics reset functionality."""

    def test_reset_clears_stats(self) -> None:
        """Reset clears all stats."""
        metrics = P03QueryMetrics()
        metrics.record_query(QueryType.SELECT, "t", 10.0)
        metrics.record_query(QueryType.INSERT, "t", 20.0)

        metrics.reset_cycle_metrics()

        summary = metrics.get_summary()
        assert summary.total_queries == 0
        assert summary.slow_queries == 0


class TestWithMetricsExporter:
    """Test with mock MetricsExporter."""

    def test_init_with_exporter(self) -> None:
        """Initialize with metrics exporter."""
        mock_exporter = MagicMock()

        P03QueryMetrics(mock_exporter)

        mock_exporter.histogram.assert_called()
        mock_exporter.counter.assert_called()

    def test_record_updates_histogram(self) -> None:
        """Recording updates Prometheus histogram."""
        mock_exporter = MagicMock()
        mock_histogram = MagicMock()
        mock_exporter.histogram.return_value = mock_histogram

        metrics = P03QueryMetrics(mock_exporter)
        metrics.record_query(QueryType.SELECT, "test", 15.0)

        mock_histogram.labels.return_value.observe.assert_called()

    def test_slow_query_increments_counter(self) -> None:
        """Slow query increments counter."""
        mock_exporter = MagicMock()
        mock_counter = MagicMock()
        mock_exporter.counter.return_value = mock_counter

        metrics = P03QueryMetrics(mock_exporter)
        metrics.record_query(QueryType.SELECT, "slow", 300.0)

        # Should increment slow query counter
        mock_counter.labels.return_value.inc.assert_called()


class TestQueryStats:
    """Test QueryStats dataclass."""

    def test_stats_structure(self) -> None:
        """QueryStats has correct fields."""
        stats = QueryStats(
            query_type=QueryType.SELECT,
            table="test_table",
            duration_ms=25.0,
            rows_affected=100,
            is_slow=False,
        )
        assert stats.query_type == QueryType.SELECT
        assert stats.table == "test_table"
        assert stats.duration_ms == 25.0
        assert stats.rows_affected == 100
        assert stats.is_slow is False

    def test_stats_slow_query(self) -> None:
        """Slow query flag."""
        stats = QueryStats(
            query_type=QueryType.SELECT,
            table="big_table",
            duration_ms=500.0,
            rows_affected=10000,
            is_slow=True,
        )
        assert stats.is_slow is True
