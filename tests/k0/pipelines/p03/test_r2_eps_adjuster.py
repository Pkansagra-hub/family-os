"""
Tests for EpsAdjuster — Adaptive eps learning via silhouette score optimization.

Issue 4.2.5: Implement adaptive eps learning (silhouette-driven)

Tests:
    1. test_no_adjustment_above_silhouette_target: silhouette >= 0.5 returns same eps
    2. test_decrease_eps_large_clusters: avg_size > 10, silhouette < 0.5 → eps decreases
    3. test_increase_eps_high_noise: singleton_rate > 0.20, silhouette < 0.5 → eps increases
    4. test_momentum_smoothing: verify 0.9/0.1 weighted average
    5. test_bounds_min: eps cannot go below 0.15
    6. test_bounds_max: eps cannot go above 0.40
    7. test_cold_start_no_adjustment: < 100 clusters returns same eps
    8. test_no_adjustment_in_range: both metrics in range → no adjustment
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.eps_adjuster import (
    EpsAdjuster,
    EpsAdjustmentConfig,
    EpsAdjustmentResult,
)

# =============================================================================
# Basic Adjustment Tests
# =============================================================================


class TestEpsAdjusterBasic:
    """Test EpsAdjuster basic functionality."""

    def test_no_adjustment_above_silhouette_target(self) -> None:
        """Silhouette >= 0.5 returns same eps (no adjustment needed)."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.25,
            silhouette_score=0.55,  # Above target
            avg_cluster_size=5.0,
            singleton_rate=0.10,
            total_clusters_formed=150,
        )

        assert not result.adjusted
        assert result.new_eps == 0.25
        assert "target" in result.reason.lower() or "0.5" in result.reason

    def test_cold_start_no_adjustment(self) -> None:
        """Cold start (< 100 clusters) returns same eps."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.25,
            silhouette_score=0.30,  # Poor quality
            avg_cluster_size=15.0,  # Would trigger decrease
            singleton_rate=0.10,
            total_clusters_formed=50,  # Below cold start threshold
        )

        assert not result.adjusted
        assert result.cold_start
        assert result.new_eps == 0.25
        assert "cold start" in result.reason.lower()


# =============================================================================
# Decrease Eps Tests
# =============================================================================


class TestEpsDecrease:
    """Test EpsAdjuster eps decrease scenarios."""

    def test_decrease_eps_large_clusters(self) -> None:
        """avg_cluster_size > 10 AND silhouette < 0.5 → decrease eps."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.25,
            silhouette_score=0.35,  # Below target
            avg_cluster_size=15.0,  # Above 10 threshold
            singleton_rate=0.10,  # Normal
            total_clusters_formed=150,
        )

        assert result.adjusted
        assert result.new_eps < result.previous_eps
        assert "decrease" in result.reason.lower()

    def test_decrease_respects_bounds(self) -> None:
        """eps cannot decrease below eps_min (0.15)."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.15,  # Already at min
            silhouette_score=0.30,
            avg_cluster_size=15.0,  # Would trigger decrease
            singleton_rate=0.10,
            total_clusters_formed=150,
        )

        # Should still try to decrease, but be clamped
        assert result.new_eps >= 0.15

    def test_bounds_min_enforced(self) -> None:
        """Repeated decreases don't go below min."""
        adjuster = EpsAdjuster()

        # Start at 0.16 (near min), trigger decrease
        result = adjuster.adjust(
            current_eps=0.16,
            silhouette_score=0.30,
            avg_cluster_size=15.0,
            singleton_rate=0.10,
            total_clusters_formed=150,
        )

        # With momentum smoothing: 0.9 * 0.16 + 0.1 * 0.14 = 0.158
        # Then clamped to min 0.15
        assert result.new_eps >= 0.15


# =============================================================================
# Increase Eps Tests
# =============================================================================


class TestEpsIncrease:
    """Test EpsAdjuster eps increase scenarios."""

    def test_increase_eps_high_noise(self) -> None:
        """singleton_rate > 0.20 AND silhouette < 0.5 → increase eps."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.25,
            silhouette_score=0.35,  # Below target
            avg_cluster_size=5.0,  # Normal (not triggering decrease)
            singleton_rate=0.25,  # Above 0.20 threshold
            total_clusters_formed=150,
        )

        assert result.adjusted
        assert result.new_eps > result.previous_eps
        assert "increase" in result.reason.lower()

    def test_bounds_max_enforced(self) -> None:
        """eps cannot increase above eps_max (0.40)."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.40,  # Already at max
            silhouette_score=0.30,
            avg_cluster_size=5.0,
            singleton_rate=0.25,  # Would trigger increase
            total_clusters_formed=150,
        )

        # Should be clamped
        assert result.new_eps <= 0.40


# =============================================================================
# Momentum Smoothing Tests
# =============================================================================


