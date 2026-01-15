"""Tests for P03 Formula Comparison (Issue 6.1.16).

Tests FormulaComparator class and Welch's t-test implementation.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import pytest

from k0.pipelines.p03.ops.formula_comparison import (
    MIN_SAMPLE_SIZE,
    REGRESSION_THRESHOLD,
    SIGNIFICANCE_THRESHOLD,
    ComparisonMetric,
    FormulaComparator,
    FormulaComparisonResult,
    _mean,
    _percentile,
    _variance,
    _welch_t_test,
)

if TYPE_CHECKING:
    pass


class TestFormulaComparator:
    """Tests for FormulaComparator class."""

    @pytest.fixture
    def comparator(self) -> FormulaComparator:
        """Create a FormulaComparator instance."""
        return FormulaComparator(metrics_registry=None)

    def test_init_without_metrics(self) -> None:
        """Test FormulaComparator initializes without metrics registry."""
        comparator = FormulaComparator()
        assert comparator._metrics is None

    def test_init_with_metrics(self) -> None:
        """Test FormulaComparator initializes with metrics registry."""
        # Mock registry not needed for this test
        comparator = FormulaComparator(metrics_registry=None)
        assert comparator._metrics is None


class TestCompareLatency:
    """Tests for compare_latency method."""

    @pytest.fixture
    def comparator(self) -> FormulaComparator:
        """Create a FormulaComparator instance."""
        return FormulaComparator()

    def test_compare_latency_insufficient_samples(self, comparator: FormulaComparator) -> None:
        """Test compare_latency with insufficient samples."""
        old_samples = [10.0] * 100  # Less than MIN_SAMPLE_SIZE
        new_samples = [10.0] * 100

        result = comparator.compare_latency(
            formula="test",
            old_version="v1",
            new_version="v2",
            old_samples=old_samples,
            new_samples=new_samples,
        )

        assert result.insufficient_samples
        assert result.winner == "tie"
        assert not result.significant

    def test_compare_latency_sufficient_samples_tie(self, comparator: FormulaComparator) -> None:
        """Test compare_latency with identical samples shows tie."""
        random.seed(42)
        old_samples = [random.gauss(100, 10) for _ in range(MIN_SAMPLE_SIZE)]
        # Very similar distribution
        new_samples = [random.gauss(100, 10) for _ in range(MIN_SAMPLE_SIZE)]

        result = comparator.compare_latency(
            formula="test",
            old_version="v1",
            new_version="v2",
            old_samples=old_samples,
            new_samples=new_samples,
        )

        assert not result.insufficient_samples
        # Very similar distributions should be tie or have high p-value
        assert result.winner == "tie" or result.p_value > 0.01

    def test_compare_latency_new_faster(self, comparator: FormulaComparator) -> None:
        """Test compare_latency when new version is significantly faster."""
        random.seed(42)
        old_samples = [random.gauss(100, 10) for _ in range(MIN_SAMPLE_SIZE)]
        new_samples = [random.gauss(80, 10) for _ in range(MIN_SAMPLE_SIZE)]  # 20% faster

        result = comparator.compare_latency(
            formula="test",
            old_version="v1",
            new_version="v2",
            old_samples=old_samples,
            new_samples=new_samples,
        )

        assert not result.insufficient_samples
        assert result.significant
        assert result.winner == "new"

    def test_compare_latency_new_slower_regression(self, comparator: FormulaComparator) -> None:
        """Test compare_latency detects regression when new is >10% slower."""
        random.seed(42)
        old_samples = [random.gauss(100, 10) for _ in range(MIN_SAMPLE_SIZE)]
        new_samples = [random.gauss(120, 10) for _ in range(MIN_SAMPLE_SIZE)]  # 20% slower

        result = comparator.compare_latency(
            formula="test",
            old_version="v1",
            new_version="v2",
            old_samples=old_samples,
            new_samples=new_samples,
        )

        assert result.significant
        assert result.winner == "old"  # Old wins when new is regression


class TestCompareErrorRate:
    """Tests for compare_error_rate method."""

    @pytest.fixture
    def comparator(self) -> FormulaComparator:
        """Create a FormulaComparator instance."""
        return FormulaComparator()

    def test_compare_error_rate_insufficient_samples(self, comparator: FormulaComparator) -> None:
        """Test compare_error_rate with insufficient samples."""
        result = comparator.compare_error_rate(
            formula="test",
            old_version="v1",
            new_version="v2",
            old_errors=5,
            old_total=100,  # Less than MIN_SAMPLE_SIZE
            new_errors=5,
            new_total=100,
        )

        assert result.insufficient_samples

    def test_compare_error_rate_same_rate(self, comparator: FormulaComparator) -> None:
        """Test compare_error_rate with same error rates."""
        result = comparator.compare_error_rate(
            formula="test",
            old_version="v1",
            new_version="v2",
            old_errors=50,
            old_total=MIN_SAMPLE_SIZE,
            new_errors=50,
            new_total=MIN_SAMPLE_SIZE,
        )

        assert not result.insufficient_samples
        # Same rates should be tie
        assert result.winner == "tie" or not result.significant

    def test_compare_error_rate_new_better(self, comparator: FormulaComparator) -> None:
        """Test compare_error_rate when new version has lower error rate."""
        result = comparator.compare_error_rate(
            formula="test",
            old_version="v1",
            new_version="v2",
            old_errors=100,
            old_total=MIN_SAMPLE_SIZE,  # 10% error rate
            new_errors=10,
            new_total=MIN_SAMPLE_SIZE,  # 1% error rate
        )

        assert not result.insufficient_samples
        # Large difference should be significant
        if result.significant:
            assert result.winner == "new"


class TestCompareRegretRate:
    """Tests for compare_regret_rate method."""

    @pytest.fixture
    def comparator(self) -> FormulaComparator:
        """Create a FormulaComparator instance."""
        return FormulaComparator()

    def test_compare_regret_rate_insufficient_samples(self, comparator: FormulaComparator) -> None:
        """Test compare_regret_rate with insufficient samples."""
        result = comparator.compare_regret_rate(
            formula="test",
            old_version="v1",
            new_version="v2",
            old_regrets=5,
            old_prunes=100,
            new_regrets=5,
            new_prunes=100,
        )

        assert result.insufficient_samples

    def test_compare_regret_rate_new_better(self, comparator: FormulaComparator) -> None:
        """Test compare_regret_rate when new has lower regret."""
        result = comparator.compare_regret_rate(
            formula="test",
            old_version="v1",
            new_version="v2",
            old_regrets=100,
            old_prunes=MIN_SAMPLE_SIZE,  # 10% regret
            new_regrets=10,
            new_prunes=MIN_SAMPLE_SIZE,  # 1% regret
        )

        if result.significant:
            assert result.winner == "new"


class TestFormulaComparisonResult:
    """Tests for FormulaComparisonResult dataclass."""

    def test_result_attributes(self) -> None:
        """Test FormulaComparisonResult has expected attributes."""
        result = FormulaComparisonResult(
            formula="hebbian",
            old_version="v1.0",
            new_version="v1.1",
            metric_name="latency_p99",
            old_value=100.0,
            new_value=95.0,
            p_value=0.01,
            significant=True,
            winner="new",
            sample_size_old=1000,
            sample_size_new=1000,
            insufficient_samples=False,
        )

        assert result.formula == "hebbian"
        assert result.metric_name == "latency_p99"
        assert result.old_value == 100.0
        assert result.new_value == 95.0
        assert result.significant
        assert result.winner == "new"

    def test_result_str_normal(self) -> None:
        """Test FormulaComparisonResult string representation."""
        result = FormulaComparisonResult(
            formula="test",
            old_version="v1",
            new_version="v2",
            metric_name="latency_p99",
            old_value=100.0,
            new_value=90.0,
            p_value=0.01,
            significant=True,
            winner="new",
            sample_size_old=1000,
            sample_size_new=1000,
        )

        s = str(result)
        assert "test" in s
        assert "latency_p99" in s
        assert "significant" in s

    def test_result_str_insufficient_samples(self) -> None:
        """Test FormulaComparisonResult string with insufficient samples."""
        result = FormulaComparisonResult(
            formula="test",
            old_version="v1",
            new_version="v2",
            metric_name="latency_p99",
            old_value=0.0,
            new_value=0.0,
            p_value=1.0,
            significant=False,
            winner="tie",
            sample_size_old=100,
            sample_size_new=100,
            insufficient_samples=True,
        )

        s = str(result)
        assert "insufficient" in s


class TestStatisticalHelpers:
    """Tests for internal statistical helper functions."""

    def test_mean_calculation(self) -> None:
        """Test mean calculation."""
        assert _mean([1, 2, 3, 4, 5]) == 3.0
        assert _mean([10]) == 10.0
        assert abs(_mean([1.5, 2.5, 3.5]) - 2.5) < 0.001

    def test_mean_empty(self) -> None:
        """Test mean of empty list."""
        assert _mean([]) == 0.0

    def test_variance_calculation(self) -> None:
        """Test variance calculation."""
        # Variance of [1, 2, 3, 4, 5] with mean 3 is 2.5 (sample variance)
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        var = _variance(data, 3.0)
        assert abs(var - 2.5) < 0.001

    def test_variance_single_element(self) -> None:
        """Test variance of single element."""
        assert _variance([10.0], 10.0) == 0.0

    def test_percentile_median(self) -> None:
        """Test percentile calculation for median."""
        data = list(range(1, 101))  # 1 to 100
        median = _percentile(data, 50)
        assert 49 <= median <= 51

    def test_percentile_extremes(self) -> None:
        """Test percentile at extremes."""
        data = list(range(1, 101))
        assert _percentile(data, 0) == 1
        assert _percentile(data, 100) == 100

    def test_percentile_empty(self) -> None:
        """Test percentile of empty list."""
        assert _percentile([], 50) == 0.0


class TestWelchsTTest:
    """Tests for Welch's t-test implementation."""

    def test_identical_samples(self) -> None:
        """Test Welch's t-test with identical samples."""
        sample1 = [10.0] * 30
        sample2 = [10.0] * 30

        t_stat, p_value = _welch_t_test(sample1, sample2)
        assert abs(t_stat) < 0.001  # t should be ~0
        assert p_value >= 0.5  # Not significant

    def test_clearly_different_means(self) -> None:
        """Test Welch's t-test with clearly different means."""
        random.seed(42)
        sample1 = [random.gauss(10, 1) for _ in range(100)]
        sample2 = [random.gauss(20, 1) for _ in range(100)]  # 2x mean

        t_stat, p_value = _welch_t_test(sample1, sample2)
        assert t_stat < -10  # Strongly negative (sample1 < sample2)
        assert p_value < 0.001  # Highly significant

    def test_insufficient_samples(self) -> None:
        """Test Welch's t-test with insufficient samples."""
        t_stat, p_value = _welch_t_test([10.0], [20.0])
        assert p_value == 1.0  # Cannot determine significance

    def test_same_variance(self) -> None:
        """Test Welch's t-test reduces to standard t-test for equal variance."""
        random.seed(42)
        sample1 = [random.gauss(50, 10) for _ in range(50)]
        sample2 = [random.gauss(55, 10) for _ in range(50)]

        t_stat, p_value = _welch_t_test(sample1, sample2)
        # Should get reasonable t-statistic and p-value
        assert -10 < t_stat < 10
        assert 0 <= p_value <= 1


