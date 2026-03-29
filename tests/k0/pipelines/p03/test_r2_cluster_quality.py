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
    CHANNEL_COHERENCE_LIVE,
    WEIGHT_COHERENCE,
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
        """Mixed metrics compute correctly with live channels only."""
        metrics = ClusterQualityMetrics(
            silhouette_score=0.5,  # Moderate silhouette
            grounding_rate=0.5,  # Half grounded (dormant — excluded)
            correction_rate=0.1,  # 10% corrections (dormant — excluded)
            singleton_rate=0.2,  # 20% singletons
        )

        composite = metrics.compute_composite()

        # Only silhouette (0.40) + singleton (0.10) are live
        # normalized_silhouette = (0.5 + 1.0) / 2.0 = 0.75
        # composite = (0.40 * 0.75 + 0.10 * 0.80) / 0.50 = (0.30 + 0.08) / 0.50 = 0.76
        expected = (0.40 * 0.75 + 0.10 * 0.80) / 0.50
        assert composite == pytest.approx(expected, abs=0.01)

    def test_silhouette_normalization(self) -> None:
        """Silhouette normalized from [-1, 1] to [0, 1] with live channels."""
        # Silhouette of 0 should normalize to 0.5
        metrics = ClusterQualityMetrics(
            silhouette_score=0.0,
            grounding_rate=0.0,
            correction_rate=1.0,
            singleton_rate=1.0,  # (1 - 1.0) = 0.0
        )
        composite = metrics.compute_composite()

        # Live channels: silhouette (0.40) + singleton (0.10)
        # sil_norm = 0.5, singleton_val = 0.0
        # composite = (0.40 * 0.5 + 0.10 * 0.0) / 0.50 = 0.20 / 0.50 = 0.40
        expected = (0.40 * 0.5 + 0.10 * 0.0) / 0.50
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
        metrics = ClusterQualityMetrics(silhouette_score=0.2, singleton_rate=0.25)

        recs = tracker.get_tuning_recommendation(metrics)

        assert "eps" in recs
        assert "INCREASE" in recs["eps"]

    def test_low_silhouette_low_singletons_recommends_decrease_eps(self) -> None:
        """Low silhouette + low singletons → decrease eps."""
        tracker = ClusterQualityTracker()
        metrics = ClusterQualityMetrics(silhouette_score=0.2, singleton_rate=0.10)

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


# =============================================================================
# Issue 2.2.6 — Quality Regression Tests (real silhouette semantics)
# =============================================================================


class TestSilhouetteValidity:
    """Prove silhouette_valid propagation through the quality pipeline."""

    def test_invalid_silhouette_excluded_from_composite(self) -> None:
        """When silhouette_valid=False, composite uses only singleton channel."""
        metrics = ClusterQualityMetrics(
            silhouette_score=0.0,
            silhouette_valid=False,
            singleton_rate=0.10,
        )
        composite = metrics.compute_composite()

        # Only singleton channel is live and valid:
        # effective = 1.0 * (1 - 0.10) = 0.90
        assert composite == pytest.approx(0.90, abs=0.01)

    def test_valid_silhouette_included_in_composite(self) -> None:
        """When silhouette_valid=True, both silhouette and singleton contribute."""
        metrics = ClusterQualityMetrics(
            silhouette_score=0.27,  # real-world mean from POC-02/03
            silhouette_valid=True,
            singleton_rate=0.10,
        )
        composite = metrics.compute_composite()

        # silhouette weight=0.40, singleton weight=0.10
        # normalized_sil = (0.27 + 1) / 2 = 0.635
        # composite = (0.40 * 0.635 + 0.10 * 0.90) / 0.50 = (0.254 + 0.09) / 0.50 = 0.688
        assert 0.5 < composite < 0.85

    def test_negative_silhouette_produces_lower_composite(self) -> None:
        """Negative silhouette (poor clustering) reduces composite."""
        metrics_good = ClusterQualityMetrics(
            silhouette_score=0.30, silhouette_valid=True, singleton_rate=0.10
        )
        metrics_bad = ClusterQualityMetrics(
            silhouette_score=-0.20, silhouette_valid=True, singleton_rate=0.10
        )
        assert metrics_good.compute_composite() > metrics_bad.compute_composite()

    def test_all_noise_batch_silhouette_invalid(self) -> None:
        """All-noise clustering should use silhouette_valid=False."""
        metrics = ClusterQualityMetrics(
            silhouette_score=0.0,
            silhouette_valid=False,
            singleton_rate=1.0,  # 100% noise
        )
        composite = metrics.compute_composite()
        # singleton channel: (1 - 1.0) = 0.0
        assert composite == pytest.approx(0.0, abs=0.01)

    def test_one_cluster_batch_silhouette_invalid(self) -> None:
        """Single-cluster batch has silhouette_valid=False, non-zero composite."""
        metrics = ClusterQualityMetrics(
            silhouette_score=0.0,
            silhouette_valid=False,
            singleton_rate=0.0,  # all events in one cluster
        )
        composite = metrics.compute_composite()
        # singleton channel: (1 - 0.0) = 1.0
        assert composite == pytest.approx(1.0, abs=0.01)


