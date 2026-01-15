"""
Tests for ClusterQualityTracker — Closed-loop cluster quality metrics.

Issue 4.2.7: Implement closed-loop cluster quality metrics

Tests:
    1. test_composite_quality_formula: verify weights 0.40/0.30/0.20/0.10
    2. test_rates_from_counts: correct rate computation
    3. test_alert_after_3_failures: silhouette < 0.3 × 3 triggers alert
    4. test_no_alert_if_recovery: alert not triggered if quality recovers
    5. test_tuning_recommendations: quality issues map to parameter adjustments
    6. test_metrics_to_dict: serialization works correctly
    7. test_is_acceptable_threshold: composite > 0.5 is acceptable
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from k0.modules.consolidation.algorithms.cluster_quality import (
    WEIGHT_CORRECTION,
    WEIGHT_GROUNDING,
    WEIGHT_SILHOUETTE,
    WEIGHT_SINGLETON,
    ClusterQualityMetrics,
    ClusterQualityTracker,
)

# =============================================================================
# Mock R2 Output
# =============================================================================


@dataclass
class MockR2Output:
    """Mock R2 staged output for testing."""

    batch_silhouette_score: float = 0.5
    cluster_count: int = 10
    noise_count: int = 2


# =============================================================================
# Composite Quality Formula Tests
# =============================================================================


class TestCompositeQualityFormula:
    """Test ClusterQualityMetrics composite formula."""

    def test_composite_quality_formula_perfect(self) -> None:
        """Perfect metrics → composite = 1.0."""
        metrics = ClusterQualityMetrics(
            silhouette_score=1.0,  # Max silhouette
            grounding_rate=1.0,  # All clusters grounded
            correction_rate=0.0,  # No corrections
            singleton_rate=0.0,  # No singletons
        )

        composite = metrics.compute_composite()

        # Formula: 0.40 × normalized_silhouette + 0.30 × grounding + 0.20 × (1-correction) + 0.10 × (1-singleton)
        # normalized_silhouette = (1.0 + 1.0) / 2.0 = 1.0
        # = 0.40 × 1.0 + 0.30 × 1.0 + 0.20 × 1.0 + 0.10 × 1.0 = 1.0
        assert composite == pytest.approx(1.0, abs=0.01)

    def test_composite_quality_formula_worst(self) -> None:
        """Worst metrics → composite approaches 0."""
        metrics = ClusterQualityMetrics(
            silhouette_score=-1.0,  # Worst silhouette
            grounding_rate=0.0,  # No clusters grounded
            correction_rate=1.0,  # All corrections
            singleton_rate=1.0,  # All singletons
        )

        composite = metrics.compute_composite()

        # normalized_silhouette = (-1.0 + 1.0) / 2.0 = 0.0
        # = 0.40 × 0.0 + 0.30 × 0.0 + 0.20 × 0.0 + 0.10 × 0.0 = 0.0
        assert composite == pytest.approx(0.0, abs=0.01)

    def test_composite_quality_formula_weights(self) -> None:
        """Verify individual weights are correct."""
        assert WEIGHT_SILHOUETTE == 0.40
        assert WEIGHT_GROUNDING == 0.30
        assert WEIGHT_CORRECTION == 0.20
        assert WEIGHT_SINGLETON == 0.10
        assert (
            WEIGHT_SILHOUETTE + WEIGHT_GROUNDING + WEIGHT_CORRECTION + WEIGHT_SINGLETON
        ) == pytest.approx(1.0, abs=1e-9)

    def test_composite_quality_mixed(self) -> None:
        """Mixed metrics compute correctly."""
        metrics = ClusterQualityMetrics(
            silhouette_score=0.5,  # Moderate silhouette
            grounding_rate=0.5,  # Half grounded
            correction_rate=0.1,  # 10% corrections
            singleton_rate=0.2,  # 20% singletons
        )

        composite = metrics.compute_composite()

        # normalized_silhouette = (0.5 + 1.0) / 2.0 = 0.75
        # = 0.40 × 0.75 + 0.30 × 0.5 + 0.20 × 0.9 + 0.10 × 0.8
        # = 0.30 + 0.15 + 0.18 + 0.08 = 0.71
        expected = 0.40 * 0.75 + 0.30 * 0.5 + 0.20 * 0.9 + 0.10 * 0.8
        assert composite == pytest.approx(expected, abs=0.01)

    def test_silhouette_normalization(self) -> None:
        """Silhouette normalized from [-1, 1] to [0, 1]."""
        # Silhouette of 0 should normalize to 0.5
        metrics = ClusterQualityMetrics(
            silhouette_score=0.0,
            grounding_rate=0.0,
            correction_rate=1.0,
            singleton_rate=1.0,
        )
        composite = metrics.compute_composite()

        # Only silhouette contributes: 0.40 × 0.5 = 0.20
        expected = 0.40 * 0.5
        assert composite == pytest.approx(expected, abs=0.01)


# =============================================================================
# Rate Computation Tests
# =============================================================================


class TestRateComputation:
    """Test ClusterQualityMetrics rate computation."""

    def test_rates_from_counts(self) -> None:
        """Rates computed correctly from counts."""
        metrics = ClusterQualityMetrics(
            total_clusters=100,
            grounded_clusters=60,
            corrected_clusters=5,
            singleton_clusters=20,
        )

        metrics.compute_rates()

        assert metrics.grounding_rate == 0.6
        assert metrics.correction_rate == 0.05
        assert metrics.singleton_rate == 0.2

    def test_rates_zero_clusters(self) -> None:
        """Zero total clusters → rates are 0."""
        metrics = ClusterQualityMetrics(
            total_clusters=0,
            grounded_clusters=0,
            corrected_clusters=0,
            singleton_clusters=0,
        )

        metrics.compute_rates()

        assert metrics.grounding_rate == 0.0
        assert metrics.correction_rate == 0.0
        assert metrics.singleton_rate == 0.0


# =============================================================================
# Alert Tests
# =============================================================================


class TestAlerts:
    """Test ClusterQualityTracker alert system."""

    def test_alert_after_3_failures(self) -> None:
        """Alert triggered after 3 consecutive low silhouette scores."""
        tracker = ClusterQualityTracker()

        # 3 consecutive low scores
        m1 = ClusterQualityMetrics(silhouette_score=0.2)
        m2 = ClusterQualityMetrics(silhouette_score=0.25)
        m3 = ClusterQualityMetrics(silhouette_score=0.1)

        assert tracker.check_for_alert(m1) is None
        assert tracker.check_for_alert(m2) is None
        alert = tracker.check_for_alert(m3)

        assert alert is not None
        assert "CLUSTER_QUALITY_DEGRADED" in alert
        assert "0.3" in alert

    def test_no_alert_if_recovery(self) -> None:
        """No alert if quality recovers before 3 failures."""
        tracker = ClusterQualityTracker()

        # 2 low, then recovery
        m1 = ClusterQualityMetrics(silhouette_score=0.2)
        m2 = ClusterQualityMetrics(silhouette_score=0.25)
        m3 = ClusterQualityMetrics(silhouette_score=0.6)  # Recovery!

        tracker.check_for_alert(m1)
        tracker.check_for_alert(m2)
        alert = tracker.check_for_alert(m3)

        assert alert is None  # No alert due to recovery

    def test_no_alert_above_threshold(self) -> None:
        """No alert when silhouette consistently above threshold."""
        tracker = ClusterQualityTracker()

        for _ in range(5):
            m = ClusterQualityMetrics(silhouette_score=0.5)
            alert = tracker.check_for_alert(m)
            assert alert is None

    def test_reset_alert_state(self) -> None:
        """Reset clears alert tracking."""
        tracker = ClusterQualityTracker()

        # Add 2 low scores
        tracker.check_for_alert(ClusterQualityMetrics(silhouette_score=0.2))
        tracker.check_for_alert(ClusterQualityMetrics(silhouette_score=0.2))

        # Reset
        tracker.reset_alert_state()

        # Now need 3 more for alert
        tracker.check_for_alert(ClusterQualityMetrics(silhouette_score=0.2))
        tracker.check_for_alert(ClusterQualityMetrics(silhouette_score=0.2))
        alert = tracker.check_for_alert(ClusterQualityMetrics(silhouette_score=0.2))

        assert alert is not None


# =============================================================================
# Tuning Recommendation Tests
# =============================================================================


class TestTuningRecommendations:
    """Test ClusterQualityTracker tuning recommendations."""

    def test_high_singleton_rate_recommends_increase_min_samples(self) -> None:
        """High singleton rate → increase min_samples."""
        tracker = ClusterQualityTracker()
        metrics = ClusterQualityMetrics(singleton_rate=0.25, total_clusters=100)

        recs = tracker.get_tuning_recommendation(metrics)

        assert "min_samples" in recs
        assert "INCREASE" in recs["min_samples"]

    def test_low_singleton_rate_recommends_decrease_min_samples(self) -> None:
        """Low singleton rate → decrease min_samples."""
        tracker = ClusterQualityTracker()
        metrics = ClusterQualityMetrics(singleton_rate=0.02, total_clusters=100)

        recs = tracker.get_tuning_recommendation(metrics)

        assert "min_samples" in recs
        assert "DECREASE" in recs["min_samples"]

    def test_low_silhouette_high_singletons_recommends_increase_eps(self) -> None:
        """Low silhouette + high singletons → increase eps."""
        tracker = ClusterQualityTracker()
        metrics = ClusterQualityMetrics(silhouette_score=0.3, singleton_rate=0.25)

        recs = tracker.get_tuning_recommendation(metrics)

        assert "eps" in recs
        assert "INCREASE" in recs["eps"]

    def test_low_silhouette_low_singletons_recommends_decrease_eps(self) -> None:
        """Low silhouette + low singletons → decrease eps."""
        tracker = ClusterQualityTracker()
        metrics = ClusterQualityMetrics(silhouette_score=0.3, singleton_rate=0.10)

        recs = tracker.get_tuning_recommendation(metrics)

        assert "eps" in recs
        assert "DECREASE" in recs["eps"]

    def test_high_correction_rate_flags_review(self) -> None:
        """High correction rate → flag for review."""
        tracker = ClusterQualityTracker()
        metrics = ClusterQualityMetrics(correction_rate=0.10)

        recs = tracker.get_tuning_recommendation(metrics)

        assert "review" in recs


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Test ClusterQualityMetrics serialization."""

    def test_metrics_to_dict(self) -> None:
        """to_dict() includes all fields."""
        metrics = ClusterQualityMetrics(
            silhouette_score=0.6,
            grounding_rate=0.5,
            correction_rate=0.05,
            singleton_rate=0.15,
            composite_quality=0.7,
            total_clusters=100,
            grounded_clusters=50,
            corrected_clusters=5,
            singleton_clusters=15,
            space_id="test-space",
            cycle_id="cycle-123",
            computed_at=1234567890,
        )

        data = metrics.to_dict()

        assert data["silhouette_score"] == 0.6
        assert data["grounding_rate"] == 0.5
        assert data["correction_rate"] == 0.05
        assert data["singleton_rate"] == 0.15
        assert data["composite_quality"] == 0.7
        assert data["total_clusters"] == 100
        assert data["space_id"] == "test-space"


