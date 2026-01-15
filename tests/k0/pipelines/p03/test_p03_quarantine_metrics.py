"""
Tests for P03 Quarantine Metrics.

Issue 6.2.19: Quarantine metrics implementation
"""

from __future__ import annotations

from typing import Any, List, Optional
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.ops.quarantine_metrics import (
    QUARANTINE_ALERT_THRESHOLDS,
    QuarantineMetricsCollector,
    QuarantineMetricsJob,
    QuarantineStats,
    create_quarantine_metrics_collector,
    create_quarantine_metrics_job,
    emit_decision_metric,
    emit_quarantine_metric,
)

# ============================================================================
# Mock database connection
# ============================================================================


class MockRow:
    """Mock database row."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


class MockConnection:
    """Mock asyncpg connection for testing."""

    def __init__(self) -> None:
        self._fetchrow_results: List[Optional[MockRow]] = []
        self._fetch_results: List[List[MockRow]] = []

    def set_fetchrow_results(self, results: List[Optional[dict]]) -> None:
        """Set results for fetchrow() calls."""
        self._fetchrow_results = [MockRow(r) if r else None for r in results]

    def set_fetch_results(self, results: List[List[dict]]) -> None:
        """Set results for fetch() calls."""
        self._fetch_results = [[MockRow(r) for r in batch] for batch in results]

    async def fetchrow(self, query: str, *args: Any) -> Optional[MockRow]:
        if self._fetchrow_results:
            return self._fetchrow_results.pop(0)
        return None

    async def fetch(self, query: str, *args: Any) -> List[MockRow]:
        if self._fetch_results:
            return self._fetch_results.pop(0)
        return []


# ============================================================================
# Factory tests
# ============================================================================


class TestFactory:
    """Tests for factory functions."""

    def test_create_collector_default(self) -> None:
        """Test factory with defaults."""
        collector = create_quarantine_metrics_collector()
        assert collector is not None
        assert collector._metrics is None

    def test_create_collector_with_metrics(self) -> None:
        """Test factory with metrics exporter."""
        metrics = MagicMock()
        collector = create_quarantine_metrics_collector(metrics)
        assert collector._metrics is metrics

    def test_create_job(self) -> None:
        """Test job factory."""
        job = create_quarantine_metrics_job()
        assert job is not None
        assert job._collector is not None


# ============================================================================
# QuarantineStats tests
# ============================================================================


class TestQuarantineStats:
    """Tests for QuarantineStats dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        stats = QuarantineStats()
        assert stats.by_reason == {}
        assert stats.by_severity == {}
        assert stats.by_decision == {}
        assert stats.pending_count == 0
        assert stats.avg_review_latency_seconds == 0.0
        assert stats.auto_release_count == 0
        assert stats.total_quarantined == 0


# ============================================================================
# Alert thresholds tests
# ============================================================================


class TestAlertThresholds:
    """Tests for alert threshold constants."""

    def test_thresholds_defined(self) -> None:
        """Test all thresholds are defined."""
        assert "high_rate_warning" in QUARANTINE_ALERT_THRESHOLDS
        assert "high_severity_spike" in QUARANTINE_ALERT_THRESHOLDS
        assert "pending_high_reviews" in QUARANTINE_ALERT_THRESHOLDS

    def test_threshold_values(self) -> None:
        """Test threshold values match dossier."""
        assert QUARANTINE_ALERT_THRESHOLDS["high_rate_warning"] == 10
        assert QUARANTINE_ALERT_THRESHOLDS["high_severity_spike"] == 1
        assert QUARANTINE_ALERT_THRESHOLDS["pending_high_reviews"] == 10


# ============================================================================
# record_quarantine tests
# ============================================================================


class TestRecordQuarantine:
    """Tests for record_quarantine method."""

    def test_no_metrics_no_error(self) -> None:
        """Test no error when metrics is None."""
        collector = QuarantineMetricsCollector(metrics=None)
        # Should not raise
        collector.record_quarantine("RATE_LIMIT", "HIGH")

    def test_emits_signals_total(self) -> None:
        """Test quarantine emits signals total."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_quarantine("RATE_LIMIT", "MEDIUM")

        metrics.counter.assert_called()
        calls = [str(c) for c in metrics.counter.call_args_list]
        assert any("p03_quarantine_signals_total" in c for c in calls)

    def test_high_severity_emits_extra(self) -> None:
        """Test high severity emits additional metric."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_quarantine("ANOMALY", "HIGH")

        # Should have 2 counter calls
        assert metrics.counter.call_count == 2