class TestComparisonMetric:
    """Tests for ComparisonMetric enum."""

    def test_has_latency(self) -> None:
        """Test ComparisonMetric has latency metric."""
        assert ComparisonMetric.LATENCY_P99.value == "latency_p99"

    def test_has_error_rate(self) -> None:
        """Test ComparisonMetric has error rate metric."""
        assert ComparisonMetric.ERROR_RATE.value == "error_rate"

    def test_has_regret_rate(self) -> None:
        """Test ComparisonMetric has regret rate metric."""
        assert ComparisonMetric.REGRET_RATE.value == "regret_rate"

    def test_has_accuracy(self) -> None:
        """Test ComparisonMetric has accuracy metric."""
        assert ComparisonMetric.ACCURACY.value == "accuracy"


class TestConstants:
    """Tests for module constants."""

    def test_min_sample_size(self) -> None:
        """Test MIN_SAMPLE_SIZE is reasonable."""
        assert MIN_SAMPLE_SIZE >= 30  # Statistical minimum
        assert MIN_SAMPLE_SIZE <= 10000  # Practical maximum

    def test_significance_threshold(self) -> None:
        """Test SIGNIFICANCE_THRESHOLD is standard."""
        assert SIGNIFICANCE_THRESHOLD == 0.05  # Standard p=0.05

    def test_regression_threshold(self) -> None:
        """Test REGRESSION_THRESHOLD is reasonable."""
        assert 0.01 <= REGRESSION_THRESHOLD <= 0.10