# =============================================================================
# Is Acceptable Tests
# =============================================================================


class TestIsAcceptable:
    """Test ClusterQualityMetrics is_acceptable property."""

    def test_is_acceptable_above_threshold(self) -> None:
        """Composite > 0.5 is acceptable."""
        metrics = ClusterQualityMetrics(composite_quality=0.6)
        assert metrics.is_acceptable is True

    def test_is_not_acceptable_below_threshold(self) -> None:
        """Composite <= 0.5 is not acceptable."""
        metrics = ClusterQualityMetrics(composite_quality=0.5)
        assert metrics.is_acceptable is False

        metrics2 = ClusterQualityMetrics(composite_quality=0.3)
        assert metrics2.is_acceptable is False


# =============================================================================
# Sync Compute Tests
# =============================================================================


class TestComputeFromR2Output:
    """Test ClusterQualityTracker.compute_from_r2_output()."""

    def test_compute_from_r2_output(self) -> None:
        """compute_from_r2_output populates all fields."""
        tracker = ClusterQualityTracker()
        r2_output = MockR2Output(
            batch_silhouette_score=0.6,
            cluster_count=10,
            noise_count=2,
        )

        metrics = tracker.compute_from_r2_output(
            space_id="test-space",
            r2_output=r2_output,
            grounded_clusters=6,
            corrected_clusters=1,
        )

        assert metrics.space_id == "test-space"
        assert metrics.silhouette_score == 0.6
        assert metrics.total_clusters == 12  # 10 + 2
        assert metrics.singleton_clusters == 2
        assert metrics.grounded_clusters == 6
        assert metrics.corrected_clusters == 1
        assert metrics.grounding_rate == pytest.approx(0.5, abs=0.01)
        assert metrics.correction_rate == pytest.approx(1 / 12, abs=0.01)
        assert metrics.composite_quality > 0.0