class TestDormantChannelHonesty:
    """Issue 2.2.7: Prove dormant grounding/correction channels do not inflate quality."""

    def test_dormant_channels_excluded_from_composite(self) -> None:
        """Composite only uses silhouette + singleton when grounding/correction dormant."""
        from k0.modules.consolidation.algorithms.cluster_quality import (
            CHANNEL_CORRECTION_LIVE,
            CHANNEL_GROUNDING_LIVE,
        )

        # Verify dormant at module level
        assert not CHANNEL_GROUNDING_LIVE
        assert not CHANNEL_CORRECTION_LIVE

        # Even with grounding/correction set to specific values,
        # they should not affect composite
        metrics_with_grounding = ClusterQualityMetrics(
            silhouette_score=0.27,
            silhouette_valid=True,
            grounding_rate=0.80,
            correction_rate=0.50,
            singleton_rate=0.10,
        )
        metrics_without = ClusterQualityMetrics(
            silhouette_score=0.27,
            silhouette_valid=True,
            grounding_rate=0.0,
            correction_rate=0.0,
            singleton_rate=0.10,
        )

        c1 = metrics_with_grounding.compute_composite()
        c2 = metrics_without.compute_composite()

        # Should be identical since dormant channels are excluded
        assert c1 == pytest.approx(c2, abs=0.001)

    def test_to_dict_includes_channel_liveness(self) -> None:
        """Serialized metrics include channel_liveness map."""
        metrics = ClusterQualityMetrics()
        data = metrics.to_dict()

        assert "channel_liveness" in data
        assert data["channel_liveness"]["silhouette"] is True
        assert data["channel_liveness"]["grounding"] is False
        assert data["channel_liveness"]["correction"] is False
        assert data["channel_liveness"]["singleton"] is True

    def test_correction_zero_does_not_inflate(self) -> None:
        """Zero correction_rate no longer inflates composite (dormant = excluded)."""
        metrics = ClusterQualityMetrics(
            silhouette_score=0.0,
            silhouette_valid=False,
            correction_rate=0.0,  # Would add 0.20 if correction channel were live
            singleton_rate=0.10,
        )
        composite = metrics.compute_composite()

        # Only singleton contributes: (1 - 0.10) = 0.90
        # Without dormant channel fix, correction_rate=0 would add 0.20
        assert composite == pytest.approx(0.90, abs=0.01)


class TestAlertWithSilhouetteValidity:
    """Prove alert tracking respects silhouette_valid (Issue 2.2.3/2.2.6)."""

    def test_invalid_silhouette_skipped_in_alert_tracking(self) -> None:
        """Invalid silhouette cycles do not count toward alert accumulation."""
        tracker = ClusterQualityTracker()

        # 3 cycles with invalid silhouette (should not trigger alert)
        for _ in range(3):
            metrics = ClusterQualityMetrics(
                silhouette_score=0.0,
                silhouette_valid=False,
            )
            alert = tracker.check_for_alert(metrics)
            assert alert is None

        # 2 cycles with low but valid silhouette (not enough for 3 consecutive)
        for _ in range(2):
            metrics = ClusterQualityMetrics(
                silhouette_score=0.1,
                silhouette_valid=True,
            )
            alert = tracker.check_for_alert(metrics)
            assert alert is None

    def test_valid_low_silhouette_triggers_alert(self) -> None:
        """3 consecutive valid low-silhouette cycles trigger alert."""
        tracker = ClusterQualityTracker()

        for i in range(3):
            metrics = ClusterQualityMetrics(
                silhouette_score=0.1,
                silhouette_valid=True,
            )
            alert = tracker.check_for_alert(metrics)

        assert alert is not None
        assert "CLUSTER_QUALITY_DEGRADED" in alert


