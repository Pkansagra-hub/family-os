"""Tests for performance regression detection and baseline management."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from k0.automation.performance_regression_detector import (
    BaselineManager,
    MetricsSnapshot,
    PerformanceBaseline,
    RegressionDetector,
    RegressionResult,
)


@pytest.fixture
def temp_baselines_dir():
    """Create temporary baselines directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_metrics() -> dict[str, MetricsSnapshot]:
    """Create sample metrics for testing."""
    return {
        "small": MetricsSnapshot(
            p50_latency_ms=10.0,
            p95_latency_ms=50.0,
            p99_latency_ms=100.0,
            throughput_rps=1000,
            error_rate=0.001,
        ),
        "balanced": MetricsSnapshot(
            p50_latency_ms=20.0,
            p95_latency_ms=100.0,
            p99_latency_ms=200.0,
            throughput_rps=500,
            error_rate=0.002,
        ),
        "large": MetricsSnapshot(
            p50_latency_ms=50.0,
            p95_latency_ms=250.0,
            p99_latency_ms=500.0,
            throughput_rps=100,
            error_rate=0.005,
        ),
    }


@pytest.fixture
def baseline(sample_metrics) -> PerformanceBaseline:
    """Create baseline for testing."""
    baseline = PerformanceBaseline(
        git_sha="abc123def456",
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        branch="main",
    )
    baseline.metrics = sample_metrics
    return baseline