# ============================================================================
# record_decision tests
# ============================================================================


class TestRecordDecision:
    """Tests for record_decision method."""

    def test_release_decision(self) -> None:
        """Test release decision emits metric."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_decision("RELEASE")

        metrics.counter.assert_called()

    def test_auto_release_extra(self) -> None:
        """Test auto-release emits additional metric."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_decision("AUTO_RELEASE")

        # decisions_total + auto_released_total
        assert metrics.counter.call_count == 2

    def test_with_latency(self) -> None:
        """Test decision with latency emits histogram."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_decision("RELEASE", review_latency_seconds=300.0)

        metrics.histogram.assert_called()


# ============================================================================
# record_rate_limit_check tests
# ============================================================================


class TestRecordRateLimitCheck:
    """Tests for record_rate_limit_check method."""

    def test_not_exceeded(self) -> None:
        """Test check when not exceeded."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_rate_limit_check(False)

        metrics.counter.assert_called_once()

    def test_exceeded_with_user(self) -> None:
        """Test check when exceeded with user ID."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_rate_limit_check(True, user_id="user123")

        # rate_limit_checks + rate_limit_exceeded
        assert metrics.counter.call_count == 2


# ============================================================================
# record_velocity_check tests
# ============================================================================


class TestRecordVelocityCheck:
    """Tests for record_velocity_check method."""

    def test_no_spike(self) -> None:
        """Test velocity check with no spike."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_velocity_check(False)

        metrics.counter.assert_called_once()

    def test_spike_with_details(self) -> None:
        """Test velocity check with spike and details."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_velocity_check(
            True,
            space_id="space123",
            spike_multiplier=15.0,
        )

        # velocity_checks + velocity_spikes
        assert metrics.counter.call_count == 2
        metrics.gauge.assert_called_once()


# ============================================================================
# record_anomaly_check tests
# ============================================================================


class TestRecordAnomalyCheck:
    """Tests for record_anomaly_check method."""

    def test_not_anomalous(self) -> None:
        """Test anomaly check with no anomaly."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_anomaly_check(False)

        metrics.counter.assert_called_once()

    def test_anomalous_with_type(self) -> None:
        """Test anomaly check with type."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        collector.record_anomaly_check(True, anomaly_type="LOW_ENTROPY")

        # anomaly_checks + anomalies_detected
        assert metrics.counter.call_count == 2


# ============================================================================
# update_pending_gauge tests
# ============================================================================


class TestUpdatePendingGauge:
    """Tests for update_pending_gauge method."""

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        """Test with no pending reviews."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)
        conn = MockConnection()
        conn.set_fetch_results([[]])

        counts = await collector.update_pending_gauge(connection=conn)

        assert counts == {"LOW": 0, "MEDIUM": 0, "HIGH": 0}

    @pytest.mark.asyncio
    async def test_with_pending(self) -> None:
        """Test with pending reviews."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)
        conn = MockConnection()
        conn.set_fetch_results(
            [
                [
                    {"severity": "LOW", "count": 5},
                    {"severity": "MEDIUM", "count": 3},
                    {"severity": "HIGH", "count": 2},
                ]
            ]
        )

        counts = await collector.update_pending_gauge(connection=conn)

        assert counts["LOW"] == 5
        assert counts["MEDIUM"] == 3
        assert counts["HIGH"] == 2
        # 3 gauge calls (one per severity)
        assert metrics.gauge.call_count == 3


# ============================================================================
# get_quarantine_stats tests
# ============================================================================


class TestGetQuarantineStats:
    """Tests for get_quarantine_stats method."""

    @pytest.mark.asyncio
    async def test_empty_stats(self) -> None:
        """Test with no quarantine data."""
        collector = QuarantineMetricsCollector(metrics=None)
        conn = MockConnection()
        conn.set_fetchrow_results(
            [
                {"total": 0},  # total
                {"avg_latency_seconds": None},  # latency
                {"count": 0},  # auto release
            ]
        )
        conn.set_fetch_results(
            [
                [],  # by reason
                [],  # by severity
                [],  # by decision
                [],  # pending gauge
            ]
        )

        stats = await collector.get_quarantine_stats(connection=conn)

        assert stats.total_quarantined == 0
        assert stats.by_reason == {}
        assert stats.avg_review_latency_seconds == 0.0

    @pytest.mark.asyncio
    async def test_with_data(self) -> None:
        """Test with quarantine data."""
        collector = QuarantineMetricsCollector(metrics=None)
        conn = MockConnection()
        conn.set_fetchrow_results(
            [
                {"total": 100},  # total
                {"avg_latency_seconds": 300.5},  # latency
                {"count": 20},  # auto release
            ]
        )
        conn.set_fetch_results(
            [
                [  # by reason
                    {"reason": "RATE_LIMIT", "count": 60},
                    {"reason": "VELOCITY_SPIKE", "count": 40},
                ],
                [  # by severity
                    {"severity": "LOW", "count": 30},
                    {"severity": "MEDIUM", "count": 50},
                    {"severity": "HIGH", "count": 20},
                ],
                [  # by decision
                    {"decision": "RELEASE", "count": 50},
                    {"decision": "DISCARD", "count": 30},
                ],
                [],  # pending gauge
            ]
        )

        stats = await collector.get_quarantine_stats(connection=conn)

        assert stats.total_quarantined == 100
        assert stats.by_reason["RATE_LIMIT"] == 60
        assert stats.by_severity["HIGH"] == 20
        assert stats.avg_review_latency_seconds == 300.5
        assert stats.auto_release_count == 20


# ============================================================================
# get_rate_limit_stats tests
# ============================================================================


class TestGetRateLimitStats:
    """Tests for get_rate_limit_stats method."""

    @pytest.mark.asyncio
    async def test_get_stats(self) -> None:
        """Test rate limit stats retrieval."""
        collector = QuarantineMetricsCollector(metrics=None)
        conn = MockConnection()
        conn.set_fetch_results(
            [
                [  # top users
                    {"user_id": "user1", "signal_count": 100},
                    {"user_id": "user2", "signal_count": 50},
                ]
            ]
        )
        conn.set_fetchrow_results(
            [
                {"count": 5},  # rate limited
            ]
        )

        stats = await collector.get_rate_limit_stats("space1", connection=conn, window_minutes=60)

        assert stats["space_id"] == "space1"
        assert stats["window_minutes"] == 60
        assert len(stats["top_users"]) == 2
        assert stats["rate_limited_count"] == 5


# ============================================================================
# QuarantineMetricsJob tests
# ============================================================================


class TestQuarantineMetricsJob:
    """Tests for QuarantineMetricsJob class."""

    def test_job_name(self) -> None:
        """Test job name constant."""
        assert QuarantineMetricsJob.JOB_NAME == "p03_quarantine_metrics"

    def test_default_interval(self) -> None:
        """Test default interval."""
        assert QuarantineMetricsJob.DEFAULT_INTERVAL_SECONDS == 60

    @pytest.mark.asyncio
    async def test_run(self) -> None:
        """Test job execution."""
        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)
        job = QuarantineMetricsJob(collector)
        conn = MockConnection()
        conn.set_fetch_results([[{"severity": "HIGH", "count": 5}]])

        result = await job.run(connection=conn)

        assert result["HIGH"] == 5


# ============================================================================
# Convenience function tests
# ============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_emit_quarantine_metric(self) -> None:
        """Test emit_quarantine_metric function."""
        metrics = MagicMock()
        emit_quarantine_metric(metrics, "ANOMALY", "HIGH")
        metrics.counter.assert_called()

    def test_emit_decision_metric(self) -> None:
        """Test emit_decision_metric function."""
        metrics = MagicMock()
        emit_decision_metric(metrics, "RELEASE", review_latency_seconds=100.0)
        metrics.counter.assert_called()
        metrics.histogram.assert_called()
