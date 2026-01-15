"""P03 Formula Comparison — Version comparison for shadow mode and canary rollout.

This module provides statistical comparison of formula performance between
versions to enable data-driven rollout decisions.

Issue Reference: M6_EXECUTION.md Issue 6.1.16
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8.7

Formula Comparison Metrics:
    - Memory retrieval accuracy: New >= Old
    - Decay calibration error: New < Old by > 5%
    - Processing time: New <= Old x 1.1
    - Edge case handling: No regressions

Statistical Requirements:
    - p < 0.05 (95% confidence) before declaring winner
    - Welch's t-test for unequal variances
    - Minimum sample size: 1000 events per version

Usage:
    comparator = FormulaComparator(metrics_registry)

    # Compare latency between versions
    result = comparator.compare_latency(
        formula="hebbian",
        old_version="v1",
        new_version="v2",
        old_samples=[...],
        new_samples=[...],
    )

    # Check if new version is winner
    if result.winner == "new" and result.significant:
        promote_formula(formula, new_version)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Literal, Sequence

if TYPE_CHECKING:
    from k0.pipelines.p03.ops.metrics import P03MetricsRegistry

__all__ = [
    "FormulaComparator",
    "FormulaComparisonResult",
    "ComparisonMetric",
    "MIN_SAMPLE_SIZE",
    "SIGNIFICANCE_THRESHOLD",
    "REGRESSION_THRESHOLD",
]

LOGGER = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Minimum samples required per version for statistical significance
MIN_SAMPLE_SIZE = 1000

# p-value threshold for declaring statistical significance
SIGNIFICANCE_THRESHOLD = 0.05

# Threshold for detecting regressions (5% worse)
REGRESSION_THRESHOLD = 0.05

# Maximum acceptable latency increase (10%)
MAX_LATENCY_INCREASE = 1.10


# =============================================================================
# ENUMS
# =============================================================================


class ComparisonMetric(str, Enum):
    """Metrics available for formula comparison."""

    LATENCY_P99 = "latency_p99"
    ERROR_RATE = "error_rate"
    ACCURACY = "accuracy"
    REGRET_RATE = "regret_rate"
    DIVERGENCE_COUNT = "divergence_count"


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True, slots=True)
class FormulaComparisonResult:
    """Result of comparing two formula versions.

    Attributes:
        formula: Name of the formula being compared.
        old_version: Version identifier for baseline.
        new_version: Version identifier for candidate.
        metric_name: Which metric was compared.
        old_value: Computed value for old version.
        new_value: Computed value for new version.
        p_value: Statistical p-value from t-test.
        significant: Whether difference is statistically significant.
        winner: Which version won ("old", "new", or "tie").
        sample_size_old: Number of samples for old version.
        sample_size_new: Number of samples for new version.
        insufficient_samples: True if either version has < MIN_SAMPLE_SIZE.
    """

    formula: str
    old_version: str
    new_version: str
    metric_name: str
    old_value: float
    new_value: float
    p_value: float
    significant: bool
    winner: Literal["old", "new", "tie"]
    sample_size_old: int
    sample_size_new: int
    insufficient_samples: bool = False

    def __str__(self) -> str:
        if self.insufficient_samples:
            return (
                f"{self.formula} {self.metric_name}: insufficient samples "
                f"(old={self.sample_size_old}, new={self.sample_size_new}, "
                f"min={MIN_SAMPLE_SIZE})"
            )
        sig_str = "significant" if self.significant else "not significant"
        return (
            f"{self.formula} {self.metric_name}: "
            f"old={self.old_value:.4f}, new={self.new_value:.4f}, "
            f"p={self.p_value:.4f} ({sig_str}), winner={self.winner}"
        )


# =============================================================================
# WELCH'S T-TEST IMPLEMENTATION
# =============================================================================


def _mean(samples: Sequence[float]) -> float:
    """Compute arithmetic mean."""
    if not samples:
        return 0.0
    return sum(samples) / len(samples)


def _variance(samples: Sequence[float], mean: float) -> float:
    """Compute sample variance."""
    n = len(samples)
    if n < 2:
        return 0.0
    return sum((x - mean) ** 2 for x in samples) / (n - 1)


def _percentile(samples: Sequence[float], pct: float) -> float:
    """Compute percentile value (0-100 scale)."""
    if not samples:
        return 0.0
    sorted_samples = sorted(samples)
    n = len(sorted_samples)
    k = (n - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_samples[int(k)]
    return sorted_samples[int(f)] * (c - k) + sorted_samples[int(c)] * (k - f)


def _welch_t_test(
    samples1: Sequence[float],
    samples2: Sequence[float],
) -> tuple[float, float]:
    """Perform Welch's t-test for unequal variances.

    Returns:
        Tuple of (t_statistic, p_value).
        p_value is two-tailed.

    Note:
        This is a simplified implementation. For production use,
        consider scipy.stats.ttest_ind(equal_var=False).
    """
    n1 = len(samples1)
    n2 = len(samples2)

    if n1 < 2 or n2 < 2:
        return 0.0, 1.0

    mean1 = _mean(samples1)
    mean2 = _mean(samples2)
    var1 = _variance(samples1, mean1)
    var2 = _variance(samples2, mean2)

    # Avoid division by zero
    if var1 == 0 and var2 == 0:
        return 0.0, 1.0 if mean1 == mean2 else 0.0

    # Welch's t-statistic
    se1 = var1 / n1
    se2 = var2 / n2
    se_diff = math.sqrt(se1 + se2)

    if se_diff == 0:
        return 0.0, 1.0

    t_stat = (mean1 - mean2) / se_diff

    # Welch-Satterthwaite degrees of freedom
    if se1 + se2 == 0:
        df = n1 + n2 - 2
    else:
        df_num = (se1 + se2) ** 2
        df_denom = (se1**2 / (n1 - 1)) + (se2**2 / (n2 - 1))
        df = df_num / df_denom if df_denom > 0 else n1 + n2 - 2

    # Approximate p-value using t-distribution
    # For large df, t-distribution approaches normal
    # This is a simplified approximation
    p_value = _approx_t_pvalue(abs(t_stat), df)

    return t_stat, p_value


def _approx_t_pvalue(t_abs: float, df: float) -> float:
    """Approximate two-tailed p-value from t-distribution.

    Uses a simplified approximation suitable for df > 30.
    For smaller df, consider using scipy.stats.t.sf().
    """
    if df <= 0:
        return 1.0

    # For large df, use normal approximation
    if df > 100:
        # Standard normal CDF approximation
        z = t_abs
        # Abramowitz and Stegun approximation
        p = 0.5 * math.erfc(z / math.sqrt(2))
        return 2 * p  # Two-tailed

    # For moderate df, use a rough t-distribution approximation
    # This is less accurate but avoids scipy dependency
    # Adjust z for t-distribution
    z = t_abs * (1 - 1 / (4 * df))
    p = 0.5 * math.erfc(z / math.sqrt(2))
    return 2 * p


# =============================================================================
# FORMULA COMPARATOR
# =============================================================================


class FormulaComparator:
    """Compare formula performance across versions.

    Uses statistical tests to determine if new formula version is
    significantly better, worse, or equivalent to baseline.

    Thread Safety:
        Thread-safe. Uses immutable comparison logic.
    """

    def __init__(self, metrics_registry: P03MetricsRegistry | None = None) -> None:
        """Initialize formula comparator.

        Args:
            metrics_registry: Optional P03MetricsRegistry for emitting metrics.
        """
        self._metrics = metrics_registry

    def compare_latency(
        self,
        formula: str,
        old_version: str,
        new_version: str,
        old_samples: Sequence[float],
        new_samples: Sequence[float],
        percentile: float = 99,
    ) -> FormulaComparisonResult:
        """Compare latency between formula versions.

        Lower latency is better. New version wins if:
        - Latency is statistically significantly lower, OR
        - Latency is within 10% of old version (not a regression)

        Args:
            formula: Formula name (e.g., "hebbian", "importance").
            old_version: Baseline version identifier.
            new_version: Candidate version identifier.
            old_samples: Latency samples (ms) for old version.
            new_samples: Latency samples (ms) for new version.
            percentile: Which percentile to compare (default p99).

        Returns:
            FormulaComparisonResult with comparison details.
        """
        # Check sample sizes
        if len(old_samples) < MIN_SAMPLE_SIZE or len(new_samples) < MIN_SAMPLE_SIZE:
            return FormulaComparisonResult(
                formula=formula,
                old_version=old_version,
                new_version=new_version,
                metric_name=f"latency_p{int(percentile)}",
                old_value=0.0,
                new_value=0.0,
                p_value=1.0,
                significant=False,
                winner="tie",
                sample_size_old=len(old_samples),
                sample_size_new=len(new_samples),
                insufficient_samples=True,
            )

        # Compute percentiles
        old_pct = _percentile(old_samples, percentile)
        new_pct = _percentile(new_samples, percentile)

        # Perform Welch's t-test
        _, p_value = _welch_t_test(old_samples, new_samples)

        significant = p_value < SIGNIFICANCE_THRESHOLD

        # Determine winner (lower is better for latency)
        if not significant:
            winner: Literal["old", "new", "tie"] = "tie"
        elif new_pct < old_pct:
            winner = "new"
        elif new_pct > old_pct * MAX_LATENCY_INCREASE:
            # New is more than 10% slower - regression
            winner = "old"
        else:
            winner = "tie"

        result = FormulaComparisonResult(
            formula=formula,
            old_version=old_version,
            new_version=new_version,
            metric_name=f"latency_p{int(percentile)}",
            old_value=old_pct,
            new_value=new_pct,
            p_value=p_value,
            significant=significant,
            winner=winner,
            sample_size_old=len(old_samples),
            sample_size_new=len(new_samples),
        )

        LOGGER.debug("Latency comparison: %s", result)
        return result

    def compare_error_rate(
        self,
        formula: str,
        old_version: str,
        new_version: str,
        old_errors: int,
        old_total: int,
        new_errors: int,
        new_total: int,
    ) -> FormulaComparisonResult:
        """Compare error rates between formula versions.

        Lower error rate is better. New version wins if error rate
        is statistically significantly lower.

        Args:
            formula: Formula name.
            old_version: Baseline version identifier.
            new_version: Candidate version identifier.
            old_errors: Error count for old version.
            old_total: Total executions for old version.
            new_errors: Error count for new version.
            new_total: Total executions for new version.

        Returns:
            FormulaComparisonResult with comparison details.
        """
        # Check sample sizes
        if old_total < MIN_SAMPLE_SIZE or new_total < MIN_SAMPLE_SIZE:
            return FormulaComparisonResult(
                formula=formula,
                old_version=old_version,
                new_version=new_version,
                metric_name="error_rate",
                old_value=0.0,
                new_value=0.0,
                p_value=1.0,
                significant=False,
                winner="tie",
                sample_size_old=old_total,
                sample_size_new=new_total,
                insufficient_samples=True,
            )

        old_rate = old_errors / old_total if old_total > 0 else 0.0
        new_rate = new_errors / new_total if new_total > 0 else 0.0

        # Create binary samples for t-test (1 = error, 0 = success)
        old_samples = [1.0] * old_errors + [0.0] * (old_total - old_errors)
        new_samples = [1.0] * new_errors + [0.0] * (new_total - new_errors)

        _, p_value = _welch_t_test(old_samples, new_samples)
        significant = p_value < SIGNIFICANCE_THRESHOLD

        # Lower error rate is better
        if not significant:
            winner: Literal["old", "new", "tie"] = "tie"
        elif new_rate < old_rate:
            winner = "new"
        else:
            winner = "old"

        return FormulaComparisonResult(
            formula=formula,
            old_version=old_version,
            new_version=new_version,
            metric_name="error_rate",
            old_value=old_rate,
            new_value=new_rate,
            p_value=p_value,
            significant=significant,
            winner=winner,
            sample_size_old=old_total,
            sample_size_new=new_total,
        )

    def compare_regret_rate(
        self,
        formula: str,
        old_version: str,
        new_version: str,
        old_regrets: int,
        old_prunes: int,
        new_regrets: int,
        new_prunes: int,
    ) -> FormulaComparisonResult:
        """Compare regret rates (prune regrets / total prunes).

        Lower regret rate is better. Measures decay calibration quality.
        New version wins if regret rate is > 5% lower.

        Args:
            formula: Formula name.
            old_version: Baseline version identifier.
            new_version: Candidate version identifier.
            old_regrets: Regret events for old version.
            old_prunes: Total prune operations for old version.
            new_regrets: Regret events for new version.
            new_prunes: Total prune operations for new version.

        Returns:
            FormulaComparisonResult with comparison details.
        """
        if old_prunes < MIN_SAMPLE_SIZE or new_prunes < MIN_SAMPLE_SIZE:
            return FormulaComparisonResult(
                formula=formula,
                old_version=old_version,
                new_version=new_version,
                metric_name="regret_rate",
                old_value=0.0,
                new_value=0.0,
                p_value=1.0,
                significant=False,
                winner="tie",
                sample_size_old=old_prunes,
                sample_size_new=new_prunes,
                insufficient_samples=True,
            )

        old_rate = old_regrets / old_prunes if old_prunes > 0 else 0.0
        new_rate = new_regrets / new_prunes if new_prunes > 0 else 0.0

        # Create binary samples
        old_samples = [1.0] * old_regrets + [0.0] * (old_prunes - old_regrets)
        new_samples = [1.0] * new_regrets + [0.0] * (new_prunes - new_regrets)

        _, p_value = _welch_t_test(old_samples, new_samples)
        significant = p_value < SIGNIFICANCE_THRESHOLD

        # New wins if regret rate is > 5% lower (relative improvement)
        improvement = (old_rate - new_rate) / old_rate if old_rate > 0 else 0.0

        if not significant:
            winner: Literal["old", "new", "tie"] = "tie"
        elif improvement > REGRESSION_THRESHOLD:
            winner = "new"
        elif improvement < -REGRESSION_THRESHOLD:
            winner = "old"
        else:
            winner = "tie"

        return FormulaComparisonResult(
            formula=formula,
            old_version=old_version,
            new_version=new_version,
            metric_name="regret_rate",
            old_value=old_rate,
            new_value=new_rate,
            p_value=p_value,
            significant=significant,
            winner=winner,
            sample_size_old=old_prunes,
            sample_size_new=new_prunes,
        )

    def emit_divergence(
        self,
        formula: str,
        old_decision: str,
        new_decision: str,
    ) -> None:
        """Record when formula versions produce different decisions.

        Args:
            formula: Formula name.
            old_decision: Decision from old version.
            new_decision: Decision from new version.
        """
        if self._metrics is None:
            LOGGER.debug(
                "Formula divergence (no metrics): %s old=%s new=%s",
                formula,
                old_decision,
                new_decision,
            )
            return

        self._metrics.emit(
            "p03_formula_comparison_divergence",
            1,
            formula=formula,
            old_decision=old_decision,
            new_decision=new_decision,
        )

    def should_promote(
        self,
        results: Sequence[FormulaComparisonResult],
        require_all_metrics: bool = False,
    ) -> tuple[bool, str]:
        """Determine if new version should be promoted based on comparison results.

        Promotion criteria:
        - No metric shows new version as significantly worse
        - At least one metric shows new version as significantly better
        - All metrics have sufficient sample sizes

        Args:
            results: Sequence of comparison results for different metrics.
            require_all_metrics: If True, all results must show new as winner.

        Returns:
            Tuple of (should_promote, reason).
        """
        if not results:
            return False, "No comparison results provided"

        # Check for insufficient samples
        insufficient = [r for r in results if r.insufficient_samples]
        if insufficient:
            return False, f"Insufficient samples for: {[r.metric_name for r in insufficient]}"

        # Check for regressions (old wins)
        regressions = [r for r in results if r.winner == "old" and r.significant]
        if regressions:
            return False, f"Regressions detected in: {[r.metric_name for r in regressions]}"

        # Check for improvements (new wins)
        improvements = [r for r in results if r.winner == "new" and r.significant]

        if require_all_metrics:
            if len(improvements) != len(results):
                return False, "Not all metrics show improvement"
            return True, "All metrics show significant improvement"

        if improvements:
            return True, f"Improvements in: {[r.metric_name for r in improvements]}"

        return False, "No significant improvements detected"