class TestMetricsSnapshot:
    """Tests for MetricsSnapshot dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = MetricsSnapshot(
            p50_latency_ms=10.0,
            p95_latency_ms=50.0,
            p99_latency_ms=100.0,
            throughput_rps=1000,
            error_rate=0.001,
        )

        result = metrics.to_dict()
        assert result["p50_latency_ms"] == 10.0
        assert result["p95_latency_ms"] == 50.0
        assert result["throughput_rps"] == 1000

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "p50_latency_ms": 10.0,
            "p95_latency_ms": 50.0,
            "p99_latency_ms": 100.0,
            "throughput_rps": 1000,
            "error_rate": 0.001,
        }

        metrics = MetricsSnapshot.from_dict(data)
        assert metrics.p50_latency_ms == 10.0
        assert metrics.error_rate == 0.001

    def test_roundtrip_serialization(self):
        """Test serialization roundtrip."""
        metrics = MetricsSnapshot(
            p50_latency_ms=15.5,
            p95_latency_ms=75.5,
            p99_latency_ms=150.5,
            throughput_rps=750,
            error_rate=0.0015,
        )

        dict_repr = metrics.to_dict()
        restored = MetricsSnapshot.from_dict(dict_repr)

        assert restored.p50_latency_ms == metrics.p50_latency_ms
        assert restored.error_rate == metrics.error_rate


class TestPerformanceBaseline:
    """Tests for PerformanceBaseline management."""

    def test_to_dict(self, baseline):
        """Test baseline to dictionary conversion."""
        result = baseline.to_dict()

        assert result["git_sha"] == "abc123def456"
        assert result["branch"] == "main"
        assert "metrics" in result
        assert "small" in result["metrics"]

    def test_from_dict(self, baseline):
        """Test baseline creation from dictionary."""
        data = baseline.to_dict()
        restored = PerformanceBaseline.from_dict(data)

        assert restored.git_sha == baseline.git_sha
        assert restored.branch == baseline.branch
        assert len(restored.metrics) == len(baseline.metrics)

    def test_roundtrip_serialization(self, baseline):
        """Test baseline serialization roundtrip."""
        dict_repr = baseline.to_dict()
        restored = PerformanceBaseline.from_dict(dict_repr)

        assert restored.git_sha == baseline.git_sha
        assert restored.metrics["small"].p95_latency_ms == 50.0

    def test_checksum_deterministic(self, baseline):
        """Test that checksum is deterministic."""
        checksum1 = baseline.get_checksum()
        checksum2 = baseline.get_checksum()

        assert checksum1 == checksum2
        assert len(checksum1) == 16  # SHA256 first 16 chars

    def test_checksum_differs_with_metrics_change(self, baseline):
        """Test that checksum changes when metrics change."""
        checksum1 = baseline.get_checksum()

        # Modify metrics
        baseline.metrics["small"].p95_latency_ms = 999.0
        checksum2 = baseline.get_checksum()

        assert checksum1 != checksum2


class TestBaselineManager:
    """Tests for baseline storage and retrieval."""

    def test_save_and_load_baseline(self, baseline, temp_baselines_dir):
        """Test saving and loading baselines."""
        manager = BaselineManager(temp_baselines_dir)

        # Save
        manager.save_baseline(baseline)

        # Load
        loaded = manager.load_baseline(baseline.git_sha)

        assert loaded.git_sha == baseline.git_sha
        assert loaded.metrics["small"].p95_latency_ms == 50.0

    def test_load_nonexistent_baseline(self, temp_baselines_dir):
        """Test loading non-existent baseline raises error."""
        manager = BaselineManager(temp_baselines_dir)

        with pytest.raises(FileNotFoundError):
            manager.load_baseline("nonexistent")

    def test_list_baselines(self, baseline, temp_baselines_dir):
        """Test listing available baselines."""
        manager = BaselineManager(temp_baselines_dir)

        # Save multiple baselines
        manager.save_baseline(baseline)

        baseline2 = PerformanceBaseline(
            git_sha="xyz789abc123",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            branch="feature",
        )
        manager.save_baseline(baseline2)

        baselines = manager.list_baselines()
        assert len(baselines) == 2
        assert "abc123def456" in baselines
        assert "xyz789abc123" in baselines

    def test_baseline_file_contains_checksum(self, baseline, temp_baselines_dir):
        """Test that saved baseline includes checksum."""
        manager = BaselineManager(temp_baselines_dir)
        manager.save_baseline(baseline)

        path = temp_baselines_dir / f"{baseline.git_sha}.json"
        data = json.loads(path.read_text())

        assert "checksum" in data
        assert len(data["checksum"]) == 16


class TestRegressionDetector:
    """Tests for regression detection."""

    def test_detect_no_regressions(self, baseline):
        """Test detection when metrics are identical."""
        current = PerformanceBaseline(
            git_sha="new123",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            branch="feature",
        )
        # Copy same metrics
        current.metrics = {
            k: MetricsSnapshot(
                p50_latency_ms=v.p50_latency_ms,
                p95_latency_ms=v.p95_latency_ms,
                p99_latency_ms=v.p99_latency_ms,
                throughput_rps=v.throughput_rps,
                error_rate=v.error_rate,
            )
            for k, v in baseline.metrics.items()
        }

        detector = RegressionDetector()
        regressions = detector.detect_regressions(baseline, current, threshold=0.10)

        # All should be non-regressions (0% change)
        assert all(not r.is_regression for r in regressions)

    def test_detect_latency_regression(self, baseline):
        """Test detection of latency regressions."""
        current = PerformanceBaseline(
            git_sha="new123",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        )
        # Create metrics with 20% latency increase
        current.metrics = {
            "small": MetricsSnapshot(
                p50_latency_ms=12.0,  # +20%
                p95_latency_ms=60.0,  # +20%
                p99_latency_ms=120.0,  # +20%
                throughput_rps=1000,
                error_rate=0.001,
            ),
        }
        baseline.metrics = {"small": baseline.metrics["small"]}

        detector = RegressionDetector()
        regressions = detector.detect_regressions(baseline, current, threshold=0.10)

        # P95 should be flagged as regression
        p95_regression = next((r for r in regressions if r.metric_name == "p95_latency_ms"), None)
        assert p95_regression is not None
        assert p95_regression.is_regression
        assert abs(p95_regression.change_percent - 20.0) < 0.1

    def test_detect_throughput_regression(self, baseline):
        """Test detection of throughput regressions."""
        current = PerformanceBaseline(
            git_sha="new123",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        )
        # Create metrics with 15% throughput decrease
        current.metrics = {
            "small": MetricsSnapshot(
                p50_latency_ms=10.0,
                p95_latency_ms=50.0,
                p99_latency_ms=100.0,
                throughput_rps=850,  # -15%
                error_rate=0.001,
            ),
        }
        baseline.metrics = {"small": baseline.metrics["small"]}

        detector = RegressionDetector()
        regressions = detector.detect_regressions(baseline, current, threshold=0.10)

        # Throughput should be flagged as regression
        tp_regression = next((r for r in regressions if r.metric_name == "throughput_rps"), None)
        assert tp_regression is not None
        assert tp_regression.is_regression

    def test_regression_result_formatting(self):
        """Test RegressionResult string formatting."""
        result = RegressionResult(
            metric_name="p95_latency_ms",
            profile="small",
            baseline_value=50.0,
            current_value=60.0,
            change_percent=20.0,
            threshold_percent=10.0,
            is_regression=True,
        )

        formatted = str(result)
        assert "⚠️" in formatted or "REGRESSION" in formatted
        assert "small" in formatted
        assert "p95_latency_ms" in formatted

    def test_generate_report_structure(self, baseline):
        """Test report generation."""
        current = PerformanceBaseline(
            git_sha="new123",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        )
        # Mix of regressions and improvements
        current.metrics = {
            "small": MetricsSnapshot(
                p50_latency_ms=12.0,  # +20% - regression
                p95_latency_ms=60.0,  # +20% - regression
                p99_latency_ms=100.0,  # No change
                throughput_rps=1000,
                error_rate=0.001,
            ),
        }
        baseline.metrics = {"small": baseline.metrics["small"]}

        detector = RegressionDetector()
        regressions = detector.detect_regressions(baseline, current, threshold=0.10)
        report = detector.generate_report(baseline, current, regressions)

        # Check report structure
        assert "Performance Regression Report" in report
        assert "Baseline" in report
        assert "Current" in report
        assert "Summary" in report
        assert "Regressions" in report

    def test_report_includes_remediation_steps(self, baseline):
        """Test that report includes remediation steps for regressions."""
        current = PerformanceBaseline(
            git_sha="new123",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        )
        # Create regression
        current.metrics = {
            "small": MetricsSnapshot(
                p50_latency_ms=15.0,  # +50%
                p95_latency_ms=75.0,  # +50%
                p99_latency_ms=150.0,  # +50%
                throughput_rps=500,  # -50%
                error_rate=0.010,  # +900%
            ),
        }
        baseline.metrics = {"small": baseline.metrics["small"]}

        detector = RegressionDetector()
        regressions = detector.detect_regressions(baseline, current, threshold=0.10)
        report = detector.generate_report(baseline, current, regressions)

        assert "Remediation Steps" in report
        assert "Profile the changes" in report
        assert "Optimize code" in report


class TestMetricsValidation:
    """Tests for metrics validation."""

    def test_error_rate_as_percentage(self):
        """Test that error_rate is stored as decimal (0.001 = 0.1%)."""
        metrics = MetricsSnapshot(
            p50_latency_ms=10.0,
            p95_latency_ms=50.0,
            p99_latency_ms=100.0,
            throughput_rps=1000,
            error_rate=0.001,  # Should be 0.1% not 100%
        )

        assert 0 <= metrics.error_rate <= 1, "error_rate should be 0-1 range"


class TestBaselineIntegration:
    """Integration tests for baseline management."""

    def test_end_to_end_baseline_workflow(self, sample_metrics, temp_baselines_dir):
        """Test complete baseline save/load/compare workflow."""
        manager = BaselineManager(temp_baselines_dir)

        # Create and save baseline
        baseline1 = PerformanceBaseline(
            git_sha="v1.0.0",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            branch="main",
        )
        baseline1.metrics = sample_metrics
        manager.save_baseline(baseline1)

        # Create and save new baseline
        baseline2 = PerformanceBaseline(
            git_sha="v1.1.0",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            branch="develop",
        )
        # Add 5% regression to all latency metrics
        baseline2.metrics = {
            k: MetricsSnapshot(
                p50_latency_ms=v.p50_latency_ms * 1.05,
                p95_latency_ms=v.p95_latency_ms * 1.05,
                p99_latency_ms=v.p99_latency_ms * 1.05,
                throughput_rps=v.throughput_rps,
                error_rate=v.error_rate,
            )
            for k, v in sample_metrics.items()
        }
        manager.save_baseline(baseline2)

        # Load and compare
        loaded1 = manager.load_baseline("v1.0.0")
        loaded2 = manager.load_baseline("v1.1.0")

        detector = RegressionDetector()
        regressions = detector.detect_regressions(loaded1, loaded2, threshold=0.10)

        # No regressions (5% < 10% threshold)
        assert all(not r.is_regression for r in regressions)

        # Check that 5% changes are recorded
        p95_results = [r for r in regressions if r.metric_name == "p95_latency_ms"]
        assert len(p95_results) > 0
        for result in p95_results:
            assert 4.5 < result.change_percent < 5.5
