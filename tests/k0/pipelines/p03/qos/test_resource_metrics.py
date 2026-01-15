"""Tests for P03 Resource Metrics.

Issue 6.4.6: Resource utilization metrics for P03 operations.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.qos.resource_metrics import (
    MEMORY_THRESHOLDS,
    P03_RESOURCE_TARGETS,
    MemoryPressureLevel,
    P03ResourceMetrics,
    ResourceSnapshot,
    ResourceTarget,
)


class TestResourceTargets:
    """Test resource target definitions."""

    def test_all_targets_defined(self) -> None:
        """All expected targets are defined."""
        expected = ["memory_mb", "cpu_cores", "db_connections", "faiss_queries"]
        for target in expected:
            assert target in P03_RESOURCE_TARGETS

    def test_memory_target(self) -> None:
        """Memory target matches dossier."""
        target = P03_RESOURCE_TARGETS["memory_mb"]
        assert target.target_value == 512.0
        assert target.alert_threshold == 410.0  # 80%
        assert target.unit == "MB"

    def test_cpu_target(self) -> None:
        """CPU target matches dossier."""
        target = P03_RESOURCE_TARGETS["cpu_cores"]
        assert target.target_value == 2.0
        assert target.alert_threshold == 1.8  # 90%

    def test_db_connections_target(self) -> None:
        """DB connections target matches dossier."""
        target = P03_RESOURCE_TARGETS["db_connections"]
        assert target.target_value == 10.0
        assert target.alert_threshold == 8.0  # 80%

    def test_faiss_queries_target(self) -> None:
        """FAISS queries target matches dossier."""
        target = P03_RESOURCE_TARGETS["faiss_queries"]
        assert target.target_value == 100.0


class TestMemoryThresholds:
    """Test memory threshold definitions."""

    def test_thresholds_defined(self) -> None:
        """All memory thresholds defined."""
        assert "warning_mb" in MEMORY_THRESHOLDS
        assert "throttle_mb" in MEMORY_THRESHOLDS
        assert "critical_mb" in MEMORY_THRESHOLDS

    def test_thresholds_ascending(self) -> None:
        """Thresholds are in ascending order."""
        assert MEMORY_THRESHOLDS["warning_mb"] < MEMORY_THRESHOLDS["throttle_mb"]
        assert MEMORY_THRESHOLDS["throttle_mb"] < MEMORY_THRESHOLDS["critical_mb"]

    def test_threshold_values(self) -> None:
        """Threshold values match dossier."""
        assert MEMORY_THRESHOLDS["warning_mb"] == 256.0
        assert MEMORY_THRESHOLDS["throttle_mb"] == 384.0
        assert MEMORY_THRESHOLDS["critical_mb"] == 480.0


class TestP03ResourceMetrics:
    """Test resource metrics tracking."""

    @pytest.fixture
    def resource_metrics(self) -> P03ResourceMetrics:
        """Create resource metrics without exporter."""
        return P03ResourceMetrics()

    def test_init_without_exporter(self, resource_metrics: P03ResourceMetrics) -> None:
        """Initialize without metrics exporter."""
        assert resource_metrics.pipeline_id == "p03_consolidation"
        assert resource_metrics._memory_gauge is None

    def test_record_memory_usage(self, resource_metrics: P03ResourceMetrics) -> None:
        """Record memory usage."""
        resource_metrics.record_memory_usage("R3", 256.0)
        assert resource_metrics._current_memory_mb == 256.0

    def test_record_faiss_query(self, resource_metrics: P03ResourceMetrics) -> None:
        """Record FAISS query."""
        resource_metrics.record_faiss_query("search", 5)
        assert resource_metrics._faiss_query_count == 5

        resource_metrics.record_faiss_query("add", 3)
        assert resource_metrics._faiss_query_count == 8

    def test_reset_cycle_metrics(self, resource_metrics: P03ResourceMetrics) -> None:
        """Reset clears per-cycle metrics."""
        resource_metrics.record_faiss_query("search", 10)
        resource_metrics.reset_cycle_metrics()
        assert resource_metrics._faiss_query_count == 0


class TestMemoryPressure:
    """Test memory pressure calculation."""

    @pytest.fixture
    def resource_metrics(self) -> P03ResourceMetrics:
        """Create resource metrics."""
        return P03ResourceMetrics()

    def test_pressure_ok(self, resource_metrics: P03ResourceMetrics) -> None:
        """Low memory returns OK."""
        level, throttle = resource_metrics.check_memory_threshold(200.0)
        assert level == MemoryPressureLevel.OK
        assert throttle is False

    def test_pressure_warning(self, resource_metrics: P03ResourceMetrics) -> None:
        """Warning level memory."""
        level, throttle = resource_metrics.check_memory_threshold(260.0)
        assert level == MemoryPressureLevel.WARNING
        assert throttle is False

    def test_pressure_throttle(self, resource_metrics: P03ResourceMetrics) -> None:
        """Throttle level memory."""
        level, throttle = resource_metrics.check_memory_threshold(400.0)
        assert level == MemoryPressureLevel.THROTTLE
        assert throttle is True

    def test_pressure_critical(self, resource_metrics: P03ResourceMetrics) -> None:
        """Critical level memory."""
        level, throttle = resource_metrics.check_memory_threshold(490.0)
        assert level == MemoryPressureLevel.CRITICAL
        assert throttle is True


class TestResourceCompliance:
    """Test resource compliance checking."""

    @pytest.fixture
    def resource_metrics(self) -> P03ResourceMetrics:
        """Create resource metrics."""
        return P03ResourceMetrics()

    def test_memory_compliant(self, resource_metrics: P03ResourceMetrics) -> None:
        """Memory within threshold is compliant."""
        is_compliant, message = resource_metrics.check_resource_compliance("memory_mb", 300.0)
        assert is_compliant
        assert "OK" in message

    def test_memory_warning(self, resource_metrics: P03ResourceMetrics) -> None:
        """Memory near threshold returns warning."""
        is_compliant, message = resource_metrics.check_resource_compliance("memory_mb", 450.0)
        assert is_compliant
        assert "Warning" in message

    def test_memory_exceeded(self, resource_metrics: P03ResourceMetrics) -> None:
        """Memory over threshold is non-compliant."""
        is_compliant, message = resource_metrics.check_resource_compliance("memory_mb", 600.0)
        assert not is_compliant
        assert "Exceeded" in message

    def test_unknown_resource(self, resource_metrics: P03ResourceMetrics) -> None:
        """Unknown resource returns compliant."""
        is_compliant, message = resource_metrics.check_resource_compliance(
            "unknown_resource", 100.0
        )
        assert is_compliant
        assert "No target" in message


class TestResourceSnapshot:
    """Test resource snapshot."""

    @pytest.fixture
    def resource_metrics(self) -> P03ResourceMetrics:
        """Create resource metrics."""
        return P03ResourceMetrics()

    def test_get_snapshot(self, resource_metrics: P03ResourceMetrics) -> None:
        """Get resource snapshot."""
        resource_metrics.record_memory_usage("R0", 256.0)
        resource_metrics.record_faiss_query("search", 10)

        snapshot = resource_metrics.get_snapshot()

        assert isinstance(snapshot, ResourceSnapshot)
        assert snapshot.memory_mb == 256.0
        assert snapshot.faiss_queries == 10
        assert snapshot.memory_pressure == MemoryPressureLevel.WARNING

    def test_snapshot_should_throttle(self) -> None:
        """Snapshot correctly reports throttle status."""
        snapshot_ok = ResourceSnapshot(
            memory_mb=200.0,
            cpu_utilization=0.5,
            db_active=5,
            db_pool_size=10,
            faiss_queries=50,
            memory_pressure=MemoryPressureLevel.OK,
        )
        assert not snapshot_ok.should_throttle

        snapshot_critical = ResourceSnapshot(
            memory_mb=490.0,
            cpu_utilization=0.9,
            db_active=10,
            db_pool_size=10,
            faiss_queries=100,
            memory_pressure=MemoryPressureLevel.CRITICAL,
        )
        assert snapshot_critical.should_throttle


class TestWithMetricsExporter:
    """Test with mock MetricsExporter."""

    def test_init_with_exporter(self) -> None:
        """Initialize with metrics exporter."""
        mock_exporter = MagicMock()

        P03ResourceMetrics(mock_exporter)

        # Should create gauges and counter
        assert mock_exporter.gauge.call_count >= 4
        assert mock_exporter.counter.call_count >= 1

    def test_record_memory_updates_gauge(self) -> None:
        """Memory recording updates Prometheus gauge."""
        mock_exporter = MagicMock()
        mock_gauge = MagicMock()
        mock_exporter.gauge.return_value = mock_gauge

        metrics = P03ResourceMetrics(mock_exporter)
        metrics.record_memory_usage("R0", 256.0)

        mock_gauge.labels.return_value.set.assert_called()

    def test_record_faiss_updates_counter(self) -> None:
        """FAISS recording updates Prometheus counter."""
        mock_exporter = MagicMock()
        mock_counter = MagicMock()
        mock_exporter.counter.return_value = mock_counter

        metrics = P03ResourceMetrics(mock_exporter)
        metrics.record_faiss_query("search", 5)

        mock_counter.labels.return_value.inc.assert_called_with(5)


class TestGetAllTargets:
    """Test static methods."""

    def test_get_all_targets(self) -> None:
        """Get all targets returns copy."""
        targets = P03ResourceMetrics.get_all_targets()
        assert len(targets) == 4
        assert all(isinstance(t, ResourceTarget) for t in targets.values())
