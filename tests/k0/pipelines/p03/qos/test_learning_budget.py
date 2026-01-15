"""Tests for P03 Learning Budget.

Issue 6.4.8: Learning compute budget tracking (<5% of cycle time).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.qos.learning_budget import (
    P03_LEARNING_BUDGET_CONFIG,
    LearningBudgetConfig,
    LearningBudgetSummary,
    LearningOperation,
    LearningOperationStats,
    P03LearningBudget,
)


class TestLearningOperation:
    """Test learning operation enumeration."""

    def test_all_operations_defined(self) -> None:
        """All operations defined."""
        ops = list(LearningOperation)
        assert LearningOperation.HEBBIAN_UPDATE in ops
        assert LearningOperation.IMPORTANCE_SCORING in ops
        assert LearningOperation.PATTERN_EXTRACTION in ops
        assert LearningOperation.EPISODE_CLUSTERING in ops
        assert LearningOperation.DREAM_EXPLORATION in ops
        assert LearningOperation.GAP_DETECTION in ops

    def test_operation_values(self) -> None:
        """Operations have string values."""
        assert LearningOperation.HEBBIAN_UPDATE.value == "hebbian_update"
        assert LearningOperation.PATTERN_EXTRACTION.value == "pattern_extraction"


class TestLearningBudgetConfig:
    """Test budget configuration."""

    def test_default_config(self) -> None:
        """Default config values match dossier."""
        config = P03_LEARNING_BUDGET_CONFIG
        assert config.max_cycle_ratio == 0.05  # 5%
        assert config.warning_ratio == 0.04  # 4%

    def test_config_per_operation_limits(self) -> None:
        """Config has per-operation limits."""
        config = P03_LEARNING_BUDGET_CONFIG
        limits = config.per_operation_limits_ms
        assert limits is not None
        assert "hebbian_update" in limits
        assert limits["hebbian_update"] == 50.0

    def test_custom_config(self) -> None:
        """Create custom config."""
        custom = LearningBudgetConfig(
            max_cycle_ratio=0.10,
            warning_ratio=0.08,
            per_operation_limits_ms={
                "hebbian_update": 100.0,
            },
        )
        assert custom.max_cycle_ratio == 0.10


class TestP03LearningBudget:
    """Test learning budget tracking."""

    @pytest.fixture
    def learning_budget(self) -> P03LearningBudget:
        """Create learning budget without exporter."""
        return P03LearningBudget()

    def test_init_without_exporter(self, learning_budget: P03LearningBudget) -> None:
        """Initialize without metrics exporter."""
        assert learning_budget.pipeline_id == "p03_consolidation"
        assert learning_budget._learning_duration_histogram is None

    def test_start_cycle(self, learning_budget: P03LearningBudget) -> None:
        """Start a new cycle."""
        learning_budget.start_cycle()
        assert learning_budget._cycle_start_time > 0
        assert learning_budget._total_learning_ms == 0.0

    def test_record_learning_time(self, learning_budget: P03LearningBudget) -> None:
        """Record learning operation time."""
        learning_budget.start_cycle()
        stats = learning_budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 10.0)

        assert stats.operation == LearningOperation.HEBBIAN_UPDATE
        assert stats.duration_ms == 10.0
        assert stats.within_budget  # 10ms <= 50ms default limit

    def test_record_multiple_operations(self, learning_budget: P03LearningBudget) -> None:
        """Record multiple operation types."""
        learning_budget.start_cycle()
        learning_budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 10.0)
        learning_budget.record_learning_time(LearningOperation.GAP_DETECTION, 5.0)
        learning_budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 8.0)

        summary = learning_budget.get_operation_summary()
        assert "hebbian_update" in summary
        assert summary["hebbian_update"]["count"] == 2
        assert summary["hebbian_update"]["total_ms"] == 18.0

        assert "gap_detection" in summary
        assert summary["gap_detection"]["count"] == 1


class TestTrackOperationContextManager:
    """Test track_operation context manager."""

    def test_track_operation_basic(self) -> None:
        """Basic timing with context manager."""
        budget = P03LearningBudget()
        budget.start_cycle()

        with budget.track_operation(LearningOperation.PATTERN_EXTRACTION):
            time.sleep(0.01)  # 10ms

        summary = budget.get_operation_summary()
        assert "pattern_extraction" in summary
        assert summary["pattern_extraction"]["count"] == 1
        assert summary["pattern_extraction"]["total_ms"] >= 10.0

    def test_track_operation_exception(self) -> None:
        """Context manager records on exception."""
        budget = P03LearningBudget()
        budget.start_cycle()

        with pytest.raises(ValueError):
            with budget.track_operation(LearningOperation.IMPORTANCE_SCORING):
                raise ValueError("Test error")

        # Still recorded despite exception
        summary = budget.get_operation_summary()
        assert "importance_scoring" in summary
        assert summary["importance_scoring"]["count"] == 1


class TestBudgetCompliance:
    """Test budget compliance checking."""

    @pytest.fixture
    def learning_budget(self) -> P03LearningBudget:
        """Create learning budget."""
        return P03LearningBudget()

    def test_within_budget(self, learning_budget: P03LearningBudget) -> None:
        """Operations within budget."""
        learning_budget.start_cycle()
        learning_budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 20.0)

        is_ok, remaining_ms, msg = learning_budget.check_budget_status(1000.0)
        assert is_ok
        assert remaining_ms == 30.0  # 50ms budget - 20ms used
        assert "OK" in msg

    def test_approaching_budget(self, learning_budget: P03LearningBudget) -> None:
        """Approaching budget limit."""
        learning_budget.start_cycle()
        learning_budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 42.0)

        is_ok, remaining_ms, msg = learning_budget.check_budget_status(1000.0)
        # Still OK but approaching limit
        assert is_ok
        assert remaining_ms == 8.0
        assert "OK" in msg

    def test_exceeded_budget(self, learning_budget: P03LearningBudget) -> None:
        """Budget exceeded."""
        learning_budget.start_cycle()
        learning_budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 55.0)

        is_ok, remaining_ms, msg = learning_budget.check_budget_status(1000.0)
        assert not is_ok
        assert remaining_ms == -5.0
        assert "exceeded" in msg.lower()


class TestEndCycle:
    """Test cycle completion."""

    def test_end_cycle_calculates_ratio(self) -> None:
        """End cycle calculates learning ratio."""
        budget = P03LearningBudget()
        budget.start_cycle()
        budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 30.0)

        summary = budget.end_cycle(total_cycle_ms=1000.0)

        assert summary.total_learning_ms == 30.0
        assert summary.cycle_duration_ms == 1000.0
        assert summary.learning_ratio == 0.03  # 3%

    def test_end_cycle_budget_compliance(self) -> None:
        """End cycle reports budget compliance."""
        budget = P03LearningBudget()
        budget.start_cycle()
        budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 30.0)

        summary = budget.end_cycle(total_cycle_ms=1000.0)
        assert summary.within_budget  # 3% < 5%

    def test_end_cycle_budget_exceeded(self) -> None:
        """End cycle reports budget exceeded."""
        budget = P03LearningBudget()
        budget.start_cycle()
        budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 60.0)

        summary = budget.end_cycle(total_cycle_ms=1000.0)
        assert not summary.within_budget  # 6% > 5%


class TestLearningBudgetSummary:
    """Test budget summary."""

    def test_summary_structure(self) -> None:
        """Summary has expected fields."""
        summary = LearningBudgetSummary(
            total_learning_ms=30.0,
            cycle_duration_ms=1000.0,
            learning_ratio=0.03,
            within_budget=True,
            operations={
                "hebbian_update": 30.0,
            },
        )
        assert summary.learning_ratio == 0.03
        assert summary.within_budget

    def test_summary_from_budget(self) -> None:
        """Summary computed from budget tracking."""
        budget = P03LearningBudget()
        budget.start_cycle()
        budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 45.0)

        summary = budget.end_cycle(total_cycle_ms=1000.0)
        # 45ms / 1000ms = 4.5% - within budget but approaching warning
        assert summary.learning_ratio == 0.045


class TestLearningOperationStats:
    """Test operation stats dataclass."""

    def test_stats_structure(self) -> None:
        """Stats have expected fields."""
        stats = LearningOperationStats(
            operation=LearningOperation.HEBBIAN_UPDATE,
            duration_ms=25.0,
            within_budget=True,
            budget_ratio=0.5,
        )
        assert stats.duration_ms == 25.0
        assert stats.within_budget

    def test_stats_over_budget(self) -> None:
        """Stats correctly report over-budget."""
        stats = LearningOperationStats(
            operation=LearningOperation.HEBBIAN_UPDATE,
            duration_ms=75.0,
            within_budget=False,
            budget_ratio=1.5,  # 75ms / 50ms limit
        )
        assert not stats.within_budget
        assert stats.budget_ratio > 1.0


class TestResetCycle:
    """Test cycle reset."""

    def test_reset_clears_stats(self) -> None:
        """Reset clears all operation stats."""
        budget = P03LearningBudget()
        budget.start_cycle()
        budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 10.0)

        budget.reset()

        summary = budget.get_operation_summary()
        assert len(summary) == 0
        assert budget._total_learning_ms == 0.0


class TestWithMetricsExporter:
    """Test with mock MetricsExporter."""

    def test_init_with_exporter(self) -> None:
        """Initialize with metrics exporter."""
        mock_exporter = MagicMock()

        P03LearningBudget(mock_exporter)

        mock_exporter.histogram.assert_called()
        mock_exporter.gauge.assert_called()
        mock_exporter.counter.assert_called()

    def test_record_updates_histogram(self) -> None:
        """Recording updates Prometheus histogram."""
        mock_exporter = MagicMock()
        mock_histogram = MagicMock()
        mock_exporter.histogram.return_value = mock_histogram

        budget = P03LearningBudget(mock_exporter)
        budget.start_cycle()
        budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 10.0)

        mock_histogram.labels.return_value.observe.assert_called()

    def test_exceeded_increments_counter(self) -> None:
        """Budget exceeded increments counter."""
        mock_exporter = MagicMock()
        mock_counter = MagicMock()
        mock_exporter.counter.return_value = mock_counter

        budget = P03LearningBudget(mock_exporter)
        budget.start_cycle()
        budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 55.0)

        budget.end_cycle(total_cycle_ms=1000.0)

        # Should increment exceeded counter
        mock_counter.labels.return_value.inc.assert_called()


class TestPerOperationLimits:
    """Test per-operation budget limits."""

    def test_operation_within_limit(self) -> None:
        """Operation within per-operation limit."""
        budget = P03LearningBudget()
        budget.start_cycle()

        stats = budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 25.0)
        # Default limit for hebbian_update is 50ms
        assert stats.within_budget
        assert stats.budget_ratio == 0.5  # 25ms / 50ms

    def test_operation_exceeds_limit(self) -> None:
        """Operation exceeds per-operation limit."""
        budget = P03LearningBudget()
        budget.start_cycle()

        stats = budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 75.0)
        # 75ms > 50ms default limit
        assert not stats.within_budget
        assert stats.budget_ratio == 1.5  # 75ms / 50ms

    def test_custom_operation_limit(self) -> None:
        """Custom per-operation limit."""
        config = LearningBudgetConfig(
            max_cycle_ratio=0.05,
            warning_ratio=0.04,
            per_operation_limits_ms={
                "hebbian_update": 20.0,  # Lower limit
            },
        )
        budget = P03LearningBudget(config=config)
        budget.start_cycle()

        stats = budget.record_learning_time(LearningOperation.HEBBIAN_UPDATE, 25.0)
        # 25ms > 20ms custom limit
        assert not stats.within_budget
