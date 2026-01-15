"""
Tests for R1 phase metrics collection and Prometheus export.

Issue: M4 4.1.7 — R1 metrics: importance distribution, hebbian update counts
Issue: M4 4.1.8 — Integration tests for R1 metrics

Spec Reference: M4_EXECUTION.md Issue 4.1.7
Dossier Reference: Section 8.2 (Performance constraints)

Test Coverage:
- R1PhaseMetrics dataclass initialization
- Importance score recording and statistics
- Hebbian edge tracking (created, updated, pruned)
- Anti-Hebbian decrease counting
- Weight info tracking with source labels
- Performance threshold checks (10s warning, 18s error)
- Prometheus metric export format
- Metric merging for batch aggregation
"""

from __future__ import annotations

import pytest

from k0.pipelines.p03.observability import (
    DURATION_MS_BUCKETS,
    EDGE_WEIGHT_BUCKETS,
    IMPORTANCE_SCORE_BUCKETS,
    R1_ERROR_THRESHOLD_MS,
    R1_WARNING_THRESHOLD_MS,
    R1PhaseMetrics,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def empty_metrics() -> R1PhaseMetrics:
    """Create an empty R1PhaseMetrics instance."""
    return R1PhaseMetrics()


@pytest.fixture
def populated_metrics() -> R1PhaseMetrics:
    """Create an R1PhaseMetrics with sample data."""
    metrics = R1PhaseMetrics()
    # Add importance scores
    metrics.record_importance_scores([0.1, 0.3, 0.5, 0.7, 0.9])
    # Set weight info
    metrics.set_weight_info(
        weights={"emotional": 0.35, "recency": 0.25, "access": 0.20, "social": 0.20},
        sample_count=500,
        source="space",
    )
    # Add Hebbian edges
    metrics.record_hebbian_edge_created(0.6)
    metrics.record_hebbian_edge_created(0.7)
    metrics.record_hebbian_edge_updated(0.8)
    metrics.record_hebbian_edge_pruned()
    metrics.record_anti_hebbian_decrease()
    # Set timing
    metrics.r1_duration_ms = 1500.0
    metrics.importance_scoring_ms = 800.0
    metrics.hebbian_update_ms = 500.0
    return metrics


# =============================================================================
# TEST: INITIALIZATION AND DEFAULTS
# =============================================================================


class TestR1PhaseMetricsInitialization:
    """Tests for R1PhaseMetrics default initialization."""

    def test_default_importance_scores_empty(self, empty_metrics: R1PhaseMetrics):
        """Default importance_scores is empty list."""
        assert empty_metrics.importance_scores == []

    def test_default_importance_weight_values_empty(self, empty_metrics: R1PhaseMetrics):
        """Default importance_weight_values is empty dict."""
        assert empty_metrics.importance_weight_values == {}

    def test_default_importance_weight_samples_zero(self, empty_metrics: R1PhaseMetrics):
        """Default importance_weight_samples is 0."""
        assert empty_metrics.importance_weight_samples == 0

    def test_default_importance_weight_source_static(self, empty_metrics: R1PhaseMetrics):
        """Default importance_weight_source is 'static'."""
        assert empty_metrics.importance_weight_source == "static"

    def test_default_hebbian_edges_zero(self, empty_metrics: R1PhaseMetrics):
        """Default Hebbian edge counts are all 0."""
        assert empty_metrics.hebbian_edges_created == 0
        assert empty_metrics.hebbian_edges_updated == 0
        assert empty_metrics.hebbian_edges_pruned == 0

    def test_default_hebbian_weight_values_empty(self, empty_metrics: R1PhaseMetrics):
        """Default hebbian_weight_values is empty list."""
        assert empty_metrics.hebbian_weight_values == []

    def test_default_anti_hebbian_decreases_zero(self, empty_metrics: R1PhaseMetrics):
        """Default anti_hebbian_decreases is 0."""
        assert empty_metrics.anti_hebbian_decreases == 0

    def test_default_timing_zero(self, empty_metrics: R1PhaseMetrics):
        """Default timing metrics are 0.0."""
        assert empty_metrics.r1_duration_ms == 0.0
        assert empty_metrics.importance_scoring_ms == 0.0
        assert empty_metrics.hebbian_update_ms == 0.0


# =============================================================================
# TEST: IMPORTANCE SCORE RECORDING
# =============================================================================


class TestImportanceScoreRecording:
    """Tests for importance score recording."""

    def test_record_single_importance_score(self, empty_metrics: R1PhaseMetrics):
        """record_importance_score adds score to list."""
        empty_metrics.record_importance_score(0.5)
        assert empty_metrics.importance_scores == [0.5]

    def test_record_multiple_importance_scores(self, empty_metrics: R1PhaseMetrics):
        """record_importance_scores extends list with multiple scores."""
        empty_metrics.record_importance_scores([0.1, 0.2, 0.3])
        assert empty_metrics.importance_scores == [0.1, 0.2, 0.3]

    def test_record_importance_scores_cumulative(self, empty_metrics: R1PhaseMetrics):
        """Recording is cumulative across calls."""
        empty_metrics.record_importance_score(0.1)
        empty_metrics.record_importance_scores([0.2, 0.3])
        empty_metrics.record_importance_score(0.4)
        assert empty_metrics.importance_scores == [0.1, 0.2, 0.3, 0.4]

    def test_get_importance_score_stats_empty(self, empty_metrics: R1PhaseMetrics):
        """get_importance_score_stats returns zeros for empty list."""
        stats = empty_metrics.get_importance_score_stats()
        assert stats == {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0}

    def test_get_importance_score_stats_populated(self, populated_metrics: R1PhaseMetrics):
        """get_importance_score_stats returns correct values."""
        # Scores: [0.1, 0.3, 0.5, 0.7, 0.9]
        stats = populated_metrics.get_importance_score_stats()
        assert stats["count"] == 5
        assert stats["min"] == 0.1
        assert stats["max"] == 0.9
        assert abs(stats["mean"] - 0.5) < 0.001  # (0.1+0.3+0.5+0.7+0.9)/5 = 0.5
        assert stats["median"] == 0.5  # Middle value of sorted list

    def test_importance_score_stats_single_value(self, empty_metrics: R1PhaseMetrics):
        """Stats work correctly with single value."""
        empty_metrics.record_importance_score(0.42)
        stats = empty_metrics.get_importance_score_stats()
        assert stats["count"] == 1
        assert stats["min"] == 0.42
        assert stats["max"] == 0.42
        assert stats["mean"] == 0.42
        assert stats["median"] == 0.42


# =============================================================================
# TEST: WEIGHT INFO TRACKING
# =============================================================================


class TestWeightInfoTracking:
    """Tests for importance weight info tracking."""

    def test_set_weight_info(self, empty_metrics: R1PhaseMetrics):
        """set_weight_info correctly sets all weight fields."""
        weights = {"emotional": 0.40, "recency": 0.30, "access": 0.15, "social": 0.15}
        empty_metrics.set_weight_info(weights, sample_count=250, source="blended")

        assert empty_metrics.importance_weight_values == weights
        assert empty_metrics.importance_weight_samples == 250
        assert empty_metrics.importance_weight_source == "blended"

    def test_set_weight_info_copies_dict(self, empty_metrics: R1PhaseMetrics):
        """set_weight_info copies the weights dict (no mutation)."""
        weights = {"emotional": 0.35}
        empty_metrics.set_weight_info(weights, sample_count=100, source="space")

        # Modify original - should not affect stored value
        weights["emotional"] = 0.99
        assert empty_metrics.importance_weight_values["emotional"] == 0.35

    def test_weight_source_values(self, empty_metrics: R1PhaseMetrics):
        """Weight source can be any of the valid values."""
        for source in ("static", "space", "global", "blended"):
            empty_metrics.set_weight_info({}, sample_count=0, source=source)
            assert empty_metrics.importance_weight_source == source


# =============================================================================
# TEST: HEBBIAN EDGE TRACKING
# =============================================================================


class TestHebbianEdgeTracking:
    """Tests for Hebbian edge tracking."""

    def test_record_hebbian_edge_created(self, empty_metrics: R1PhaseMetrics):
        """record_hebbian_edge_created increments counter and records weight."""
        empty_metrics.record_hebbian_edge_created(0.6)
        assert empty_metrics.hebbian_edges_created == 1
        assert empty_metrics.hebbian_weight_values == [0.6]

    def test_record_hebbian_edge_updated(self, empty_metrics: R1PhaseMetrics):
        """record_hebbian_edge_updated increments counter and records weight."""
        empty_metrics.record_hebbian_edge_updated(0.75)
        assert empty_metrics.hebbian_edges_updated == 1
        assert empty_metrics.hebbian_weight_values == [0.75]

    def test_record_hebbian_edge_pruned(self, empty_metrics: R1PhaseMetrics):
        """record_hebbian_edge_pruned increments counter."""
        empty_metrics.record_hebbian_edge_pruned()
        empty_metrics.record_hebbian_edge_pruned()
        assert empty_metrics.hebbian_edges_pruned == 2

    def test_record_anti_hebbian_decrease(self, empty_metrics: R1PhaseMetrics):
        """record_anti_hebbian_decrease increments counter."""
        empty_metrics.record_anti_hebbian_decrease()
        empty_metrics.record_anti_hebbian_decrease()
        empty_metrics.record_anti_hebbian_decrease()
        assert empty_metrics.anti_hebbian_decreases == 3

    def test_get_hebbian_weight_stats_empty(self, empty_metrics: R1PhaseMetrics):
        """get_hebbian_weight_stats returns zeros for empty list."""
        stats = empty_metrics.get_hebbian_weight_stats()
        assert stats == {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0}

    def test_get_hebbian_weight_stats_populated(self, populated_metrics: R1PhaseMetrics):
        """get_hebbian_weight_stats returns correct values."""
        # Weights: [0.6, 0.7, 0.8] from 2 created + 1 updated
        stats = populated_metrics.get_hebbian_weight_stats()
        assert stats["count"] == 3
        assert stats["min"] == 0.6
        assert stats["max"] == 0.8
        assert abs(stats["mean"] - 0.7) < 0.001  # (0.6+0.7+0.8)/3 = 0.7


# =============================================================================
# TEST: PERFORMANCE THRESHOLDS
# =============================================================================


class TestPerformanceThresholds:
    """Tests for R1 performance threshold checking."""

    def test_threshold_constants(self):
        """Performance threshold constants are correct per dossier."""
        assert R1_WARNING_THRESHOLD_MS == 10_000  # 10 seconds
        assert R1_ERROR_THRESHOLD_MS == 18_000  # 18 seconds (5% of 360s cycle)

    def test_check_performance_below_warning(self, empty_metrics: R1PhaseMetrics):
        """Duration below 10s returns None (OK)."""
        empty_metrics.r1_duration_ms = 5000.0
        assert empty_metrics.check_performance_threshold() is None

    def test_check_performance_at_warning(self, empty_metrics: R1PhaseMetrics):
        """Duration at 10s returns 'warning'."""
        empty_metrics.r1_duration_ms = 10_000.0
        assert empty_metrics.check_performance_threshold() == "warning"

    def test_check_performance_between_thresholds(self, empty_metrics: R1PhaseMetrics):
        """Duration between 10s and 18s returns 'warning'."""
        empty_metrics.r1_duration_ms = 15_000.0
        assert empty_metrics.check_performance_threshold() == "warning"

    def test_check_performance_at_error(self, empty_metrics: R1PhaseMetrics):
        """Duration at 18s returns 'error'."""
        empty_metrics.r1_duration_ms = 18_000.0
        assert empty_metrics.check_performance_threshold() == "error"

    def test_check_performance_above_error(self, empty_metrics: R1PhaseMetrics):
        """Duration above 18s returns 'error'."""
        empty_metrics.r1_duration_ms = 25_000.0
        assert empty_metrics.check_performance_threshold() == "error"


# =============================================================================
# TEST: PROMETHEUS METRIC EXPORT
# =============================================================================


class TestPrometheusExport:
    """Tests for Prometheus metric export."""

    def test_bucket_constants(self):
        """Histogram bucket constants are correct per spec."""
        assert IMPORTANCE_SCORE_BUCKETS == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
        assert EDGE_WEIGHT_BUCKETS == (0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0)
        assert DURATION_MS_BUCKETS == (100, 500, 1000, 5000, 10000, 18000)

    def test_to_prometheus_metrics_returns_dict(self, populated_metrics: R1PhaseMetrics):
        """to_prometheus_metrics returns a dict."""
        result = populated_metrics.to_prometheus_metrics()
        assert isinstance(result, dict)

    def test_importance_score_distribution_metric(self, populated_metrics: R1PhaseMetrics):
        """p03_importance_score_distribution contains histogram data."""
        result = populated_metrics.to_prometheus_metrics()
        assert "p03_importance_score_distribution" in result
        dist = result["p03_importance_score_distribution"]
        assert "values" in dist
        assert "buckets" in dist
        assert dist["values"] == [0.1, 0.3, 0.5, 0.7, 0.9]
        assert dist["buckets"] == IMPORTANCE_SCORE_BUCKETS

    def test_importance_weight_gauges(self, populated_metrics: R1PhaseMetrics):
        """p03_importance_weight_{factor} gauges are present."""
        result = populated_metrics.to_prometheus_metrics()
        assert result["p03_importance_weight_emotional"] == 0.35
        assert result["p03_importance_weight_recency"] == 0.25
        assert result["p03_importance_weight_access"] == 0.20
        assert result["p03_importance_weight_social"] == 0.20

    def test_importance_weight_sample_count_metric(self, populated_metrics: R1PhaseMetrics):
        """p03_importance_weight_sample_count gauge is present."""
        result = populated_metrics.to_prometheus_metrics()
        assert result["p03_importance_weight_sample_count"] == 500

    def test_importance_weight_source_label(self, populated_metrics: R1PhaseMetrics):
        """p03_importance_weight_source label is present."""
        result = populated_metrics.to_prometheus_metrics()
        assert result["p03_importance_weight_source"] == "space"

    def test_hebbian_edge_counters(self, populated_metrics: R1PhaseMetrics):
        """p03_hebbian_edges_{created,updated,pruned} counters are present."""
        result = populated_metrics.to_prometheus_metrics()
        assert result["p03_hebbian_edges_created"] == 2
        assert result["p03_hebbian_edges_updated"] == 1
        assert result["p03_hebbian_edges_pruned"] == 1

    def test_hebbian_weight_distribution_metric(self, populated_metrics: R1PhaseMetrics):
        """p03_hebbian_weight_distribution contains histogram data."""
        result = populated_metrics.to_prometheus_metrics()
        assert "p03_hebbian_weight_distribution" in result
        dist = result["p03_hebbian_weight_distribution"]
        assert "values" in dist
        assert "buckets" in dist
        assert dist["values"] == [0.6, 0.7, 0.8]
        assert dist["buckets"] == EDGE_WEIGHT_BUCKETS

    def test_anti_hebbian_decreases_counter(self, populated_metrics: R1PhaseMetrics):
        """p03_anti_hebbian_decreases counter is present."""
        result = populated_metrics.to_prometheus_metrics()
        assert result["p03_anti_hebbian_decreases"] == 1

    def test_duration_histogram_metric(self, populated_metrics: R1PhaseMetrics):
        """p03_r1_duration_ms histogram is present."""
        result = populated_metrics.to_prometheus_metrics()
        assert "p03_r1_duration_ms" in result
        dur = result["p03_r1_duration_ms"]
        assert dur["value"] == 1500.0
        assert dur["buckets"] == DURATION_MS_BUCKETS

    def test_timing_sub_metrics(self, populated_metrics: R1PhaseMetrics):
        """Timing sub-metrics for importance scoring and hebbian are present."""
        result = populated_metrics.to_prometheus_metrics()
        assert result["p03_r1_importance_scoring_ms"] == 800.0
        assert result["p03_r1_hebbian_update_ms"] == 500.0

    def test_empty_metrics_export(self, empty_metrics: R1PhaseMetrics):
        """Empty metrics export correctly with default values."""
        result = empty_metrics.to_prometheus_metrics()
        assert result["p03_importance_score_distribution"]["values"] == []
        assert result["p03_importance_weight_emotional"] == 0.0
        assert result["p03_importance_weight_sample_count"] == 0
        assert result["p03_importance_weight_source"] == "static"
        assert result["p03_hebbian_edges_created"] == 0
        assert result["p03_anti_hebbian_decreases"] == 0


# =============================================================================
# TEST: TO_DICT SERIALIZATION
# =============================================================================


class TestToDictSerialization:
    """Tests for JSON-serializable dict export."""

    def test_to_dict_returns_dict(self, populated_metrics: R1PhaseMetrics):
        """to_dict returns a dictionary."""
        result = populated_metrics.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_contains_all_fields(self, populated_metrics: R1PhaseMetrics):
        """to_dict contains all expected fields."""
        result = populated_metrics.to_dict()
        expected_keys = {
            "importance_scores",
            "importance_weight_values",
            "importance_weight_samples",
            "importance_weight_source",
            "hebbian_edges_created",
            "hebbian_edges_updated",
            "hebbian_edges_pruned",
            "hebbian_weight_stats",
            "anti_hebbian_decreases",
            "r1_duration_ms",
            "importance_scoring_ms",
            "hebbian_update_ms",
            "performance_status",
        }
        assert set(result.keys()) == expected_keys

    def test_to_dict_importance_scores_are_stats(self, populated_metrics: R1PhaseMetrics):
        """importance_scores field contains stats, not raw list."""
        result = populated_metrics.to_dict()
        assert "count" in result["importance_scores"]
        assert "mean" in result["importance_scores"]

    def test_to_dict_performance_status(self, empty_metrics: R1PhaseMetrics):
        """performance_status reflects threshold check."""
        empty_metrics.r1_duration_ms = 5000.0
        assert empty_metrics.to_dict()["performance_status"] is None

        empty_metrics.r1_duration_ms = 12_000.0
        assert empty_metrics.to_dict()["performance_status"] == "warning"


# =============================================================================
# TEST: METRIC MERGING
# =============================================================================


class TestMetricMerging:
    """Tests for merging metrics across batches."""

    def test_merge_extends_importance_scores(self):
        """merge extends importance_scores list."""
        m1 = R1PhaseMetrics()
        m1.record_importance_scores([0.1, 0.2])
        m2 = R1PhaseMetrics()
        m2.record_importance_scores([0.3, 0.4])

        m1.merge(m2)
        assert m1.importance_scores == [0.1, 0.2, 0.3, 0.4]

    def test_merge_updates_weight_info(self):
        """merge takes weight info from other if set."""
        m1 = R1PhaseMetrics()
        m1.set_weight_info({"emotional": 0.3}, sample_count=100, source="static")
        m2 = R1PhaseMetrics()
        m2.set_weight_info({"emotional": 0.4}, sample_count=500, source="space")

        m1.merge(m2)
        assert m1.importance_weight_values == {"emotional": 0.4}
        assert m1.importance_weight_samples == 500
        assert m1.importance_weight_source == "space"

    def test_merge_sums_hebbian_counters(self):
        """merge sums Hebbian edge counters."""
        m1 = R1PhaseMetrics()
        m1.hebbian_edges_created = 5
        m1.hebbian_edges_updated = 10
        m1.hebbian_edges_pruned = 2
        m2 = R1PhaseMetrics()
        m2.hebbian_edges_created = 3
        m2.hebbian_edges_updated = 7
        m2.hebbian_edges_pruned = 1

        m1.merge(m2)
        assert m1.hebbian_edges_created == 8
        assert m1.hebbian_edges_updated == 17
        assert m1.hebbian_edges_pruned == 3

    def test_merge_extends_hebbian_weights(self):
        """merge extends hebbian_weight_values list."""
        m1 = R1PhaseMetrics()
        m1.hebbian_weight_values = [0.5, 0.6]
        m2 = R1PhaseMetrics()
        m2.hebbian_weight_values = [0.7, 0.8]

        m1.merge(m2)
        assert m1.hebbian_weight_values == [0.5, 0.6, 0.7, 0.8]

    def test_merge_sums_anti_hebbian(self):
        """merge sums anti_hebbian_decreases."""
        m1 = R1PhaseMetrics()
        m1.anti_hebbian_decreases = 5
        m2 = R1PhaseMetrics()
        m2.anti_hebbian_decreases = 3

        m1.merge(m2)
        assert m1.anti_hebbian_decreases == 8

    def test_merge_takes_max_duration(self):
        """merge takes max of r1_duration_ms."""
        m1 = R1PhaseMetrics()
        m1.r1_duration_ms = 1000.0
        m2 = R1PhaseMetrics()
        m2.r1_duration_ms = 1500.0

        m1.merge(m2)
        assert m1.r1_duration_ms == 1500.0

    def test_merge_sums_sub_timings(self):
        """merge sums importance_scoring_ms and hebbian_update_ms."""
        m1 = R1PhaseMetrics()
        m1.importance_scoring_ms = 500.0
        m1.hebbian_update_ms = 300.0
        m2 = R1PhaseMetrics()
        m2.importance_scoring_ms = 400.0
        m2.hebbian_update_ms = 200.0

        m1.merge(m2)
        assert m1.importance_scoring_ms == 900.0
        assert m1.hebbian_update_ms == 500.0


# =============================================================================
# TEST: INTEGRATION WITH P03 OBSERVABILITY CONTEXT
# =============================================================================


class TestR1MetricsIntegration:
    """Tests for R1PhaseMetrics integration patterns."""

    def test_metrics_json_serializable(self, populated_metrics: R1PhaseMetrics):
        """Metrics can be serialized to JSON."""
        import json

        result = populated_metrics.to_dict()
        # Should not raise
        json_str = json.dumps(result)
        assert json_str is not None

    def test_prometheus_metrics_json_serializable(self, populated_metrics: R1PhaseMetrics):
        """Prometheus metrics can be serialized to JSON."""
        import json

        result = populated_metrics.to_prometheus_metrics()
        json_str = json.dumps(result)
        assert json_str is not None

    def test_metric_values_within_bounds(self, populated_metrics: R1PhaseMetrics):
        """All importance scores are in valid range [0.0, 1.0]."""
        for score in populated_metrics.importance_scores:
            assert 0.0 <= score <= 1.0

    def test_hebbian_weights_within_bounds(self, populated_metrics: R1PhaseMetrics):
        """All Hebbian weights are in valid range [0.0, 1.0]."""
        for weight in populated_metrics.hebbian_weight_values:
            assert 0.0 <= weight <= 1.0

    def test_timing_metrics_non_negative(self, populated_metrics: R1PhaseMetrics):
        """All timing metrics are non-negative."""
        assert populated_metrics.r1_duration_ms >= 0.0
        assert populated_metrics.importance_scoring_ms >= 0.0
        assert populated_metrics.hebbian_update_ms >= 0.0
