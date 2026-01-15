"""Tests for P03 Throughput Tracker.

Issue 6.4.5: Throughput SLOs for P03 operations.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from k0.pipelines.p03.qos.throughput_tracker import (
    P03_THROUGHPUT_TARGETS,
    P03ThroughputTracker,
    ThroughputComplianceLevel,
    ThroughputSnapshot,
    ThroughputTargets,
)


class TestThroughputTargets:
    """Test throughput target definitions."""

    def test_default_targets(self) -> None:
        """Default targets match dossier."""
        targets = P03_THROUGHPUT_TARGETS
        assert targets.events_per_cycle == 1000
        assert targets.cycles_per_hour == 40
        assert targets.events_per_hour == 40000
        assert targets.peak_events_per_hour == 100000
        assert targets.cycle_interval_seconds == 90.0

    def test_custom_targets(self) -> None:
        """Custom targets can be created."""
        targets = ThroughputTargets(
            events_per_cycle=500,
            cycles_per_hour=60,
            events_per_hour=30000,
            peak_events_per_hour=50000,
            cycle_interval_seconds=60.0,
        )
        assert targets.events_per_cycle == 500
        assert targets.cycles_per_hour == 60


class TestP03ThroughputTracker:
    """Test throughput tracker basic operations."""

    @pytest.fixture
    def tracker(self) -> P03ThroughputTracker:
        """Create tracker without metrics exporter."""
        return P03ThroughputTracker()

    def test_init_defaults(self, tracker: P03ThroughputTracker) -> None:
        """Default initialization."""
        assert tracker.pipeline_id == "p03_consolidation"
        assert tracker.targets == P03_THROUGHPUT_TARGETS

    def test_init_custom_targets(self) -> None:
        """Custom targets accepted."""
        custom = ThroughputTargets(events_per_cycle=500)
        tracker = P03ThroughputTracker(targets=custom)
        assert tracker.targets.events_per_cycle == 500

    def test_record_cycle(self, tracker: P03ThroughputTracker) -> None:
        """Record a cycle."""
        tracker.record_cycle(event_count=1000, duration_seconds=30.0)

        snapshot = tracker.get_throughput_snapshot()
        assert snapshot.total_cycles == 1
        assert snapshot.total_events == 1000

    def test_record_multiple_cycles(self, tracker: P03ThroughputTracker) -> None:
        """Record multiple cycles."""
        tracker.record_cycle(event_count=1000, duration_seconds=30.0)
        tracker.record_cycle(event_count=1200, duration_seconds=35.0)
        tracker.record_cycle(event_count=800, duration_seconds=25.0)

        snapshot = tracker.get_throughput_snapshot()
        assert snapshot.total_cycles == 3
        assert snapshot.total_events == 3000
        assert snapshot.avg_events_per_cycle == 1000.0

    def test_record_events_only(self, tracker: P03ThroughputTracker) -> None:
        """Record events without full cycle."""
        tracker.record_events(500)

        snapshot = tracker.get_throughput_snapshot()
        assert snapshot.total_events == 500
        assert snapshot.total_cycles == 0

    def test_reset(self, tracker: P03ThroughputTracker) -> None:
        """Reset clears all tracking."""
        tracker.record_cycle(event_count=1000, duration_seconds=30.0)
        tracker.reset()

        snapshot = tracker.get_throughput_snapshot()
        assert snapshot.total_cycles == 0
        assert snapshot.total_events == 0


class TestThroughputSnapshot:
    """Test throughput snapshot calculations."""

    @pytest.fixture
    def tracker(self) -> P03ThroughputTracker:
        """Create tracker."""
        return P03ThroughputTracker()

    def test_empty_snapshot(self, tracker: P03ThroughputTracker) -> None:
        """Empty tracker returns degraded snapshot."""
        snapshot = tracker.get_throughput_snapshot()

        assert snapshot.events_per_hour == 0.0
        assert snapshot.cycles_per_hour == 0.0
        assert snapshot.avg_events_per_cycle == 0.0
        assert snapshot.compliance_level == ThroughputComplianceLevel.DEGRADED
        assert not snapshot.is_compliant

    def test_snapshot_is_compliant_property(self) -> None:
        """is_compliant property works correctly."""
        # Compliant levels
        assert ThroughputSnapshot(
            events_per_hour=40000,
            cycles_per_hour=40,
            avg_events_per_cycle=1000,
            total_events=1000,
            total_cycles=1,
            compliance_level=ThroughputComplianceLevel.EXCELLENT,
            compliance_message="test",
        ).is_compliant

        assert ThroughputSnapshot(
            events_per_hour=35000,
            cycles_per_hour=35,
            avg_events_per_cycle=1000,
            total_events=1000,
            total_cycles=1,
            compliance_level=ThroughputComplianceLevel.GOOD,
            compliance_message="test",
        ).is_compliant

        # Non-compliant levels
        assert not ThroughputSnapshot(
            events_per_hour=25000,
            cycles_per_hour=25,
            avg_events_per_cycle=1000,
            total_events=1000,
            total_cycles=1,
            compliance_level=ThroughputComplianceLevel.WARNING,
            compliance_message="test",
        ).is_compliant


class TestComplianceChecks:
    """Test SLO compliance checking."""

    @pytest.fixture
    def tracker(self) -> P03ThroughputTracker:
        """Create tracker."""
        return P03ThroughputTracker()

    def test_check_cycle_rate_no_cycles(self, tracker: P03ThroughputTracker) -> None:
        """No cycles fails compliance."""
        is_compliant, message = tracker.check_cycle_rate_compliance()
        assert not is_compliant
        assert "low" in message.lower()

    def test_check_events_per_hour_no_events(self, tracker: P03ThroughputTracker) -> None:
        """No events fails compliance."""
        is_compliant, message = tracker.check_events_per_hour_compliance()
        assert not is_compliant
        assert "low" in message.lower()


class TestComplianceAssessment:
    """Test compliance level assessment."""

    def test_assess_excellent(self) -> None:
        """100%+ of target is excellent."""
        tracker = P03ThroughputTracker()
        level, message = tracker._assess_compliance(40000, 40)
        assert level == ThroughputComplianceLevel.EXCELLENT
        assert "Exceeding" in message

    def test_assess_good(self) -> None:
        """80-100% of target is good."""
        tracker = P03ThroughputTracker()
        level, message = tracker._assess_compliance(35000, 35)
        assert level == ThroughputComplianceLevel.GOOD
        assert "Meeting" in message

    def test_assess_warning(self) -> None:
        """60-80% of target is warning."""
        tracker = P03ThroughputTracker()
        level, message = tracker._assess_compliance(28000, 28)
        assert level == ThroughputComplianceLevel.WARNING
        assert "Below" in message

    def test_assess_degraded(self) -> None:
        """<60% of target is degraded."""
        tracker = P03ThroughputTracker()
        level, message = tracker._assess_compliance(20000, 20)
        assert level == ThroughputComplianceLevel.DEGRADED
        assert "Degraded" in message

    def test_assess_mixed_ratios(self) -> None:
        """Uses minimum of events and cycles ratio."""
        tracker = P03ThroughputTracker()
        # High events, low cycles
        level, _ = tracker._assess_compliance(40000, 20)
        assert level == ThroughputComplianceLevel.DEGRADED


class TestWindowPruning:
    """Test rolling window management."""

    def test_prune_old_records(self) -> None:
        """Old records are pruned."""
        tracker = P03ThroughputTracker(window_size_hours=1.0)

        # Mock time to add old record
        with patch("time.time") as mock_time:
            # Add record 2 hours ago
            mock_time.return_value = 1000.0
            tracker.record_cycle(event_count=1000, duration_seconds=30.0)

            # Check now (2 hours later)
            mock_time.return_value = 1000.0 + 7200.0
            tracker.get_throughput_snapshot()  # Triggers pruning

            # Record should be pruned
            assert len(tracker._cycles) == 0


class TestWithMetricsExporter:
    """Test with mock MetricsExporter."""

    def test_init_with_exporter(self) -> None:
        """Initialize with metrics exporter."""
        mock_exporter = MagicMock()

        P03ThroughputTracker(mock_exporter)

        # Should create counter and gauge
        assert mock_exporter.counter.call_count == 2
        assert mock_exporter.gauge.call_count == 2

    def test_record_cycle_updates_counters(self) -> None:
        """Recording cycle updates Prometheus counters."""
        mock_exporter = MagicMock()
        mock_counter = MagicMock()
        mock_exporter.counter.return_value = mock_counter

        tracker = P03ThroughputTracker(mock_exporter)
        tracker.record_cycle(event_count=1000, duration_seconds=30.0)

        mock_counter.labels.return_value.inc.assert_called()


class TestThroughputComplianceLevel:
    """Test compliance level enum."""

    def test_all_levels_defined(self) -> None:
        """All compliance levels exist."""
        assert ThroughputComplianceLevel.EXCELLENT.value == "excellent"
        assert ThroughputComplianceLevel.GOOD.value == "good"
        assert ThroughputComplianceLevel.WARNING.value == "warning"
        assert ThroughputComplianceLevel.DEGRADED.value == "degraded"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_zero_event_cycle(self) -> None:
        """Zero event cycle is valid."""
        tracker = P03ThroughputTracker()
        tracker.record_cycle(event_count=0, duration_seconds=30.0)

        snapshot = tracker.get_throughput_snapshot()
        assert snapshot.total_cycles == 1
        assert snapshot.total_events == 0

    def test_very_large_event_count(self) -> None:
        """Large event counts handled."""
        tracker = P03ThroughputTracker()
        tracker.record_cycle(event_count=1000000, duration_seconds=30.0)

        snapshot = tracker.get_throughput_snapshot()
        assert snapshot.total_events == 1000000

    def test_custom_window_size(self) -> None:
        """Custom window size works."""
        tracker = P03ThroughputTracker(window_size_hours=0.5)
        assert tracker._window_size_seconds == 1800.0

    def test_custom_pipeline_id(self) -> None:
        """Custom pipeline ID works."""
        tracker = P03ThroughputTracker(pipeline_id="custom_pipeline")
        assert tracker.pipeline_id == "custom_pipeline"