# =============================================================================
# Coherence Integration Tests (M4-RSCH-04)
# =============================================================================


class TestCoherenceQualityIntegration:
    """Prove coherence_score integration into composite quality formula."""

    def test_coherence_channel_live(self) -> None:
        """CHANNEL_COHERENCE_LIVE is True (M4-RSCH-04)."""
        assert CHANNEL_COHERENCE_LIVE is True

    def test_coherence_weight_value(self) -> None:
        """WEIGHT_COHERENCE = 0.40 (highest priority live channel)."""
        assert WEIGHT_COHERENCE == 0.40

    def test_coherence_valid_contributes_to_composite(self) -> None:
        """When coherence_valid=True, coherence raises composite vs without."""
        metrics_with = ClusterQualityMetrics(
            coherence_score=0.80,
            coherence_valid=True,
            silhouette_score=0.27,
            silhouette_valid=True,
            singleton_rate=0.10,
        )
        metrics_without = ClusterQualityMetrics(
            coherence_score=0.80,
            coherence_valid=False,  # excluded
            silhouette_score=0.27,
            silhouette_valid=True,
            singleton_rate=0.10,
        )

        c_with = metrics_with.compute_composite()
        c_without = metrics_without.compute_composite()

        # Both should be valid composites
        assert 0.0 < c_with <= 1.0
        assert 0.0 < c_without <= 1.0
        # They differ because coherence adds a channel
        assert c_with != pytest.approx(c_without, abs=0.001)

    def test_all_live_channels_formula(self) -> None:
        """All 3 live channels: coherence(0.40) + silhouette(0.40) + singleton(0.10)."""
        metrics = ClusterQualityMetrics(
            coherence_score=0.75,
            coherence_valid=True,
            silhouette_score=0.50,
            silhouette_valid=True,
            singleton_rate=0.20,
        )
        composite = metrics.compute_composite()

        # Weights: coherence=0.40, silhouette=0.40, singleton=0.10; total=0.90
        norm_sil = (0.50 + 1.0) / 2.0  # 0.75
        expected = (0.40 * 0.75 + 0.40 * norm_sil + 0.10 * 0.80) / 0.90
        assert composite == pytest.approx(expected, abs=0.001)

    def test_coherence_only_no_silhouette(self) -> None:
        """Coherence valid + silhouette invalid → coherence + singleton only."""
        metrics = ClusterQualityMetrics(
            coherence_score=0.60,
            coherence_valid=True,
            silhouette_score=0.0,
            silhouette_valid=False,
            singleton_rate=0.10,
        )
        composite = metrics.compute_composite()

        # Weights: coherence=0.40, singleton=0.10; total=0.50
        expected = (0.40 * 0.60 + 0.10 * 0.90) / 0.50
        assert composite == pytest.approx(expected, abs=0.001)

    def test_high_coherence_improves_quality(self) -> None:
        """Higher coherence → higher composite (monotonic)."""
        metrics_low = ClusterQualityMetrics(
            coherence_score=0.30,
            coherence_valid=True,
            silhouette_score=0.27,
            silhouette_valid=True,
            singleton_rate=0.10,
        )
        metrics_high = ClusterQualityMetrics(
            coherence_score=0.90,
            coherence_valid=True,
            silhouette_score=0.27,
            silhouette_valid=True,
            singleton_rate=0.10,
        )

        assert metrics_high.compute_composite() > metrics_low.compute_composite()

    def test_coherence_in_to_dict(self) -> None:
        """to_dict() includes coherence_score and coherence_valid."""
        metrics = ClusterQualityMetrics(
            coherence_score=0.65,
            coherence_valid=True,
        )
        data = metrics.to_dict()

        assert data["coherence_score"] == 0.65
        assert data["coherence_valid"] is True
        assert data["channel_liveness"]["coherence"] is True

    def test_coherence_default_invalid(self) -> None:
        """Default coherence_valid=False, coherence excluded from composite."""
        metrics = ClusterQualityMetrics(
            silhouette_score=0.27,
            silhouette_valid=True,
            singleton_rate=0.10,
        )
        # coherence_valid defaults to False
        assert metrics.coherence_valid is False

        composite = metrics.compute_composite()
        # Only silhouette + singleton (same as pre-coherence behavior)
        norm_sil = (0.27 + 1.0) / 2.0
        expected = (0.40 * norm_sil + 0.10 * 0.90) / 0.50
        assert composite == pytest.approx(expected, abs=0.001)
