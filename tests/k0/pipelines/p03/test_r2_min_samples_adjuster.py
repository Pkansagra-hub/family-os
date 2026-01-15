"""
Tests for MinSamplesAdjuster — Adaptive min_samples learning based on singleton rate.

Issue 4.2.6: Implement adaptive min_samples learning

Tests:
    1. test_increase_on_high_singleton_rate: 25% singletons → min_samples + 1
    2. test_decrease_on_low_singleton_rate: 3% singletons → min_samples - 1
    3. test_no_change_in_good_range: 10% singletons → no change
    4. test_bounds_min: cannot go below 2
    5. test_bounds_max: cannot go above 5
    6. test_at_max_no_increase: already at 5, no increase possible
    7. test_at_min_no_decrease: already at 2, no decrease possible
"""

from __future__ import annotations

from k0.modules.consolidation.algorithms.min_samples_adjuster import (
    MinSamplesAdjuster,
    MinSamplesAdjustmentResult,
    MinSamplesConfig,
)

# =============================================================================
# Increase Tests
# =============================================================================


class TestMinSamplesIncrease:
    """Test MinSamplesAdjuster increase scenarios."""

    def test_increase_on_high_singleton_rate(self) -> None:
        """singleton_rate > 0.20 → increase min_samples."""
        adjuster = MinSamplesAdjuster()

        result = adjuster.adjust(
            current_min_samples=2,
            singleton_rate=0.25,  # 25% noise (above 20%)
        )

        assert result.adjusted
        assert result.new_min_samples == 3
        assert result.direction == "increase"
        assert "increase" in result.reason.lower()

    def test_increase_multiple_times(self) -> None:
        """Multiple increases work up to max."""
        adjuster = MinSamplesAdjuster()

        # 2 → 3
        result1 = adjuster.adjust(current_min_samples=2, singleton_rate=0.30)
        assert result1.new_min_samples == 3

        # 3 → 4
        result2 = adjuster.adjust(current_min_samples=3, singleton_rate=0.30)
        assert result2.new_min_samples == 4

        # 4 → 5
        result3 = adjuster.adjust(current_min_samples=4, singleton_rate=0.30)
        assert result3.new_min_samples == 5

    def test_at_max_no_increase(self) -> None:
        """Already at max (5), cannot increase further."""
        adjuster = MinSamplesAdjuster()

        result = adjuster.adjust(
            current_min_samples=5,  # At max
            singleton_rate=0.30,  # Would trigger increase
        )

        assert not result.adjusted
        assert result.new_min_samples == 5
        assert "max" in result.reason.lower()


# =============================================================================
# Decrease Tests
# =============================================================================


class TestMinSamplesDecrease:
    """Test MinSamplesAdjuster decrease scenarios."""

    def test_decrease_on_low_singleton_rate(self) -> None:
        """singleton_rate < 0.05 → decrease min_samples."""
        adjuster = MinSamplesAdjuster()

        result = adjuster.adjust(
            current_min_samples=3,
            singleton_rate=0.03,  # 3% noise (below 5%)
        )

        assert result.adjusted
        assert result.new_min_samples == 2
        assert result.direction == "decrease"
        assert "decrease" in result.reason.lower()

    def test_decrease_multiple_times(self) -> None:
        """Multiple decreases work down to min."""
        adjuster = MinSamplesAdjuster()

        # 5 → 4
        result1 = adjuster.adjust(current_min_samples=5, singleton_rate=0.02)
        assert result1.new_min_samples == 4

        # 4 → 3
        result2 = adjuster.adjust(current_min_samples=4, singleton_rate=0.02)
        assert result2.new_min_samples == 3

        # 3 → 2
        result3 = adjuster.adjust(current_min_samples=3, singleton_rate=0.02)
        assert result3.new_min_samples == 2

    def test_at_min_no_decrease(self) -> None:
        """Already at min (2), cannot decrease further."""
        adjuster = MinSamplesAdjuster()

        result = adjuster.adjust(
            current_min_samples=2,  # At min
            singleton_rate=0.02,  # Would trigger decrease
        )

        assert not result.adjusted
        assert result.new_min_samples == 2
        assert "min" in result.reason.lower()


# =============================================================================
# No Change Tests
# =============================================================================