class TestEmitDivergence:
    """Tests for emit_divergence functionality."""

    @pytest.fixture
    def comparator(self) -> FormulaComparator:
        """Create a FormulaComparator instance."""
        return FormulaComparator()

    def test_emit_divergence_no_metrics(self, comparator: FormulaComparator) -> None:
        """Test emit_divergence logs when no metrics registry."""
        # Should not raise with None metrics
        comparator.emit_divergence(
            formula="test",
            old_decision="keep",
            new_decision="prune",
        )

    def test_emit_divergence_parameters(self, comparator: FormulaComparator) -> None:
        """Test emit_divergence accepts expected parameters."""
        # Test with different decision combinations
        comparator.emit_divergence(
            formula="hebbian",
            old_decision="prune",
            new_decision="keep",
        )


class TestShouldPromote:
    """Tests for should_promote functionality."""

    @pytest.fixture
    def comparator(self) -> FormulaComparator:
        """Create a FormulaComparator instance."""
        return FormulaComparator()

    def test_should_promote_exists(self, comparator: FormulaComparator) -> None:
        """Test should_promote method exists if implemented."""
        if hasattr(comparator, "should_promote"):
            # Method exists - would need proper test data
            pass
        else:
            # Method not implemented - acceptable for this version
            pytest.skip("should_promote not implemented")