class TestMomentumSmoothing:
    """Test EpsAdjuster momentum smoothing."""

    def test_momentum_smoothing_decrease(self) -> None:
        """Verify 0.9/0.1 weighted average for decrease."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.30,
            silhouette_score=0.35,
            avg_cluster_size=15.0,  # Trigger decrease
            singleton_rate=0.10,
            total_clusters_formed=150,
        )

        # Expected: step = 0.02, adjusted = 0.28
        # Smoothed: 0.9 * 0.30 + 0.1 * 0.28 = 0.27 + 0.028 = 0.298
        expected = 0.9 * 0.30 + 0.1 * (0.30 - 0.02)
        assert result.new_eps == pytest.approx(expected, abs=0.001)

    def test_momentum_smoothing_increase(self) -> None:
        """Verify 0.9/0.1 weighted average for increase."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.30,
            silhouette_score=0.35,
            avg_cluster_size=5.0,
            singleton_rate=0.25,  # Trigger increase
            total_clusters_formed=150,
        )

        # Expected: step = 0.02, adjusted = 0.32
        # Smoothed: 0.9 * 0.30 + 0.1 * 0.32 = 0.27 + 0.032 = 0.302
        expected = 0.9 * 0.30 + 0.1 * (0.30 + 0.02)
        assert result.new_eps == pytest.approx(expected, abs=0.001)

    def test_custom_momentum(self) -> None:
        """Custom momentum value is respected."""
        config = EpsAdjustmentConfig(momentum=0.5)  # 50/50 instead of 90/10
        adjuster = EpsAdjuster(config)

        result = adjuster.adjust(
            current_eps=0.30,
            silhouette_score=0.35,
            avg_cluster_size=15.0,  # Trigger decrease
            singleton_rate=0.10,
            total_clusters_formed=150,
        )

        # Expected: 0.5 * 0.30 + 0.5 * 0.28 = 0.29
        expected = 0.5 * 0.30 + 0.5 * (0.30 - 0.02)
        assert result.new_eps == pytest.approx(expected, abs=0.001)


# =============================================================================
# No Adjustment Tests
# =============================================================================


class TestNoAdjustment:
    """Test scenarios where no adjustment occurs."""

    def test_no_adjustment_metrics_in_range(self) -> None:
        """Silhouette < 0.5 but metrics in acceptable range → no adjustment."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.25,
            silhouette_score=0.40,  # Below target
            avg_cluster_size=8.0,  # Not > 10
            singleton_rate=0.15,  # Not > 0.20
            total_clusters_formed=150,
        )

        assert not result.adjusted
        assert result.new_eps == 0.25

    def test_decrease_priority_over_increase(self) -> None:
        """If both conditions met, decrease takes priority."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.25,
            silhouette_score=0.30,
            avg_cluster_size=15.0,  # Would trigger decrease
            singleton_rate=0.25,  # Would also trigger increase
            total_clusters_formed=150,
        )

        # Decrease should win (checked first in algorithm)
        assert result.adjusted
        assert result.new_eps < result.previous_eps


# =============================================================================
# Result Tests
# =============================================================================


class TestEpsAdjustmentResult:
    """Test EpsAdjustmentResult dataclass."""

    def test_result_to_dict(self) -> None:
        """Result.to_dict() returns all fields."""
        result = EpsAdjustmentResult(
            previous_eps=0.25,
            new_eps=0.252,
            adjusted=True,
            reason="test reason",
            silhouette_score=0.35,
            avg_cluster_size=15.0,
            singleton_rate=0.10,
            cold_start=False,
        )

        data = result.to_dict()

        assert data["previous_eps"] == 0.25
        assert data["new_eps"] == 0.252
        assert data["adjusted"] is True
        assert data["reason"] == "test reason"
        assert data["silhouette_score"] == 0.35
        assert data["avg_cluster_size"] == 15.0
        assert data["singleton_rate"] == 0.1
        assert data["cold_start"] is False


# =============================================================================
# Config Tests
# =============================================================================


class TestEpsAdjustmentConfig:
    """Test EpsAdjustmentConfig validation."""

    def test_default_config(self) -> None:
        """Default config has expected values."""
        config = EpsAdjustmentConfig()

        assert config.eps_min == 0.15
        assert config.eps_max == 0.40
        assert config.eps_step == 0.02
        assert config.silhouette_target == 0.5
        assert config.momentum == 0.9
        assert config.cold_start_threshold == 100

    def test_custom_config(self) -> None:
        """Custom config values are respected."""
        config = EpsAdjustmentConfig(
            eps_min=0.10,
            eps_max=0.50,
            eps_step=0.05,
            silhouette_target=0.6,
            momentum=0.8,
            cold_start_threshold=50,
        )

        assert config.eps_min == 0.10
        assert config.eps_max == 0.50
        assert config.eps_step == 0.05
        assert config.silhouette_target == 0.6
        assert config.momentum == 0.8
        assert config.cold_start_threshold == 50
