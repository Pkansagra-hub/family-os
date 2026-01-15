"""Tests for P03 Phase Metrics.

Issue 6.4.4: Phase latency targets implementation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from k0.pipelines.p03.qos.phase_metrics import (
    LATENCY_BUCKETS_SECONDS,
    PHASE_LATENCY_TARGETS,
    LatencyTarget,
    P03PhaseMetrics,
    SLOCheckResult,
    SLOComplianceLevel,
)


class TestLatencyTargets:
    """Test latency target definitions."""

    def test_all_phases_defined(self) -> None:
        """All phases have targets."""
        expected_phases = ["R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "FULL_CYCLE"]
        for phase in expected_phases:
            assert phase in PHASE_LATENCY_TARGETS

    def test_r0_targets(self) -> None:
        """R0 targets match dossier."""
        target = PHASE_LATENCY_TARGETS["R0"]
        assert target.p50_ms == 10
        assert target.p95_ms == 50
        assert target.p99_ms == 100
        assert target.description == "Batch Select"

    def test_r1_targets(self) -> None:
        """R1 targets match dossier."""
        target = PHASE_LATENCY_TARGETS["R1"]
        assert target.p50_ms == 20
        assert target.p95_ms == 100
        assert target.p99_ms == 200

    def test_r2_targets(self) -> None:
        """R2 targets match dossier."""
        target = PHASE_LATENCY_TARGETS["R2"]
        assert target.p50_ms == 50
        assert target.p95_ms == 200
        assert target.p99_ms == 500

    def test_r3_targets(self) -> None:
        """R3 targets match dossier."""
        target = PHASE_LATENCY_TARGETS["R3"]
        assert target.p50_ms == 30
        assert target.p95_ms == 150
        assert target.p99_ms == 300

    def test_r4_targets(self) -> None:
        """R4 targets match dossier."""
        target = PHASE_LATENCY_TARGETS["R4"]
        assert target.p50_ms == 100
        assert target.p95_ms == 300
        assert target.p99_ms == 600

    def test_r5_targets(self) -> None:
        """R5 targets match dossier."""
        target = PHASE_LATENCY_TARGETS["R5"]
        assert target.p50_ms == 200
        assert target.p95_ms == 500
        assert target.p99_ms == 1000

    def test_r6_targets(self) -> None:
        """R6 targets match dossier."""
        target = PHASE_LATENCY_TARGETS["R6"]
        assert target.p50_ms == 10
        assert target.p95_ms == 30
        assert target.p99_ms == 50

    def test_r7_targets(self) -> None:
        """R7 targets match dossier."""
        target = PHASE_LATENCY_TARGETS["R7"]
        assert target.p50_ms == 50
        assert target.p95_ms == 150
        assert target.p99_ms == 300

    def test_r8_targets(self) -> None:
        """R8 targets match dossier."""
        target = PHASE_LATENCY_TARGETS["R8"]
        assert target.p50_ms == 5
        assert target.p95_ms == 20
        assert target.p99_ms == 50

    def test_full_cycle_targets(self) -> None:
        """Full cycle targets match dossier."""
        target = PHASE_LATENCY_TARGETS["FULL_CYCLE"]
        assert target.p50_ms == 500
        assert target.p95_ms == 1500
        assert target.p99_ms == 3000


class TestLatencyBuckets:
    """Test histogram bucket configuration."""

    def test_buckets_ascending(self) -> None:
        """Buckets are in ascending order."""
        for i in range(len(LATENCY_BUCKETS_SECONDS) - 1):
            assert LATENCY_BUCKETS_SECONDS[i] < LATENCY_BUCKETS_SECONDS[i + 1]

    def test_buckets_cover_targets(self) -> None:
        """Buckets cover all target values."""
        min_bucket = LATENCY_BUCKETS_SECONDS[0]
        max_bucket = LATENCY_BUCKETS_SECONDS[-1]

        # Smallest target is R8 P50 = 5ms = 0.005s
        assert min_bucket <= 0.005

        # Largest target is FULL_CYCLE P99 = 3000ms = 3.0s
        assert max_bucket >= 3.0


class TestP03PhaseMetrics:
    """Test phase metrics without Prometheus."""

    @pytest.fixture
    def phase_metrics(self) -> P03PhaseMetrics:
        """Create phase metrics without exporter."""
        return P03PhaseMetrics()

    def test_init_without_exporter(self, phase_metrics: P03PhaseMetrics) -> None:
        """Initialize without metrics exporter."""
        assert phase_metrics.pipeline_id == "p03_consolidation"
        assert phase_metrics._phase_duration is None
        assert phase_metrics._cycle_duration is None

    def test_record_phase_no_exporter(self, phase_metrics: P03PhaseMetrics) -> None:
        """Record phase duration without exporter (no error)."""
        phase_metrics.record_phase_duration("R0", 25.0)  # Should not raise

    def test_get_target_exists(self, phase_metrics: P03PhaseMetrics) -> None:
        """Get target for existing phase."""
        target = phase_metrics.get_target("R0")
        assert target is not None
        assert target.phase == "R0"

    def test_get_target_not_exists(self, phase_metrics: P03PhaseMetrics) -> None:
        """Get target for non-existing phase."""
        target = phase_metrics.get_target("UNKNOWN")  # type: ignore[arg-type]
        assert target is None

    def test_get_all_phases(self) -> None:
        """Get all defined phases."""
        phases = P03PhaseMetrics.get_all_phases()
        assert len(phases) == 10
        assert "R0" in phases
        assert "FULL_CYCLE" in phases

    def test_get_all_targets(self) -> None:
        """Get all targets."""
        targets = P03PhaseMetrics.get_all_targets()
        assert len(targets) == 10
        assert all(isinstance(t, LatencyTarget) for t in targets.values())


class TestSLOCompliance:
    """Test SLO compliance checking."""

    @pytest.fixture
    def phase_metrics(self) -> P03PhaseMetrics:
        """Create phase metrics."""
        return P03PhaseMetrics()

    def test_check_excellent(self, phase_metrics: P03PhaseMetrics) -> None:
        """Duration under P50 is excellent."""
        result = phase_metrics.check_slo_compliance("R0", 5.0)
        assert result.level == SLOComplianceLevel.EXCELLENT
        assert result.is_compliant
        assert "Excellent" in result.message

    def test_check_good(self, phase_metrics: P03PhaseMetrics) -> None:
        """Duration under P95 is good."""
        result = phase_metrics.check_slo_compliance("R0", 30.0)
        assert result.level == SLOComplianceLevel.GOOD
        assert result.is_compliant
        assert "Good" in result.message

    def test_check_warning(self, phase_metrics: P03PhaseMetrics) -> None:
        """Duration under P99 is warning."""
        result = phase_metrics.check_slo_compliance("R0", 80.0)
        assert result.level == SLOComplianceLevel.WARNING
        assert result.is_compliant  # Still compliant (within P99)
        assert "Warning" in result.message

    def test_check_breach(self, phase_metrics: P03PhaseMetrics) -> None:
        """Duration over P99 is breach."""
        result = phase_metrics.check_slo_compliance("R0", 150.0)
        assert result.level == SLOComplianceLevel.BREACH
        assert not result.is_compliant
        assert "breach" in result.message.lower()

    def test_check_at_p50_boundary(self, phase_metrics: P03PhaseMetrics) -> None:
        """Duration exactly at P50 is excellent."""
        result = phase_metrics.check_slo_compliance("R0", 10.0)
        assert result.level == SLOComplianceLevel.EXCELLENT

    def test_check_at_p95_boundary(self, phase_metrics: P03PhaseMetrics) -> None:
        """Duration exactly at P95 is good."""
        result = phase_metrics.check_slo_compliance("R0", 50.0)
        assert result.level == SLOComplianceLevel.GOOD

    def test_check_at_p99_boundary(self, phase_metrics: P03PhaseMetrics) -> None:
        """Duration exactly at P99 is warning."""
        result = phase_metrics.check_slo_compliance("R0", 100.0)
        assert result.level == SLOComplianceLevel.WARNING

    def test_check_unknown_phase(self, phase_metrics: P03PhaseMetrics) -> None:
        """Unknown phase returns excellent (no target)."""
        result = phase_metrics.check_slo_compliance("UNKNOWN", 100.0)  # type: ignore[arg-type]
        assert result.level == SLOComplianceLevel.EXCELLENT
        assert "No target defined" in result.message

    def test_result_includes_target(self, phase_metrics: P03PhaseMetrics) -> None:
        """Result includes target information."""
        result = phase_metrics.check_slo_compliance("R1", 50.0)
        assert result.target.phase == "R1"
        assert result.target.p50_ms == 20
        assert result.duration_ms == 50.0
        assert result.phase == "R1"


class TestRecordAndCheck:
    """Test combined record and check."""

    @pytest.fixture
    def phase_metrics(self) -> P03PhaseMetrics:
        """Create phase metrics."""
        return P03PhaseMetrics()

    def test_record_and_check(self, phase_metrics: P03PhaseMetrics) -> None:
        """Record and check in one call."""
        result = phase_metrics.record_and_check("R0", 25.0)
        assert isinstance(result, SLOCheckResult)
        assert result.is_compliant


class TestTimePhaseContextManager:
    """Test timing context manager."""

    @pytest.fixture
    def phase_metrics(self) -> P03PhaseMetrics:
        """Create phase metrics."""
        return P03PhaseMetrics()

    def test_time_phase_records_duration(self, phase_metrics: P03PhaseMetrics) -> None:
        """Context manager records duration."""
        with patch.object(phase_metrics, "record_phase_duration") as mock_record:
            with phase_metrics.time_phase("R0"):
                pass  # Quick operation

            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert args[0] == "R0"
            assert isinstance(args[1], float)
            assert args[1] >= 0

    def test_time_phase_records_on_exception(self, phase_metrics: P03PhaseMetrics) -> None:
        """Duration recorded even on exception."""
        with patch.object(phase_metrics, "record_phase_duration") as mock_record:
            with pytest.raises(ValueError):
                with phase_metrics.time_phase("R0"):
                    raise ValueError("test error")

            mock_record.assert_called_once()


class TestWithMetricsExporter:
    """Test with mock MetricsExporter."""

    def test_init_with_exporter(self) -> None:
        """Initialize with metrics exporter."""
        mock_exporter = MagicMock()
        mock_histogram = MagicMock()
        mock_exporter.histogram.return_value = mock_histogram

        metrics = P03PhaseMetrics(mock_exporter)

        assert mock_exporter.histogram.call_count == 2  # phase + cycle

    def test_record_phase_with_exporter(self) -> None:
        """Record phase duration with exporter."""
        mock_exporter = MagicMock()
        mock_histogram = MagicMock()
        mock_exporter.histogram.return_value = mock_histogram

        metrics = P03PhaseMetrics(mock_exporter)
        metrics.record_phase_duration("R0", 25.0)

        mock_histogram.labels.return_value.observe.assert_called()

    def test_record_full_cycle_with_exporter(self) -> None:
        """Record full cycle duration with exporter."""
        mock_exporter = MagicMock()
        mock_histogram = MagicMock()
        mock_exporter.histogram.return_value = mock_histogram

        phase_metrics = P03PhaseMetrics(mock_exporter)
        phase_metrics.record_phase_duration("FULL_CYCLE", 1000.0)

        mock_histogram.labels.return_value.observe.assert_called()


class TestSLOCheckResult:
    """Test SLOCheckResult dataclass."""

    def test_result_immutable(self) -> None:
        """Result is frozen."""
        target = LatencyTarget("R0", 10, 50, 100, "Test")
        result = SLOCheckResult(
            phase="R0",
            duration_ms=25.0,
            level=SLOComplianceLevel.GOOD,
            target=target,
            message="Test",
        )
        with pytest.raises(AttributeError):
            result.duration_ms = 50.0  # type: ignore[misc]

    def test_is_compliant_excellent(self) -> None:
        """EXCELLENT is compliant."""
        target = LatencyTarget("R0", 10, 50, 100, "Test")
        result = SLOCheckResult(
            phase="R0",
            duration_ms=5.0,
            level=SLOComplianceLevel.EXCELLENT,
            target=target,
            message="Test",
        )
        assert result.is_compliant

    def test_is_compliant_breach(self) -> None:
        """BREACH is not compliant."""
        target = LatencyTarget("R0", 10, 50, 100, "Test")
        result = SLOCheckResult(
            phase="R0",
            duration_ms=150.0,
            level=SLOComplianceLevel.BREACH,
            target=target,
            message="Test",
        )
        assert not result.is_compliant