class TestMinSamplesNoChange:
    """Test MinSamplesAdjuster no-change scenarios."""

    def test_no_change_in_good_range(self) -> None:
        """singleton_rate in [0.05, 0.20] → no change."""
        adjuster = MinSamplesAdjuster()

        result = adjuster.adjust(
            current_min_samples=3,
            singleton_rate=0.10,  # 10% noise (in good range)
        )

        assert not result.adjusted
        assert result.new_min_samples == 3
        assert result.direction == "none"
        assert "good range" in result.reason.lower()

    def test_exactly_at_low_threshold(self) -> None:
        """singleton_rate exactly at 0.05 → no change (inclusive)."""
        adjuster = MinSamplesAdjuster()

        result = adjuster.adjust(
            current_min_samples=3,
            singleton_rate=0.05,  # Exactly at low threshold
        )

        # At threshold (not below), so no change
        assert not result.adjusted
        assert result.new_min_samples == 3

    def test_exactly_at_high_threshold(self) -> None:
        """singleton_rate exactly at 0.20 → no change (exclusive upper)."""
        adjuster = MinSamplesAdjuster()

        result = adjuster.adjust(
            current_min_samples=3,
            singleton_rate=0.20,  # Exactly at high threshold
        )

        # At threshold (not above), so no change
        assert not result.adjusted
        assert result.new_min_samples == 3


# =============================================================================
# Bounds Tests
# =============================================================================


class TestMinSamplesBounds:
    """Test MinSamplesAdjuster bounds enforcement."""

    def test_bounds_min_value(self) -> None:
        """min_samples bounded by min value (2)."""
        adjuster = MinSamplesAdjuster()

        # Already at 2, try to decrease
        result = adjuster.adjust(current_min_samples=2, singleton_rate=0.01)

        assert result.new_min_samples >= 2

    def test_bounds_max_value(self) -> None:
        """min_samples bounded by max value (5)."""
        adjuster = MinSamplesAdjuster()

        # Already at 5, try to increase
        result = adjuster.adjust(current_min_samples=5, singleton_rate=0.50)

        assert result.new_min_samples <= 5

    def test_custom_bounds(self) -> None:
        """Custom min/max bounds are respected."""
        config = MinSamplesConfig(min_samples_min=3, min_samples_max=7)
        adjuster = MinSamplesAdjuster(config)

        # At custom min (3), try to decrease
        result1 = adjuster.adjust(current_min_samples=3, singleton_rate=0.01)
        assert result1.new_min_samples >= 3

        # At custom max (7), try to increase
        result2 = adjuster.adjust(current_min_samples=7, singleton_rate=0.50)
        assert result2.new_min_samples <= 7


# =============================================================================
# Result Tests
# =============================================================================


class TestMinSamplesAdjustmentResult:
    """Test MinSamplesAdjustmentResult dataclass."""

    def test_result_to_dict(self) -> None:
        """Result.to_dict() returns all fields."""
        result = MinSamplesAdjustmentResult(
            previous_min_samples=2,
            new_min_samples=3,
            adjusted=True,
            reason="test reason",
            singleton_rate=0.25,
            direction="increase",
        )

        data = result.to_dict()

        assert data["previous_min_samples"] == 2
        assert data["new_min_samples"] == 3
        assert data["adjusted"] is True
        assert data["reason"] == "test reason"
        assert data["singleton_rate"] == 0.25
        assert data["direction"] == "increase"


# =============================================================================
# Config Tests
# =============================================================================


class TestMinSamplesConfig:
    """Test MinSamplesConfig validation."""

    def test_default_config(self) -> None:
        """Default config has expected values."""
        config = MinSamplesConfig()

        assert config.min_samples_min == 2
        assert config.min_samples_max == 5
        assert config.noise_threshold_high == 0.20
        assert config.noise_threshold_low == 0.05

    def test_custom_config(self) -> None:
        """Custom config values are respected."""
        config = MinSamplesConfig(
            min_samples_min=1,
            min_samples_max=10,
            noise_threshold_high=0.30,
            noise_threshold_low=0.10,
        )

        assert config.min_samples_min == 1
        assert config.min_samples_max == 10
        assert config.noise_threshold_high == 0.30
        assert config.noise_threshold_low == 0.10

    def test_custom_thresholds_adjust_behavior(self) -> None:
        """Custom thresholds affect adjustment decisions."""
        config = MinSamplesConfig(
            noise_threshold_high=0.15,  # Stricter than default
            noise_threshold_low=0.10,
        )
        adjuster = MinSamplesAdjuster(config)

        # 18% would not trigger with default (0.20) but triggers with 0.15
        result = adjuster.adjust(current_min_samples=2, singleton_rate=0.18)

        assert result.adjusted
        assert result.new_min_samples == 3
